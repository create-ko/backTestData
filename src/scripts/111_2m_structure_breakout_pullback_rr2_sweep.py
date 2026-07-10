# -*- coding: utf-8 -*-
"""2m structural breakout-pullback fixed 1:2 RR sweep.

Concept:
- Build a rolling structural high/low from prior 2m bars.
- A breakout occurs when close crosses beyond that level.
- Wait for a pullback that touches the broken level and closes back on the
  breakout side.
- Enter on the next 2m open.
- Stop behind the retest candle or the structure level, target exactly 2R.

Unlike the older micro-retest script, this evaluates all signals then applies a
practical max-concurrent-position cap, which better matches the requested
10-20 trades/day profile.
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
OUTPUT_DIR = ROOT / "result" / "structure_breakout_pullback_rr2_sweep"


spec = importlib.util.spec_from_file_location("base100_for_111", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
sys.modules["base100_for_111"] = base
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


LOOKBACKS = env_int_list("LOOKBACKS", [12, 24, 48])
RETEST_WINDOWS = env_int_list("RETEST_WINDOWS", [3, 6])
STOP_BUFFERS = env_float_list("STOP_BUFFERS", [0.2, 0.5])
MIN_RISKS = env_float_list("MIN_RISKS", [0.8])
MAX_RISKS = env_float_list("MAX_RISKS", [4.0, 8.0])
MAX_HOLD_BARS_SET = env_int_list("MAX_HOLD_BARS_SET", [20])
CONCURRENCY_CAPS = env_int_list("CONCURRENCY_CAPS", [5])
STOP_MODES = env_str_list("STOP_MODES", ["retest", "level"])


def load_data() -> pd.DataFrame:
    full = quiet_call(base.load_tf, "2m")
    start = pd.Timestamp(TEST_START, tz="Asia/Seoul")
    end = pd.Timestamp(TEST_END, tz="Asia/Seoul")
    df = full[(full.index >= start) & (full.index < end)].copy()
    df["sma20"] = df["close"].rolling(20, min_periods=20).mean()
    df["sma120"] = df["close"].rolling(120, min_periods=120).mean()
    return df


def entry_time_allowed(ts: pd.Timestamp) -> bool:
    return base.entry_time_allowed(ts)


def find_entries(df: pd.DataFrame, lookback: int, retest_window: int) -> pd.DataFrame:
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    open_ = df["open"].to_numpy(float)
    sessions = df["session"].astype(str).to_numpy()
    prior_high = df["high"].shift(1).rolling(lookback, min_periods=lookback).max().to_numpy(float)
    prior_low = df["low"].shift(1).rolling(lookback, min_periods=lookback).min().to_numpy(float)
    prev_close = df["close"].shift(1).to_numpy(float)
    rows = []

    for breakout_pos in range(max(lookback + 1, 120), len(df) - retest_window - 2):
        long_break = close[breakout_pos] > prior_high[breakout_pos] and prev_close[breakout_pos] <= prior_high[breakout_pos]
        short_break = close[breakout_pos] < prior_low[breakout_pos] and prev_close[breakout_pos] >= prior_low[breakout_pos]
        if long_break and short_break:
            continue
        if not (long_break or short_break):
            continue

        direction = "long" if long_break else "short"
        level = float(prior_high[breakout_pos] if direction == "long" else prior_low[breakout_pos])
        retest_pos = None
        search_end = min(len(df) - 2, breakout_pos + retest_window)
        for pos in range(breakout_pos + 1, search_end + 1):
            if direction == "long":
                touched = low[pos] <= level
                confirmed = close[pos] >= level
            else:
                touched = high[pos] >= level
                confirmed = close[pos] <= level
            if touched and confirmed:
                retest_pos = pos
                break
        if retest_pos is None:
            continue

        entry_pos = retest_pos + 1
        if not entry_time_allowed(idx[entry_pos]):
            continue
        ts = idx[entry_pos]
        rows.append({
            "lookback": lookback,
            "retest_window": retest_window,
            "direction": direction,
            "breakout_pos": breakout_pos,
            "retest_pos": retest_pos,
            "entry_pos": entry_pos,
            "breakout_time": idx[breakout_pos],
            "retest_time": idx[retest_pos],
            "entry_time": ts,
            "level": level,
            "entry_price": float(open_[entry_pos]),
            "breakout_high": float(high[breakout_pos]),
            "breakout_low": float(low[breakout_pos]),
            "retest_high": float(high[retest_pos]),
            "retest_low": float(low[retest_pos]),
            "session": str(sessions[entry_pos]),
            "year": int(ts.year),
            "month": ts.strftime("%Y-%m"),
            "day": ts.date().isoformat(),
        })
    return pd.DataFrame(rows)


def apply_concurrency_cap(trades: pd.DataFrame, cap: int) -> pd.DataFrame:
    open_exits = []
    kept = []
    for _, row in trades.sort_values("entry_time").iterrows():
        entry_time = row["entry_time"]
        open_exits = [exit_time for exit_time in open_exits if exit_time > entry_time]
        if len(open_exits) >= cap:
            continue
        kept.append(row)
        open_exits.append(row["exit_time"])
    return pd.DataFrame(kept).reset_index(drop=True) if kept else trades.iloc[0:0].copy()


def simulate_rr2(
    df: pd.DataFrame,
    entries: pd.DataFrame,
    stop_mode: str,
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

    for _, entry_row in entries.iterrows():
        entry_pos = int(entry_row["entry_pos"])
        direction = str(entry_row["direction"])
        entry_price = float(entry_row["entry_price"])
        level = float(entry_row["level"])
        if direction == "long":
            if stop_mode == "level":
                stop_price = level - stop_buffer
            elif stop_mode == "retest":
                stop_price = float(entry_row["retest_low"]) - stop_buffer
            else:
                raise ValueError("unknown stop_mode: %s" % stop_mode)
            risk = entry_price - stop_price
            target_price = entry_price + 2.0 * risk
        else:
            if stop_mode == "level":
                stop_price = level + stop_buffer
            elif stop_mode == "retest":
                stop_price = float(entry_row["retest_high"]) + stop_buffer
            else:
                raise ValueError("unknown stop_mode: %s" % stop_mode)
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
            **entry_row.to_dict(),
            "stop_mode": stop_mode,
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
    header{background:#101820;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#c9d3df}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    target = summary[summary["full_target_frequency"]].sort_values("full_net_points", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m Structure Breakout Pullback RR2 Sweep</title><style>%s</style></head>
<body><header><h1>2m Structure Breakout Pullback RR2 Sweep</h1><p>Fixed 1:2 RR rolling high/low breakout, pullback confirmation, max concurrent cap.</p></header><main>
%s%s
</main></body></html>""" % (
        css,
        table_html(target, "Configs Within 10-20 Trades/Day On Full Period", 160),
        table_html(summary.sort_values("score", ascending=False), "All Configs Ranked", 200),
    )
    (OUTPUT_DIR / "structure_breakout_pullback_rr2_sweep_report.html").write_text(html, encoding="utf-8")


