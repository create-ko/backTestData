# -*- coding: utf-8 -*-
"""2m rolling false-breakout reversal sweep with fixed 1:2 RR.

The level is the prior rolling high/low.  After a close breaks that level,
the trade is taken only when a later candle closes back inside it.  Entry is
the next 2m open in the reversal direction; the stop is beyond the whole
breakout/failure excursion and the target is exactly 2R.
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE115 = SCRIPT_DIR / "115_2m_session_liquidity_rr2_sweep.py"
TEST_START = os.environ.get("TEST_START", "2023-01-01")
TEST_END = os.environ.get("TEST_END", "2026-06-17")
OUTPUT_DIR = ROOT / "result" / "rolling_false_breakout_reversal_rr2"

spec = importlib.util.spec_from_file_location("base115_for_130", BASE115)
base115 = importlib.util.module_from_spec(spec)
sys.modules["base115_for_130"] = base115
assert spec.loader is not None
spec.loader.exec_module(base115)


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
FAIL_WINDOWS = env_int_list("FAIL_WINDOWS", [1, 3, 6])
BREAKOUT_BODY_MINS = env_float_list("BREAKOUT_BODY_MINS", [0.0, 0.25, 0.4])
BIAS_MODES = env_str_list("BIAS_MODES", ["none", "price_follow"])
DISPLACEMENT_MODES = env_str_list("DISPLACEMENT_MODES", ["close_extreme", "body35_close_extreme"])
COOLDOWN_BARS_SET = env_int_list("COOLDOWN_BARS_SET", [0, 3, 6])
STOP_BUFFERS = env_float_list("STOP_BUFFERS", [0.2, 0.5])
MIN_RISKS = env_float_list("MIN_RISKS", [0.8])
MAX_RISKS = env_float_list("MAX_RISKS", [5.0, 8.0])
MAX_HOLD_BARS_SET = env_int_list("MAX_HOLD_BARS_SET", [20, 30, 45])
CONCURRENCY_CAPS = env_int_list("CONCURRENCY_CAPS", [5])


def load_data() -> pd.DataFrame:
    old_start, old_end = base115.TEST_START, base115.TEST_END
    base115.TEST_START, base115.TEST_END = TEST_START, TEST_END
    try:
        return base115.load_data()
    finally:
        base115.TEST_START, base115.TEST_END = old_start, old_end


def find_entries(
    df: pd.DataFrame,
    lookback: int,
    fail_window: int,
    breakout_body_min: float,
    bias_mode: str,
    displacement_mode: str,
    cooldown_bars: int,
) -> pd.DataFrame:
    idx = df.index
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    body_ratio = df["body_ratio"].to_numpy(float)
    session_id = df["session_id"].to_numpy(int)
    session_name = df["session_name"].astype(str).to_numpy()
    kst_date = df["kst_date"].astype(str).to_numpy()
    prior_high = df["high"].shift(1).rolling(lookback, min_periods=lookback).max().to_numpy(float)
    prior_low = df["low"].shift(1).rolling(lookback, min_periods=lookback).min().to_numpy(float)
    prev_close = df["close"].shift(1).to_numpy(float)
    rows = []
    last_signal_pos = {"high": -10**9, "low": -10**9}
    start = max(120, lookback + 1)

    for breakout_pos in range(start, len(df) - fail_window - 2):
        if not math.isfinite(body_ratio[breakout_pos]) or body_ratio[breakout_pos] < breakout_body_min:
            continue
        candidates = []
        if math.isfinite(prior_high[breakout_pos]) and close[breakout_pos] > prior_high[breakout_pos] and prev_close[breakout_pos] <= prior_high[breakout_pos]:
            candidates.append(("high", "short", prior_high[breakout_pos]))
        if math.isfinite(prior_low[breakout_pos]) and close[breakout_pos] < prior_low[breakout_pos] and prev_close[breakout_pos] >= prior_low[breakout_pos]:
            candidates.append(("low", "long", prior_low[breakout_pos]))
        if len(candidates) != 1:
            continue

        level_key, direction, level = candidates[0]
        if breakout_pos - last_signal_pos[level_key] <= cooldown_bars:
            continue
        fail_pos = None
        for pos in range(breakout_pos + 1, breakout_pos + fail_window + 1):
            if session_id[pos] != session_id[breakout_pos]:
                break
            failed = close[pos] < level if direction == "short" else close[pos] > level
            if failed:
                fail_pos = pos
                break
        if fail_pos is None:
            continue
        entry_pos = fail_pos + 1
        if entry_pos >= len(df) or session_id[entry_pos] != session_id[breakout_pos]:
            continue
        if not base115.bias_allowed(df, entry_pos, direction, bias_mode):
            continue
        if not base115.displacement_allowed(df, fail_pos, direction, displacement_mode):
            continue
        if not base115.entry_time_allowed(idx[entry_pos]):
            continue

        excursion_high = float(max(high[breakout_pos : fail_pos + 1]))
        excursion_low = float(min(low[breakout_pos : fail_pos + 1]))
        ts = idx[entry_pos]
        rows.append({
            "lookback": lookback,
            "fail_window": fail_window,
            "breakout_body_min": breakout_body_min,
            "bias_mode": bias_mode,
            "displacement_mode": displacement_mode,
            "level_name": "rolling_high" if level_key == "high" else "rolling_low",
            "direction": direction,
            "breakout_pos": breakout_pos,
            "retest_pos": fail_pos,
            "entry_pos": entry_pos,
            "breakout_time": idx[breakout_pos],
            "retest_time": idx[fail_pos],
            "entry_time": ts,
            "level": float(level),
            "entry_price": float(open_[entry_pos]),
            "breakout_high": float(high[breakout_pos]),
            "breakout_low": float(low[breakout_pos]),
            "retest_high": excursion_high,
            "retest_low": excursion_low,
            "session": str(session_name[entry_pos]),
            "session_id": int(session_id[entry_pos]),
            "year": int(ts.year),
            "month": ts.strftime("%Y-%m"),
            "day": str(kst_date[entry_pos]),
        })
        last_signal_pos[level_key] = breakout_pos

    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def write_period(prefix: str, trades: pd.DataFrame) -> None:
    if trades.empty:
        return
    trades.to_csv(OUTPUT_DIR / f"{prefix}_trades.csv", index=False, encoding="utf-8-sig")
    agg = lambda group: base115.round_floats(group.agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
        avg_risk=("risk_points", "mean"),
    ).reset_index())
    agg(trades.groupby("year")).to_csv(OUTPUT_DIR / f"{prefix}_yearly.csv", index=False, encoding="utf-8-sig")
    agg(trades.groupby("month")).to_csv(OUTPUT_DIR / f"{prefix}_monthly.csv", index=False, encoding="utf-8-sig")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    days = int(pd.Series(df.index.date).nunique())
    sample_start = pd.Timestamp("2026-01-01", tz="Asia/Seoul")
    days_2026 = int(pd.Series(df[df.index >= sample_start].index.date).nunique())
    rows = []
    best_target = None
    best_quality = None

    for lookback in LOOKBACKS:
        for fail_window in FAIL_WINDOWS:
            for body_min in BREAKOUT_BODY_MINS:
                for bias_mode in BIAS_MODES:
                    for displacement_mode in DISPLACEMENT_MODES:
                        for cooldown in COOLDOWN_BARS_SET:
                            entries = find_entries(df, lookback, fail_window, body_min, bias_mode, displacement_mode, cooldown)
                            print("ENTRIES", lookback, fail_window, body_min, bias_mode, displacement_mode, cooldown, len(entries), flush=True)
                            if entries.empty:
                                continue
                            for stop_buffer in STOP_BUFFERS:
                                for min_risk in MIN_RISKS:
                                    for max_risk in MAX_RISKS:
                                        if min_risk >= max_risk:
                                            continue
                                        for hold in MAX_HOLD_BARS_SET:
                                            for cap in CONCURRENCY_CAPS:
                                                trades = base115.simulate_rr2(df, entries, "retest", stop_buffer, min_risk, max_risk, hold, cap)
                                                if trades.empty:
                                                    continue
                                                t26 = trades[trades["entry_time"] >= sample_start]
                                                row = {
                                                    "config_id": f"lb{lookback}_fw{fail_window}_body{str(body_min).replace('.', 'p')}_{bias_mode}_{displacement_mode}_cd{cooldown}_sb{str(stop_buffer).replace('.', 'p')}_min{str(min_risk).replace('.', 'p')}_max{str(max_risk).replace('.', 'p')}_hold{hold}_cap{cap}",
                                                    "lookback": lookback, "fail_window": fail_window, "breakout_body_min": body_min,
                                                    "bias_mode": bias_mode, "displacement_mode": displacement_mode, "cooldown_bars": cooldown,
                                                    "stop_buffer": stop_buffer, "min_risk": min_risk, "max_risk": max_risk,
                                                    "max_hold_bars": hold, "max_concurrent_positions": cap,
                                                }
                                                row.update({f"full_{k}": v for k, v in base115.summarize(trades, days).items()})
                                                row.update({f"sample2026_{k}": v for k, v in base115.summarize(t26, days_2026).items()})
                                                row["full_target_frequency"] = 8.0 <= row["full_trades_per_day"] <= 14.0
                                                row["score"] = (row["full_net_points"] if row["full_target_frequency"] else -10000.0) + row["full_net_points"] * 0.05 + row["full_profit_factor"] * 10.0
                                                rows.append(row)
                                                if row["full_target_frequency"] and (best_target is None or row["full_net_points"] > best_target[0]):
                                                    best_target = (row["full_net_points"], trades.copy())
                                                if row["full_net_points"] > 0 and (best_quality is None or row["full_net_points"] > best_quality[0]):
                                                    best_quality = (row["full_net_points"], trades.copy())

    summary = pd.DataFrame(rows).sort_values("score", ascending=False) if rows else pd.DataFrame()
    if summary.empty:
        print("NO_RESULTS")
        return
    summary.to_csv(OUTPUT_DIR / "rolling_false_breakout_reversal_rr2_summary.csv", index=False, encoding="utf-8-sig")
    write_period("best_target_frequency", best_target[1] if best_target else pd.DataFrame())
    write_period("best_quality", best_quality[1] if best_quality else pd.DataFrame())
    target = summary[summary["full_target_frequency"]].head(80)
    profitable = summary[summary["full_net_points"] > 0].head(80)
    html = "<html lang='ko'><head><meta charset='utf-8'><title>Rolling False Breakout RR2</title><style>body{font-family:Arial;padding:24px}table{border-collapse:collapse;font-size:12px}th,td{padding:5px;border:1px solid #ddd;white-space:nowrap}th{background:#eef2f7}</style></head><body><h1>2m Rolling False-Breakout Reversal RR2</h1>"
    html += "<h2>8-14 trades/day</h2>" + (target.to_html(index=False) if not target.empty else "<p>없음</p>")
    html += "<h2>Profitable full-period configs</h2>" + (profitable.to_html(index=False) if not profitable.empty else "<p>없음</p>")
    html += "<h2>All configs</h2>" + summary.head(160).to_html(index=False) + "</body></html>"
    (OUTPUT_DIR / "rolling_false_breakout_reversal_rr2_report.html").write_text(html, encoding="utf-8")
    print(summary.head(12).to_string(index=False), flush=True)


if __name__ == "__main__":
    run()
