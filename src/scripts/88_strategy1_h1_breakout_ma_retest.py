# -*- coding: utf-8 -*-
"""Strategy 1: H1 double-BB breakout + 120SMA 3-scale entry.

Rules implemented from the latest clarification:
- H1 breakout double-BB is the setup trigger.
- Entry is tested on 1m, 5m, and 10m lower timeframes.
- First entry is the lower-TF 120SMA touch after the H1 breakout closes.
- Three equal-unit limit entries are used at 10 point spacing:
    long:  E1=120SMA, E2=E1-10P, E3=E1-20P
    short: E1=120SMA, E2=E1+10P, E3=E1+20P
- No fixed take-profit. After price reaches the current average entry
  breakeven, a 5 point trailing stop is armed.

TODO: A hard stop was not specified. This first pass uses max_holding_hours and
exits at the final close if breakeven/trailing is never reached.
"""
from __future__ import annotations

import contextlib
import io
import math
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gold_data_prep as prep  # noqa: E402


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "result" / "strategy1_h1_breakout_120sma_scale_trail"

ENTRY_TFS = ["1m", "5m", "10m"]
SMA_LEN = 120
ENTRY_SPACING_POINTS = 10.0
MAX_ENTRIES = 3
TRAIL_POINTS = 5.0
MAX_WAIT_HOURS = 6
MAX_HOLD_HOURS = 24
ROUND_TRIP_COST_POINTS_PER_UNIT = 0.40


