# -*- coding: utf-8 -*-
"""Completed-15m EMA trend plus 5m pullback candle, fixed 2R, one position."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "mtf_trend_candle_pullback_rr2"
START = "2010-01-01"
SELECTION_START = "2026-01-01"
END = "2026-06-17"
COST = 0.5
TARGET_SESSIONS = {"asia", "europe", "us_open"}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


base = load_module("base100_for_155", SCRIPT_DIR / "100_strategy2_grid_multitimeframe_month_filter.py")
metrics = load_module("metrics144_for_155", SCRIPT_DIR / "144_bb20_rr2_daily2_validation.py")


def prepare() -> pd.DataFrame:
    df = base.load_tf("5m").copy()
    df["day"] = df.index.tz_convert("Asia/Seoul").date.astype(str)
    df["bar_range"] = df["high"] - df["low"]
    df["body"] = (df["close"] - df["open"]).abs()
    df["lower_wick"] = np.minimum(df["open"], df["close"]) - df["low"]
    df["upper_wick"] = df["high"] - np.maximum(df["open"], df["close"])
    df["close_location"] = (df["close"] - df["low"]) / df["bar_range"].replace(0.0, np.nan)
    df["atr14"] = df["bar_range"].rolling(14, min_periods=14).mean()
    return df


def completed_15m_features(df: pd.DataFrame, fast: int, slow: int, slope_bars: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    close15 = df["close"].resample("15min", label="left", closed="left").last().dropna()
    ema_fast = close15.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close15.ewm(span=slow, adjust=False, min_periods=slow).mean()
    slope = ema_fast - ema_fast.shift(slope_bars)
    # At a 5m bar open only the previous 15m bar is complete.
    mapped_fast = ema_fast.shift(1).reindex(df.index, method="ffill")
    mapped_slow = ema_slow.shift(1).reindex(df.index, method="ffill")
    mapped_slope = slope.shift(1).reindex(df.index, method="ffill")
    return mapped_fast, mapped_slow, mapped_slope


def make_entries(
    df: pd.DataFrame,
    ema_fast: pd.Series,
    ema_slow: pd.Series,
    ema_slope: pd.Series,
    pattern: str,
    wick_mult: float,
    close_location_min: float,
    touch_atr: float,
    start: str,
    end: str,
) -> pd.DataFrame:
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    close = df["close"]
    body = df["body"]
    atr = df["atr14"]
    close_loc = df["close_location"]
    long_trend = (ema_fast > ema_slow) & (ema_slope > 0)
    short_trend = (ema_fast < ema_slow) & (ema_slope < 0)
    long_touch = (low <= ema_fast + atr * touch_atr) & (close >= ema_fast)
    short_touch = (high >= ema_fast - atr * touch_atr) & (close <= ema_fast)
    long_rejection = (
        (close > open_) & (df["lower_wick"] >= body * wick_mult)
        & (close_loc >= close_location_min)
    )
    short_rejection = (
        (close < open_) & (df["upper_wick"] >= body * wick_mult)
        & (close_loc <= 1.0 - close_location_min)
    )
    long_engulf = (
        (close > open_) & (close.shift(1) < open_.shift(1))
        & (open_ <= close.shift(1)) & (close >= open_.shift(1))
    )
    short_engulf = (
        (close < open_) & (close.shift(1) > open_.shift(1))
        & (open_ >= close.shift(1)) & (close <= open_.shift(1))
    )
    if pattern == "rejection":
        long_candle, short_candle = long_rejection, short_rejection
    elif pattern == "engulfing":
        long_candle, short_candle = long_engulf, short_engulf
    elif pattern == "either":
        long_candle, short_candle = long_rejection | long_engulf, short_rejection | short_engulf
    else:
        raise ValueError(pattern)

    start_ts = pd.Timestamp(start, tz="Asia/Seoul")
    end_ts = pd.Timestamp(end, tz="Asia/Seoul")
    allowed = df["session"].astype(str).isin(TARGET_SESSIONS)
    within = (df.index >= start_ts) & (df.index < end_ts)
    long_signal = (long_trend & long_touch & long_candle & allowed & within).fillna(False)
    short_signal = (short_trend & short_touch & short_candle & allowed & within).fillna(False)
    positions = np.flatnonzero((long_signal | short_signal).to_numpy(bool))
    if len(positions) == 0:
        return pd.DataFrame()
    valid = positions[(positions + 1) < len(df)]
    valid = valid[
        (df["day"].to_numpy()[valid + 1] == df["day"].to_numpy()[valid])
        & (df["session"].astype(str).to_numpy()[valid + 1] == df["session"].astype(str).to_numpy()[valid])
    ]
    candidate = pd.DataFrame({
        "signal_pos": valid,
        "entry_pos": valid + 1,
        "entry_time": df.index[valid + 1],
        "day": df["day"].to_numpy()[valid],
        "session": df["session"].astype(str).to_numpy()[valid],
        "direction": np.where(long_signal.to_numpy(bool)[valid], "long", "short"),
        "entry_price": df["open"].to_numpy(float)[valid + 1],
        "signal_high": high.to_numpy(float)[valid],
        "signal_low": low.to_numpy(float)[valid],
        "atr": atr.to_numpy(float)[valid],
    })
    # At most one opportunity per KST day/session.
    return candidate.sort_values("entry_time").groupby(["day", "session"], sort=False).head(1).reset_index(drop=True)


def simulate(
    df: pd.DataFrame,
    entries: pd.DataFrame,
    stop_buffer_atr: float,
    max_risk_atr: float,
    max_hold_bars: int,
) -> pd.DataFrame:
    if entries.empty:
        return pd.DataFrame()
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    rows = []
    active_exit = None
    for row in entries.sort_values("entry_time").itertuples(index=False):
        if active_exit is not None and row.entry_time < active_exit:
            continue
        if not math.isfinite(float(row.atr)) or row.atr <= 0:
            continue
        buffer_points = max(0.2, float(row.atr) * stop_buffer_atr)
        if row.direction == "long":
            stop = float(row.signal_low - buffer_points)
            risk = float(row.entry_price - stop)
            target = float(row.entry_price + 2.0 * risk)
        else:
            stop = float(row.signal_high + buffer_points)
            risk = float(stop - row.entry_price)
            target = float(row.entry_price - 2.0 * risk)
        if risk < max(0.8, float(row.atr) * 0.50) or risk > float(row.atr) * max_risk_atr:
            continue
        pos = int(row.entry_pos)
        end = min(len(df) - 1, pos + max_hold_bars)
        exit_pos, exit_price, reason = end, float(close[end]), "time_exit"
        for p in range(pos, end + 1):
            if row.direction == "long":
                if low[p] <= stop:
                    exit_pos, exit_price, reason = p, stop, "stop"
                    break
                if high[p] >= target:
                    exit_pos, exit_price, reason = p, target, "target_2r"
                    break
            else:
                if high[p] >= stop:
                    exit_pos, exit_price, reason = p, stop, "stop"
                    break
                if low[p] <= target:
                    exit_pos, exit_price, reason = p, target, "target_2r"
                    break
        active_exit = df.index[exit_pos]
        gross = exit_price - row.entry_price if row.direction == "long" else row.entry_price - exit_price
        rows.append({
            **row._asdict(),
            "stop_price": stop,
            "target_price": target,
            "risk_points": risk,
            "exit_time": active_exit,
            "gross_points": gross,
            "net_points": gross - COST,
            "r_net": (gross - COST) / risk,
            "exit_reason": reason,
            "hold_bars": exit_pos - pos + 1,
            "year": int(row.entry_time.year),
            "month": row.entry_time.strftime("%Y-%m"),
        })
    return pd.DataFrame(rows)


def selection_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "trades": 0, "active_days": 0, "trades_per_day": 0.0,
            "net_points": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0,
            "win_rate": 0.0, "positive_month_rate": 0.0,
        }
    pnl = trades["net_points"]
    monthly = trades.groupby("month")["net_points"].sum()
    return {
        "trades": len(trades),
        "active_days": trades["day"].nunique(),
        "trades_per_day": len(trades) / 142,
        "net_points": float(pnl.sum()),
        "profit_factor": metrics.profit_factor(pnl),
        "max_drawdown": metrics.max_drawdown(pnl),
        "win_rate": float((pnl > 0).mean() * 100),
        "positive_month_rate": float((monthly > 0).mean() * 100),
    }


def main() -> None:
    df = prepare()
    rows = []
    best = None
    feature_cache = {}
    entry_cache = {}
    for fast, slow in [(20, 50), (20, 100), (50, 100)]:
        for slope_bars in [3, 6]:
            features = completed_15m_features(df, fast, slow, slope_bars)
            feature_cache[(fast, slow, slope_bars)] = features
            for pattern in ["rejection", "engulfing", "either"]:
                wick_values = [1.0, 1.5] if pattern != "engulfing" else [1.0]
                for wick_mult in wick_values:
                    for touch_atr in [0.0, 0.25]:
                        entries = make_entries(
                            df, *features, pattern, wick_mult, 0.65,
                            touch_atr, SELECTION_START, END,
                        )
                        entry_cache[(fast, slow, slope_bars, pattern, wick_mult, touch_atr)] = entries
                        for stop_buffer in [0.10, 0.25]:
                            for max_risk_atr in [2.0, 3.0]:
                                for hold in [24, 48, 96]:
                                    trades = simulate(df, entries, stop_buffer, max_risk_atr, hold)
                                    row = {
                                        "ema_fast": fast, "ema_slow": slow,
                                        "slope_bars": slope_bars, "pattern": pattern,
                                        "wick_mult": wick_mult, "touch_atr": touch_atr,
                                        "stop_buffer_atr": stop_buffer,
                                        "max_risk_atr": max_risk_atr,
                                        "max_hold_bars": hold,
                                    }
                                    row.update(selection_metrics(trades))
                                    row["frequency_pass"] = 1.0 <= row["trades_per_day"] <= 3.0
                                    row["score"] = row["net_points"] - 0.25 * row["max_drawdown"] + 2.0 * row["positive_month_rate"]
                                    rows.append(row)
                                    if row["frequency_pass"] and row["net_points"] > 0 and row["profit_factor"] > 1.0:
                                        rank = (row["positive_month_rate"], row["score"], row["profit_factor"])
                                        if best is None or rank > (best["positive_month_rate"], best["score"], best["profit_factor"]):
                                            best = row.copy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep = pd.DataFrame(rows).sort_values(["frequency_pass", "score"], ascending=[False, False])
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        (OUTPUT / "REPORT.md").write_text("# MTF Trend Candle Pullback RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8")
        print(sweep.head(20).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    feature_key = (int(best["ema_fast"]), int(best["ema_slow"]), int(best["slope_bars"]))
    entries = make_entries(
        df, *feature_cache[feature_key], str(best["pattern"]), float(best["wick_mult"]),
        0.65, float(best["touch_atr"]), START, END,
    )
    fixed = simulate(
        df, entries, float(best["stop_buffer_atr"]),
        float(best["max_risk_atr"]), int(best["max_hold_bars"]),
    )
    metrics.audit_orders(fixed)
    sample = metrics.select_period(fixed, SELECTION_START, END)
    full = metrics.select_period(fixed, START, END)
    result_rows = [metrics.summarize("selection_2026", SELECTION_START, END, 142, sample)]
    for start, end, days in metrics.SLICES:
        result_rows.append(metrics.summarize("3y_chunk", start, end, days, metrics.select_period(fixed, start, end)))
    result_rows.append(metrics.summarize("full", START, END, 5125, full))
    result = pd.DataFrame(result_rows)
    result["frequency_pass"] = result["trades_per_trading_day"].between(1.0, 3.0, inclusive="both")
    result["passed"] = result["frequency_pass"] & result["performance_pass"]
    result.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "session").round(4).to_csv(OUTPUT / "full_by_session.csv", index=False, encoding="utf-8-sig")
    chunk_passes = int(result.loc[result["period"] == "3y_chunk", "performance_pass"].sum())
    full_pass = bool(result.loc[result["period"] == "full", "passed"].iloc[0])
    final = "PASSED" if full_pass and chunk_passes == 6 else ("CONDITIONAL_PASS" if full_pass else "REJECTED")
    keys = [
        "ema_fast", "ema_slow", "slope_bars", "pattern", "wick_mult", "touch_atr",
        "stop_buffer_atr", "max_risk_atr", "max_hold_bars",
    ]
    report = [
        "# MTF Trend Candle Pullback RR2", "",
        "- Trend: only completed 15m EMA state and slope",
        "- Entry: first 5m EMA pullback rejection/engulfing candle per KST day/session, next-bar open",
        "- Exit: signal-wick ATR stop, exact 2R, 0.5-point cost, stop-first ambiguity",
        "- Execution: one position at a time; average frequency target 1 to 3 per trading day", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "Parameters are selected on 2026 and remain fixed in every historical slice.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
