# -*- coding: utf-8 -*-
"""2m trend-pullback fixed 1:2 RR sweep.

Concept:
- Trade with the local 2m trend instead of chasing a breakout extreme.
- Long: fast SMA is above slow SMA, price pulls back to the fast SMA area,
  then closes back upward with a small confirmation candle.
- Short: mirror logic.
- Enter next 2m open, stop behind the pullback swing, target exactly 2R.

The purpose is to test a materially different signal family after BB/structure
breakout variants failed to produce enough 2R follow-through.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import math
import os
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_SCRIPT = SCRIPT_DIR / "100_strategy2_grid_multitimeframe_month_filter.py"

TEST_START = os.environ.get("TEST_START", "2023-01-01")
TEST_END = os.environ.get("TEST_END", "2026-06-17")
ROUND_TURN_COST_POINTS = float(os.environ.get("ROUND_TURN_COST_POINTS", "0.5"))
OUTPUT_DIR = ROOT / "result" / "trend_pullback_rr2_sweep"


spec = importlib.util.spec_from_file_location("base100_for_114", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
sys.modules["base100_for_114"] = base
assert spec.loader is not None
spec.loader.exec_module(base)


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def env_int_list(name: str, default: list[int]) -> list[int]:
    raw = os.environ.get(name)
    return [int(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def env_float_list(name: str, default: list[float]) -> list[float]:
    raw = os.environ.get(name)
    return [float(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def env_str_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else default


FAST_SMAS = env_int_list("FAST_SMAS", [10, 20])
SLOW_SMAS = env_int_list("SLOW_SMAS", [60, 120])
PULLBACK_WINDOWS = env_int_list("PULLBACK_WINDOWS", [3, 5])
TOUCH_BUFFERS = env_float_list("TOUCH_BUFFERS", [0.2, 0.5, 1.0])
STOP_BUFFERS = env_float_list("STOP_BUFFERS", [0.2, 0.5])
MIN_RISKS = env_float_list("MIN_RISKS", [0.8])
MAX_RISKS = env_float_list("MAX_RISKS", [3.0, 5.0, 8.0])
MAX_HOLD_BARS_SET = env_int_list("MAX_HOLD_BARS_SET", [10, 20, 30])
CONCURRENCY_CAPS = env_int_list("CONCURRENCY_CAPS", [5])
CONFIRM_MODES = env_str_list("CONFIRM_MODES", ["close_fast", "engulf", "momentum"])
TREND_MODES = env_str_list("TREND_MODES", ["stack", "slope"])


def load_data() -> pd.DataFrame:
    full = quiet_call(base.load_tf, "2m")
    start = pd.Timestamp(TEST_START, tz="Asia/Seoul")
    end = pd.Timestamp(TEST_END, tz="Asia/Seoul")
    df = full[(full.index >= start) & (full.index < end)].copy()
    for n in sorted(set(FAST_SMAS + SLOW_SMAS + [20, 60, 120])):
        df[f"sma{n}"] = df["close"].rolling(n, min_periods=n).mean()
        df[f"sma{n}_slope"] = df[f"sma{n}"] - df[f"sma{n}"].shift(5)
    df["body"] = (df["close"] - df["open"]).abs()
    df["range"] = df["high"] - df["low"]
    df["median_range20"] = df["range"].rolling(20, min_periods=20).median()
    return df


def entry_time_allowed(ts: pd.Timestamp) -> bool:
    return base.entry_time_allowed(ts)


def trend_ok(row: pd.Series, direction: str, fast: int, slow: int, mode: str) -> bool:
    fast_value = row[f"sma{fast}"]
    slow_value = row[f"sma{slow}"]
    slope = row[f"sma{slow}_slope"]
    if not math.isfinite(float(fast_value)) or not math.isfinite(float(slow_value)):
        return False
    if mode == "stack":
        return fast_value > slow_value if direction == "long" else fast_value < slow_value
    if mode == "slope":
        if direction == "long":
            return fast_value > slow_value and slope > 0
        return fast_value < slow_value and slope < 0
    raise ValueError("unknown trend mode: %s" % mode)


def confirm_ok(df: pd.DataFrame, pos: int, direction: str, fast: int, mode: str) -> bool:
    row = df.iloc[pos]
    prev = df.iloc[pos - 1]
    fast_value = float(row[f"sma{fast}"])
    median_range = float(row["median_range20"])
    body = float(row["body"])
    if not math.isfinite(fast_value) or not math.isfinite(median_range):
        return False
    if mode == "close_fast":
        return row["close"] > fast_value if direction == "long" else row["close"] < fast_value
    if mode == "engulf":
        if direction == "long":
            return row["close"] > row["open"] and row["close"] > prev["high"]
        return row["close"] < row["open"] and row["close"] < prev["low"]
    if mode == "momentum":
        if body < median_range * 0.35:
            return False
        return row["close"] > row["open"] if direction == "long" else row["close"] < row["open"]
    raise ValueError("unknown confirm mode: %s" % mode)


def find_entries(
    df: pd.DataFrame,
    fast: int,
    slow: int,
    pullback_window: int,
    touch_buffer: float,
    trend_mode: str,
    confirm_mode: str,
) -> pd.DataFrame:
    idx = df.index
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    fast_values = df[f"sma{fast}"].to_numpy(float)
    slow_values = df[f"sma{slow}"].to_numpy(float)
    slow_slopes = df[f"sma{slow}_slope"].to_numpy(float)
    body = df["body"].to_numpy(float)
    median_range20 = df["median_range20"].to_numpy(float)
    sessions = df["session"].astype(str).to_numpy()
    roll_low = df["low"].rolling(pullback_window, min_periods=pullback_window).min().to_numpy(float)
    roll_high = df["high"].rolling(pullback_window, min_periods=pullback_window).max().to_numpy(float)
    roll_close_min = df["close"].rolling(pullback_window, min_periods=pullback_window).min().to_numpy(float)
    roll_close_max = df["close"].rolling(pullback_window, min_periods=pullback_window).max().to_numpy(float)
    rows = []
    start_pos = max(fast, slow, 120) + pullback_window + 2
    for pos in range(start_pos, len(df) - 2):
        entry_pos = pos + 1
        if not entry_time_allowed(idx[entry_pos]):
            continue

        fast_value = float(fast_values[pos])
        slow_value = float(slow_values[pos])
        slow_slope = float(slow_slopes[pos])
        if not math.isfinite(fast_value):
            continue

        for direction in ("long", "short"):
            if trend_mode == "stack":
                trend_is_ok = fast_value > slow_value if direction == "long" else fast_value < slow_value
            elif trend_mode == "slope":
                trend_is_ok = (
                    fast_value > slow_value and slow_slope > 0
                    if direction == "long"
                    else fast_value < slow_value and slow_slope < 0
                )
            else:
                raise ValueError("unknown trend mode: %s" % trend_mode)
            if not trend_is_ok:
                continue

            if direction == "long":
                touched = roll_low[pos] <= fast_value + touch_buffer
                stayed_above_slow = roll_close_min[pos] >= slow_value - touch_buffer
                pullback_extreme = float(roll_low[pos])
            else:
                touched = roll_high[pos] >= fast_value - touch_buffer
                stayed_above_slow = roll_close_max[pos] <= slow_value + touch_buffer
                pullback_extreme = float(roll_high[pos])
            if not touched or not stayed_above_slow:
                continue
            if confirm_mode == "close_fast":
                confirmed = close[pos] > fast_value if direction == "long" else close[pos] < fast_value
            elif confirm_mode == "engulf":
                confirmed = (
                    close[pos] > open_[pos] and close[pos] > high[pos - 1]
                    if direction == "long"
                    else close[pos] < open_[pos] and close[pos] < low[pos - 1]
                )
            elif confirm_mode == "momentum":
                if not math.isfinite(float(median_range20[pos])) or body[pos] < median_range20[pos] * 0.35:
                    confirmed = False
                else:
                    confirmed = close[pos] > open_[pos] if direction == "long" else close[pos] < open_[pos]
            else:
                raise ValueError("unknown confirm mode: %s" % confirm_mode)
            if not confirmed:
                continue

            ts = idx[entry_pos]
            rows.append({
                "fast_sma": fast,
                "slow_sma": slow,
                "pullback_window": pullback_window,
                "touch_buffer": touch_buffer,
                "trend_mode": trend_mode,
                "confirm_mode": confirm_mode,
                "direction": direction,
                "signal_pos": pos,
                "entry_pos": entry_pos,
                "signal_time": idx[pos],
                "entry_time": ts,
                "entry_price": float(open_[entry_pos]),
                "fast_sma_value": fast_value,
                "slow_sma_value": slow_value,
                "pullback_extreme": pullback_extreme,
                "session": str(sessions[entry_pos]),
                "year": int(ts.year),
                "month": ts.strftime("%Y-%m"),
                "day": ts.date().isoformat(),
            })
    return pd.DataFrame(rows)


def apply_concurrency_cap(trades: pd.DataFrame, cap: int) -> pd.DataFrame:
    open_exits = []
    kept_indices = []
    ordered = trades.sort_values("entry_time")
    entry_pos = ordered.columns.get_loc("entry_time")
    exit_pos = ordered.columns.get_loc("exit_time")
    for row in ordered.itertuples(index=True, name=None):
        entry_time = row[entry_pos + 1]
        open_exits = [exit_time for exit_time in open_exits if exit_time > entry_time]
        if len(open_exits) >= cap:
            continue
        kept_indices.append(row[0])
        open_exits.append(row[exit_pos + 1])
    return trades.loc[kept_indices].reset_index(drop=True) if kept_indices else trades.iloc[0:0].copy()


def simulate_rr2(
    df: pd.DataFrame,
    entries: pd.DataFrame,
    stop_buffer: float,
    min_risk: float,
    max_risk: float,
    max_hold_bars: int,
    cap: int,
) -> pd.DataFrame:
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    rows = []

    for entry_row in entries.itertuples(index=False):
        entry_pos = int(entry_row.entry_pos)
        direction = str(entry_row.direction)
        entry_price = float(entry_row.entry_price)
        extreme = float(entry_row.pullback_extreme)
        if direction == "long":
            stop_price = extreme - stop_buffer
            risk = entry_price - stop_price
            target_price = entry_price + 2.0 * risk
        else:
            stop_price = extreme + stop_buffer
            risk = stop_price - entry_price
            target_price = entry_price - 2.0 * risk
        if not math.isfinite(risk) or risk < min_risk or risk > max_risk:
            continue

        end_pos = min(len(df) - 1, entry_pos + max_hold_bars)
        exit_price = float(close[end_pos])
        exit_pos = end_pos
        exit_reason = "time_exit"
        for pos in range(entry_pos, end_pos + 1):
            if direction == "long":
                if low[pos] <= stop_price:
                    exit_price = stop_price
                    exit_pos = pos
                    exit_reason = "stop"
                    break
                if high[pos] >= target_price:
                    exit_price = target_price
                    exit_pos = pos
                    exit_reason = "target_2r"
                    break
            else:
                if high[pos] >= stop_price:
                    exit_price = stop_price
                    exit_pos = pos
                    exit_reason = "stop"
                    break
                if low[pos] <= target_price:
                    exit_price = target_price
                    exit_pos = pos
                    exit_reason = "target_2r"
                    break

        gross = exit_price - entry_price if direction == "long" else entry_price - exit_price
        net = gross - ROUND_TURN_COST_POINTS
        rows.append({
            "fast_sma": int(entry_row.fast_sma),
            "slow_sma": int(entry_row.slow_sma),
            "pullback_window": int(entry_row.pullback_window),
            "touch_buffer": float(entry_row.touch_buffer),
            "trend_mode": str(entry_row.trend_mode),
            "confirm_mode": str(entry_row.confirm_mode),
            "direction": direction,
            "signal_pos": int(entry_row.signal_pos),
            "entry_pos": entry_pos,
            "signal_time": entry_row.signal_time,
            "entry_time": entry_row.entry_time,
            "entry_price": entry_price,
            "fast_sma_value": float(entry_row.fast_sma_value),
            "slow_sma_value": float(entry_row.slow_sma_value),
            "pullback_extreme": extreme,
            "session": str(entry_row.session),
            "year": int(entry_row.year),
            "month": str(entry_row.month),
            "day": str(entry_row.day),
            "stop_buffer": stop_buffer,
            "max_hold_bars": max_hold_bars,
            "max_concurrent_positions": cap,
            "exit_time": idx[exit_pos],
            "stop_price": stop_price,
            "target_price": target_price,
            "risk_points": risk,
            "gross_points": gross,
            "net_points": net,
            "r_net": net / risk,
            "exit_reason": exit_reason,
            "hold_bars": int(exit_pos - entry_pos + 1),
        })

    trades = pd.DataFrame(rows)
    if trades.empty:
        return trades
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    return apply_concurrency_cap(trades, cap)


def profit_factor(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").fillna(0.0)
    gp = vals[vals > 0].sum()
    gl = abs(vals[vals < 0].sum())
    if gl == 0:
        return math.inf if gp > 0 else 0.0
    return float(gp / gl)


def max_drawdown(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").fillna(0.0)
    eq = vals.cumsum()
    dd = eq.cummax() - eq
    return float(dd.max()) if len(vals) else 0.0


def summarize(trades: pd.DataFrame, trading_days: int) -> dict:
    pnl = trades["net_points"].astype(float) if len(trades) else pd.Series(dtype=float)
    yearly = trades.groupby("year")["net_points"].sum() if len(trades) else pd.Series(dtype=float)
    monthly = trades.groupby("month")["net_points"].sum() if len(trades) else pd.Series(dtype=float)
    return {
        "trades": int(len(trades)),
        "trading_days": int(trading_days),
        "active_days": int(trades["day"].nunique()) if len(trades) else 0,
        "trades_per_day": float(len(trades) / trading_days) if trading_days else 0.0,
        "trades_per_active_day": float(len(trades) / trades["day"].nunique()) if len(trades) and trades["day"].nunique() else 0.0,
        "net_points": float(pnl.sum()) if len(pnl) else 0.0,
        "avg_points": float(pnl.mean()) if len(pnl) else 0.0,
        "profit_factor": profit_factor(pnl),
        "win_rate": float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
        "target_rate": float((trades["exit_reason"] == "target_2r").mean() * 100) if len(trades) else 0.0,
        "max_drawdown_points": max_drawdown(pnl),
        "positive_years": int((yearly > 0).sum()) if len(yearly) else 0,
        "years": int(yearly.size),
        "positive_month_rate": float((monthly > 0).mean() * 100) if monthly.size else 0.0,
        "avg_risk": float(trades["risk_points"].mean()) if len(trades) else 0.0,
        "avg_hold_bars": float(trades["hold_bars"].mean()) if len(trades) else 0.0,
    }


def prefix_metrics(prefix: str, metrics: dict) -> dict:
    return {prefix + "_" + key: value for key, value in metrics.items()}


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join("<th>%s</th>" % c for c in show.columns)
    rows = []
    for _, row in show.iterrows():
        cells = []
        for col, value in row.items():
            cls = ""
            if col in {"full_net_points", "sample2026_net_points", "full_profit_factor", "sample2026_profit_factor", "score"}:
                try:
                    num = float(value)
                    cls = "pos" if (num >= 1 if "profit_factor" in col else num > 0) else "neg"
                except Exception:
                    pass
            text = "" if pd.isna(value) else ("%.4f" % value if isinstance(value, float) else str(value))
            cells.append("<td class='%s'>%s</td>" % (cls, text))
        rows.append("<tr>%s</tr>" % "".join(cells))
    return "<section><h2>%s</h2><div><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></section>" % (
        title,
        headers,
        "".join(rows),
    )


def write_html(summary: pd.DataFrame) -> None:
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#16213e;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#d8deea}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    target = summary[summary["full_target_frequency"]].sort_values("full_net_points", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m Trend Pullback RR2 Sweep</title><style>%s</style></head>
<body><header><h1>2m Trend Pullback RR2 Sweep</h1><p>Fixed 1:2 RR trend filter, SMA pullback, confirmation candle, max concurrent cap.</p></header><main>
%s%s
</main></body></html>""" % (
        css,
        table_html(target, "Configs Within 10-20 Trades/Day On Full Period", 160),
        table_html(summary.sort_values("score", ascending=False), "All Configs Ranked", 220),
    )
    (OUTPUT_DIR / "trend_pullback_rr2_sweep_report.html").write_text(html, encoding="utf-8")