def prefix_metrics(prefix: str, metrics: dict) -> dict:
    return {prefix + "_" + key: value for key, value in metrics.items()}


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    trading_days = int(pd.Series(df.index.date).nunique())
    trading_days_2026 = int(pd.Series(df[df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")].index.date).nunique())
    rows = []
    best_trades = None
    best_key = None
    best_net = -math.inf

    for lookback in LOOKBACKS:
        for retest_window in RETEST_WINDOWS:
            entries = find_entries(df, lookback, retest_window)
            print("ENTRIES", "lookback", lookback, "retest", retest_window, len(entries), flush=True)
            if entries.empty:
                continue
            for stop_mode in STOP_MODES:
                for stop_buffer in STOP_BUFFERS:
                    for min_risk in MIN_RISKS:
                        for max_risk in MAX_RISKS:
                            if min_risk >= max_risk:
                                continue
                            for max_hold_bars in MAX_HOLD_BARS_SET:
                                for cap in CONCURRENCY_CAPS:
                                    trades = simulate_rr2(df, entries, stop_mode, stop_buffer, min_risk, max_risk, max_hold_bars, cap)
                                    if trades.empty:
                                        continue
                                    trades2026 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
                                    config_id = "lb%s_rt%s_%s_sb%s_min%s_max%s_hold%s_cap%s" % (
                                        lookback,
                                        retest_window,
                                        stop_mode,
                                        str(stop_buffer).replace(".", "p"),
                                        str(min_risk).replace(".", "p"),
                                        str(max_risk).replace(".", "p"),
                                        max_hold_bars,
                                        cap,
                                    )
                                    row = {
                                        "config_id": config_id,
                                        "lookback": lookback,
                                        "retest_window": retest_window,
                                        "stop_mode": stop_mode,
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
    summary.to_csv(OUTPUT_DIR / "structure_breakout_pullback_rr2_sweep_summary.csv", index=False, encoding="utf-8-sig")
    if best_trades is not None:
        best_trades.to_csv(OUTPUT_DIR / "structure_breakout_pullback_rr2_best_trades.csv", index=False, encoding="utf-8-sig")
    write_html(summary)

    print("=== 2M STRUCTURE BREAKOUT PULLBACK RR2 SWEEP ===")
    print("Configs:", len(summary), "Trading days:", trading_days, "2026 days:", trading_days_2026)
    print("Best target-frequency config:", best_key)
    print(summary.head(40).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