def _quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _round_report(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(3)
    return out


def make_h1_breakout_signals(df10: pd.DataFrame) -> pd.DataFrame:
    h1 = (
        df10[["open", "high", "low", "close", "volume"]]
        .resample("1h", label="left", closed="left")
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        .dropna(subset=["open", "high", "low", "close"])
    )
    h1.attrs["timeframe"] = "1h"
    h1 = prep.add_bollinger_bands(h1)
    h1["h1_bar_time"] = h1.index
    h1["h1_signal_time"] = h1.index + pd.Timedelta(hours=1)
    h1["h1_breakout_long"] = (
        (h1["close"] > h1["bb20_2_upper_close"])
        & (h1["close"] > h1["bb4_4_upper_open"])
    ).fillna(False)
    h1["h1_breakout_short"] = (
        (h1["close"] < h1["bb20_2_lower_close"])
        & (h1["close"] < h1["bb4_4_lower_open"])
    ).fillna(False)

    rows = []
    signals = h1[h1["h1_breakout_long"] | h1["h1_breakout_short"]]
    for _, row in signals.iterrows():
        direction = "long" if bool(row["h1_breakout_long"]) else "short"
        rows.append({
            "direction": direction,
            "h1_bar_time": row["h1_bar_time"],
            "h1_signal_time": row["h1_signal_time"],
            "h1_open": float(row["open"]),
            "h1_high": float(row["high"]),
            "h1_low": float(row["low"]),
            "h1_close": float(row["close"]),
        })
    return pd.DataFrame(rows).sort_values("h1_signal_time").reset_index(drop=True)


def load_entry_tf(timeframe: str) -> pd.DataFrame:
    path = DATA_DIR / ("xauusd_%s_2010-01-01_2026-06-16.csv" % timeframe)
    df = _quiet_call(prep.load_gold_data, path, timeframe=timeframe)
    df = prep.assign_session(df)
    df["sma120"] = df["close"].rolling(SMA_LEN, min_periods=SMA_LEN).mean()
    return df


def find_first_sma_touch(df: pd.DataFrame, signal: pd.Series) -> dict | None:
    direction = signal["direction"]
    start_time = signal["h1_signal_time"]
    end_time = start_time + pd.Timedelta(hours=MAX_WAIT_HOURS)
    window = df.loc[(df.index >= start_time) & (df.index < end_time)]
    if window.empty:
        return None

    for entry_time, bar in window.iterrows():
        sma = bar["sma120"]
        if pd.isna(sma):
            continue
        touched = bar["low"] <= sma if direction == "long" else bar["high"] >= sma
        if touched:
            return {
                "entry_time": entry_time,
                "entry_1_price": float(sma),
                "session": bar["session"] if "session" in window.columns else "unknown",
            }
    return None


def _entry_levels(entry_1: float, direction: str) -> list[float]:
    if direction == "long":
        return [entry_1 - i * ENTRY_SPACING_POINTS for i in range(MAX_ENTRIES)]
    return [entry_1 + i * ENTRY_SPACING_POINTS for i in range(MAX_ENTRIES)]


def resolve_scaled_trade(df: pd.DataFrame, signal: pd.Series, entry: dict) -> dict | None:
    direction = signal["direction"]
    entry_time = entry["entry_time"]
    start_pos = df.index.searchsorted(entry_time)
    if start_pos >= len(df):
        return None

    bar_delta = df.index[1] - df.index[0]
    max_hold_bars = int(pd.Timedelta(hours=MAX_HOLD_HOURS) / bar_delta)
    end_pos = min(len(df) - 1, start_pos + max_hold_bars - 1)

    levels = _entry_levels(float(entry["entry_1_price"]), direction)
    filled = [False] * MAX_ENTRIES
    fill_times = [pd.NaT] * MAX_ENTRIES
    fill_prices = []
    open_units = 0
    avg_entry = math.nan
    trailing_armed = False
    trail_stop = math.nan
    best_favorable_price = math.nan
    max_favorable_points = 0.0
    max_adverse_points = 0.0
    exit_reason = "time_exit"
    exit_price = float(df["close"].iloc[end_pos])
    exit_time = df.index[end_pos]

    for pos in range(start_pos, end_pos + 1):
        hi = float(df["high"].iloc[pos])
        lo = float(df["low"].iloc[pos])
        close = float(df["close"].iloc[pos])

        for level_i, level in enumerate(levels):
            if filled[level_i]:
                continue
            hit = lo <= level if direction == "long" else hi >= level
            if hit:
                filled[level_i] = True
                fill_times[level_i] = df.index[pos]
                fill_prices.append(level)
                open_units += 1
                avg_entry = sum(fill_prices) / len(fill_prices)
                trailing_armed = False
                trail_stop = math.nan
                best_favorable_price = math.nan

        if open_units == 0:
            continue

        if direction == "long":
            max_favorable_points = max(max_favorable_points, hi - avg_entry)
            max_adverse_points = max(max_adverse_points, avg_entry - lo)
            if not trailing_armed and hi >= avg_entry:
                trailing_armed = True
                best_favorable_price = hi
                trail_stop = max(avg_entry, best_favorable_price - TRAIL_POINTS)
            elif trailing_armed:
                best_favorable_price = max(best_favorable_price, hi)
                trail_stop = max(avg_entry, best_favorable_price - TRAIL_POINTS)
            if trailing_armed and lo <= trail_stop:
                exit_reason = "trail_5p"
                exit_price = trail_stop
                exit_time = df.index[pos]
                break
        else:
            max_favorable_points = max(max_favorable_points, avg_entry - lo)
            max_adverse_points = max(max_adverse_points, hi - avg_entry)
            if not trailing_armed and lo <= avg_entry:
                trailing_armed = True
                best_favorable_price = lo
                trail_stop = min(avg_entry, best_favorable_price + TRAIL_POINTS)
            elif trailing_armed:
                best_favorable_price = min(best_favorable_price, lo)
                trail_stop = min(avg_entry, best_favorable_price + TRAIL_POINTS)
            if trailing_armed and hi >= trail_stop:
                exit_reason = "trail_5p"
                exit_price = trail_stop
                exit_time = df.index[pos]
                break

        if pos == end_pos:
            exit_price = close

    if open_units == 0 or pd.isna(avg_entry):
        return None

    gross_points_per_unit = (exit_price - avg_entry) if direction == "long" else (avg_entry - exit_price)
    gross_points_total = gross_points_per_unit * open_units
    cost_points_total = ROUND_TRIP_COST_POINTS_PER_UNIT * open_units
    net_points_total = gross_points_total - cost_points_total

    return {
        "entry_1_price": levels[0],
        "entry_2_price": levels[1],
        "entry_3_price": levels[2],
        "entry_1_time": fill_times[0],
        "entry_2_time": fill_times[1],
        "entry_3_time": fill_times[2],
        "filled_entries": int(open_units),
        "avg_entry": avg_entry,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_points_per_unit": gross_points_per_unit,
        "gross_points_total": gross_points_total,
        "cost_points_total": cost_points_total,
        "net_points_total": net_points_total,
        "net_10p": net_points_total / ENTRY_SPACING_POINTS,
        "mfe_points": max_favorable_points,
        "mae_points": max_adverse_points,
        "mfe_10p": max_favorable_points / ENTRY_SPACING_POINTS,
        "mae_10p": max_adverse_points / ENTRY_SPACING_POINTS,
        "hold_bars": int(df.index.searchsorted(exit_time) - start_pos + 1),
    }


def build_trades(signals: pd.DataFrame, df: pd.DataFrame, entry_tf: str) -> pd.DataFrame:
    rows = []
    for _, signal in signals.iterrows():
        entry = find_first_sma_touch(df, signal)
        if entry is None:
            continue
        result = resolve_scaled_trade(df, signal, entry)
        if result is None:
            continue
        row = signal.to_dict()
        row.update(entry)
        row.update(result)
        row.update({
            "entry_tf": entry_tf,
            "sma_len": SMA_LEN,
            "entry_spacing_points": ENTRY_SPACING_POINTS,
            "trail_points": TRAIL_POINTS,
            "year": pd.Timestamp(entry["entry_time"]).year,
        })
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def profit_factor(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    gp = vals[vals > 0].sum()
    gl = abs(vals[vals < 0].sum())
    if gl == 0:
        return math.inf if gp > 0 else 0.0
    return float(gp / gl)


def max_drawdown(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").fillna(0.0)
    eq = vals.cumsum()
    dd = eq.cummax() - eq
    return float(dd.max()) if len(dd) else 0.0


def summarize_group(group: pd.DataFrame) -> dict:
    if group.empty:
        return {
            "trades": 0,
            "win_rate": math.nan,
            "expectancy_points_total": math.nan,
            "expectancy_10p": math.nan,
            "profit_factor": math.nan,
            "max_drawdown_points": math.nan,
            "cumulative_points": 0.0,
            "avg_filled_entries": math.nan,
            "avg_mfe_10p": math.nan,
            "avg_mae_10p": math.nan,
        }
    pnl = pd.to_numeric(group["net_points_total"], errors="coerce")
    return {
        "trades": int(len(group)),
        "win_rate": float((pnl > 0).mean()),
        "expectancy_points_total": float(pnl.mean()),
        "expectancy_10p": float(pd.to_numeric(group["net_10p"], errors="coerce").mean()),
        "profit_factor": profit_factor(pnl),
        "max_drawdown_points": max_drawdown(pnl),
        "cumulative_points": float(pnl.sum()),
        "avg_filled_entries": float(pd.to_numeric(group["filled_entries"], errors="coerce").mean()),
        "avg_mfe_10p": float(pd.to_numeric(group["mfe_10p"], errors="coerce").mean()),
        "avg_mae_10p": float(pd.to_numeric(group["mae_10p"], errors="coerce").mean()),
    }


def summarize(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    by_year_rows = []
    by_session_rows = []
    by_exit_rows = []

    for key, group in trades.groupby(["entry_tf", "direction"], sort=True):
        row = {"entry_tf": key[0], "direction": key[1]}
        row.update(summarize_group(group))
        summary_rows.append(row)
    for entry_tf, group in trades.groupby("entry_tf", sort=True):
        row = {"entry_tf": entry_tf, "direction": "combined"}
        row.update(summarize_group(group))
        summary_rows.append(row)

    for key, group in trades.groupby(["entry_tf", "direction", "year"], sort=True):
        row = {"entry_tf": key[0], "direction": key[1], "year": int(key[2])}
        row.update(summarize_group(group))
        by_year_rows.append(row)

    for key, group in trades.groupby(["entry_tf", "direction", "session"], sort=True):
        row = {"entry_tf": key[0], "direction": key[1], "session": key[2]}
        row.update(summarize_group(group))
        by_session_rows.append(row)

    for key, group in trades.groupby(["entry_tf", "direction", "exit_reason"], sort=True):
        row = {"entry_tf": key[0], "direction": key[1], "exit_reason": key[2]}
        row.update(summarize_group(group))
        by_exit_rows.append(row)

    return (
        _round_report(pd.DataFrame(summary_rows)),
        _round_report(pd.DataFrame(by_year_rows)),
        _round_report(pd.DataFrame(by_session_rows)),
        _round_report(pd.DataFrame(by_exit_rows)),
    )


def run() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df10 = load_entry_tf("10m")
    signals = make_h1_breakout_signals(df10)

    all_trades = []
    cache = {"10m": df10}
    for entry_tf in ENTRY_TFS:
        df = cache.get(entry_tf)
        if df is None:
            df = load_entry_tf(entry_tf)
            cache[entry_tf] = df
        trades = build_trades(signals, df, entry_tf)
        if not trades.empty:
            all_trades.append(trades)

    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    summary, by_year, by_session, by_exit = summarize(trades)

    trades.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_trail_trades.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_trail_summary.csv", index=False, encoding="utf-8-sig")
    by_year.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_trail_by_year.csv", index=False, encoding="utf-8-sig")
    by_session.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_trail_by_session.csv", index=False, encoding="utf-8-sig")
    by_exit.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_trail_by_exit.csv", index=False, encoding="utf-8-sig")

    top = summary.sort_values("expectancy_10p", ascending=False)
    print("")
    print("=== STRATEGY 1: 120SMA 3-SCALE 10P TRAIL ===")
    print("H1 double-BB breakout -> lower-TF 120SMA touch -> 3 entries every 10P adverse -> BE then 5P trailing")
    print("max_wait_hours=%s max_hold_hours=%s cost_per_unit=%s" % (
        MAX_WAIT_HOURS,
        MAX_HOLD_HOURS,
        ROUND_TRIP_COST_POINTS_PER_UNIT,
    ))
    print("H1 signals:", len(signals))
    print("Trades:", len(trades))
    print("")
    cols = [
        "entry_tf",
        "direction",
        "trades",
        "win_rate",
        "expectancy_points_total",
        "expectancy_10p",
        "profit_factor",
        "max_drawdown_points",
        "cumulative_points",
        "avg_filled_entries",
        "avg_mfe_10p",
        "avg_mae_10p",
    ]
    print(top[cols].to_string(index=False))
    print("")
    print("WROTE:", OUTPUT_DIR)
    return {
        "trades": trades,
        "summary": summary,
        "by_year": by_year,
        "by_session": by_session,
        "by_exit": by_exit,
    }


if __name__ == "__main__":
    run()