def period_table(trades: pd.DataFrame, period_col: str) -> pd.DataFrame:
    rows = []
    for period, group in trades.groupby(period_col):
        pnl = group["net_points"].astype(float)
        rows.append({
            period_col: period,
            "trades": int(len(group)),
            "net_points": float(pnl.sum()),
            "avg_points": float(pnl.mean()),
            "profit_factor": profit_factor(pnl),
            "win_rate": float((pnl > 0).mean() * 100),
            "target_rate": float((group["exit_reason"] == "target_2r").mean() * 100),
            "max_drawdown_points": max_drawdown(pnl),
            "avg_risk": float(group["risk_points"].mean()),
            "avg_hold_bars": float(group["hold_bars"].mean()),
        })
    return round_floats(pd.DataFrame(rows))


def write_best_period_reports(trades: pd.DataFrame) -> None:
    if trades.empty:
        return
    yearly = period_table(trades, "year")
    monthly = period_table(trades, "month")
    yearly.to_csv(OUTPUT_DIR / "trend_pullback_rr2_best_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "trend_pullback_rr2_best_monthly.csv", index=False, encoding="utf-8-sig")

    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#16213e;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#d8deea}
    main{max-width:1500px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child{text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m Trend Pullback RR2 Period Report</title><style>%s</style></head>
<body><header><h1>2m Trend Pullback RR2 Period Report</h1><p>Yearly and monthly report for the selected target-frequency configuration.</p></header><main>
%s%s
</main></body></html>""" % (
        css,
        table_html(yearly, "Yearly Report"),
        table_html(monthly, "Monthly Report"),
    )
    (OUTPUT_DIR / "trend_pullback_rr2_best_period_report.html").write_text(html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    trading_days = int(pd.Series(df.index.date).nunique())
    sample2026 = df[df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
    trading_days_2026 = int(pd.Series(sample2026.index.date).nunique())
    rows = []
    best_trades = None
    best_key = None
    best_net = -math.inf

    for fast in FAST_SMAS:
        for slow in SLOW_SMAS:
            if fast >= slow:
                continue
            for pullback_window in PULLBACK_WINDOWS:
                for touch_buffer in TOUCH_BUFFERS:
                    for trend_mode in TREND_MODES:
                        for confirm_mode in CONFIRM_MODES:
                            entries = find_entries(df, fast, slow, pullback_window, touch_buffer, trend_mode, confirm_mode)
                            print(
                                "ENTRIES",
                                "fast", fast,
                                "slow", slow,
                                "win", pullback_window,
                                "touch", touch_buffer,
                                "trend", trend_mode,
                                "confirm", confirm_mode,
                                len(entries),
                                flush=True,
                            )
                            if entries.empty:
                                continue
                            for stop_buffer in STOP_BUFFERS:
                                for min_risk in MIN_RISKS:
                                    for max_risk in MAX_RISKS:
                                        if min_risk >= max_risk:
                                            continue
                                        for max_hold_bars in MAX_HOLD_BARS_SET:
                                            for cap in CONCURRENCY_CAPS:
                                                trades = simulate_rr2(
                                                    df,
                                                    entries,
                                                    stop_buffer,
                                                    min_risk,
                                                    max_risk,
                                                    max_hold_bars,
                                                    cap,
                                                )
                                                if trades.empty:
                                                    continue
                                                trades2026 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
                                                config_id = "f%s_s%s_w%s_tb%s_%s_%s_sb%s_min%s_max%s_hold%s_cap%s" % (
                                                    fast,
                                                    slow,
                                                    pullback_window,
                                                    str(touch_buffer).replace(".", "p"),
                                                    trend_mode,
                                                    confirm_mode,
                                                    str(stop_buffer).replace(".", "p"),
                                                    str(min_risk).replace(".", "p"),
                                                    str(max_risk).replace(".", "p"),
                                                    max_hold_bars,
                                                    cap,
                                                )
                                                row = {
                                                    "config_id": config_id,
                                                    "fast_sma": fast,
                                                    "slow_sma": slow,
                                                    "pullback_window": pullback_window,
                                                    "touch_buffer": touch_buffer,
                                                    "trend_mode": trend_mode,
                                                    "confirm_mode": confirm_mode,
                                                    "stop_buffer": stop_buffer,
                                                    "min_risk": min_risk,
                                                    "max_risk": max_risk,
                                                    "max_hold_bars": max_hold_bars,
                                                    "max_concurrent_positions": cap,
                                                }
                                                row.update(prefix_metrics("full", summarize(trades, trading_days)))
                                                row.update(prefix_metrics("sample2026", summarize(trades2026, trading_days_2026)))
                                                row["full_target_frequency"] = 10.0 <= row["full_trades_per_day"] <= 20.0
                                                row["sample2026_target_frequency"] = 10.0 <= row["sample2026_trades_per_day"] <= 20.0
                                                row["score"] = (
                                                    row["full_net_points"]
                                                    - row["full_max_drawdown_points"] * 0.20
                                                    + row["full_positive_month_rate"] * 5.0
                                                    + (1000.0 if row["full_target_frequency"] else 0.0)
                                                    + row["sample2026_net_points"] * 0.10
                                                )
                                                rows.append(row)
                                                if row["full_target_frequency"] and row["full_net_points"] > best_net:
                                                    best_net = row["full_net_points"]
                                                    best_key = config_id
                                                    best_trades = trades.copy()

    summary = round_floats(pd.DataFrame(rows).sort_values(["full_target_frequency", "full_net_points"], ascending=[False, False]))
    summary.to_csv(OUTPUT_DIR / "trend_pullback_rr2_sweep_summary.csv", index=False, encoding="utf-8-sig")
    if best_trades is not None:
        best_trades.to_csv(OUTPUT_DIR / "trend_pullback_rr2_best_trades.csv", index=False, encoding="utf-8-sig")
        write_best_period_reports(best_trades)
    write_html(summary)

    print("=== 2M TREND PULLBACK RR2 SWEEP ===")
    print("Configs:", len(summary), "Trading days:", trading_days, "2026 days:", trading_days_2026)
    print("Best target-frequency config:", best_key)
    print(summary.head(40).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
