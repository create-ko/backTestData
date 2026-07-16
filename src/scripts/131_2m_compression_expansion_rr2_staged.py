# -*- coding: utf-8 -*-
"""Staged 2m volatility-compression expansion breakout sweep.

Signal family deliberately differs from the prior BB wick/reversal and
session-liquidity branches:
- the preceding bars are compressed relative to the recent median range;
- the current candle closes through a prior rolling high/low;
- the breakout candle has sufficient body and range expansion;
- enter next 2m open with the breakout candle extreme stop and fixed 2R.

Run the same script in stages by changing TEST_START/TEST_END.  The default
stage is 2026, which keeps the initial search fast; only promising configs
should be rerun for longer periods.
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
TEST_START = os.environ.get("TEST_START", "2026-01-01")
TEST_END = os.environ.get("TEST_END", "2026-06-17")
STAGE = os.environ.get("STAGE", TEST_START[:10].replace("-", "") + "_" + TEST_END[:10].replace("-", ""))
OUTPUT_DIR = ROOT / "result" / "compression_expansion_rr2_staged" / STAGE

spec = importlib.util.spec_from_file_location("base115_for_131", BASE115)
base115 = importlib.util.module_from_spec(spec)
sys.modules["base115_for_131"] = base115
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


LOOKBACKS = env_int_list("LOOKBACKS", [6, 12, 24])
COMPRESSION_WINDOWS = env_int_list("COMPRESSION_WINDOWS", [3, 5])
COMPRESSION_MULTS = env_float_list("COMPRESSION_MULTS", [0.6, 0.8, 1.0])
BODY_MINS = env_float_list("BODY_MINS", [0.35, 0.5])
RANGE_EXPANSION_MINS = env_float_list("RANGE_EXPANSION_MINS", [1.0, 1.2, 1.5])
BIAS_MODES = env_str_list("BIAS_MODES", ["none", "price_follow"])
COOLDOWN_BARS = env_int_list("COOLDOWN_BARS", [0, 3, 6])
STOP_BUFFERS = env_float_list("STOP_BUFFERS", [0.2, 0.5])
MIN_RISKS = env_float_list("MIN_RISKS", [0.8])
MAX_RISKS = env_float_list("MAX_RISKS", [3.0, 5.0, 8.0])
MAX_HOLDS = env_int_list("MAX_HOLDS", [10, 20, 30])
CAPS = env_int_list("CAPS", [5])


def load_data() -> pd.DataFrame:
    old_start, old_end = base115.TEST_START, base115.TEST_END
    base115.TEST_START, base115.TEST_END = TEST_START, TEST_END
    try:
        df = base115.load_data()
    finally:
        base115.TEST_START, base115.TEST_END = old_start, old_end
    df["range_median20_prev"] = df["range_median20"].shift(1)
    df["range_mean3_prev"] = df["bar_range"].shift(1).rolling(3, min_periods=3).mean()
    df["range_mean5_prev"] = df["bar_range"].shift(1).rolling(5, min_periods=5).mean()
    return df


def find_entries(
    df: pd.DataFrame,
    lookback: int,
    compression_window: int,
    compression_mult: float,
    body_min: float,
    expansion_min: float,
    bias_mode: str,
    cooldown: int,
) -> pd.DataFrame:
    idx = df.index
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    body_ratio = df["body_ratio"].to_numpy(float)
    bar_range = df["bar_range"].to_numpy(float)
    median_prev = df["range_median20_prev"].to_numpy(float)
    compressed_mean = df[f"range_mean{compression_window}_prev"].to_numpy(float)
    prior_high = df["high"].shift(1).rolling(lookback, min_periods=lookback).max().to_numpy(float)
    prior_low = df["low"].shift(1).rolling(lookback, min_periods=lookback).min().to_numpy(float)
    prev_close = df["close"].shift(1).to_numpy(float)
    sessions = df["session_id"].to_numpy(int)
    session_name = df["session_name"].astype(str).to_numpy()
    dates = df["kst_date"].astype(str).to_numpy()
    rows = []
    last_signal = {"long": -10**9, "short": -10**9}
    start = max(120, lookback + 2, compression_window + 2)

    for pos in range(start, len(df) - 2):
        if not all(math.isfinite(float(x)) for x in (body_ratio[pos], bar_range[pos], median_prev[pos], compressed_mean[pos])):
            continue
        if compressed_mean[pos] > median_prev[pos] * compression_mult:
            continue
        if body_ratio[pos] < body_min or bar_range[pos] < median_prev[pos] * expansion_min:
            continue
        candidates = []
        if close[pos] > prior_high[pos] and prev_close[pos] <= prior_high[pos]:
            candidates.append("long")
        if close[pos] < prior_low[pos] and prev_close[pos] >= prior_low[pos]:
            candidates.append("short")
        if len(candidates) != 1:
            continue
        direction = candidates[0]
        if pos - last_signal[direction] <= cooldown:
            continue
        entry_pos = pos + 1
        if sessions[entry_pos] != sessions[pos] or not base115.entry_time_allowed(idx[entry_pos]):
            continue
        if not base115.bias_allowed(df, entry_pos, direction, bias_mode):
            continue
        ts = idx[entry_pos]
        rows.append({
            "lookback": lookback,
            "compression_window": compression_window,
            "compression_mult": compression_mult,
            "body_min": body_min,
            "expansion_min": expansion_min,
            "bias_mode": bias_mode,
            "cooldown_bars": cooldown,
            "level_name": "rolling_high" if direction == "long" else "rolling_low",
            "direction": direction,
            "breakout_pos": pos,
            "retest_pos": pos,
            "entry_pos": entry_pos,
            "breakout_time": idx[pos],
            "retest_time": idx[pos],
            "entry_time": ts,
            "level": float(prior_high[pos] if direction == "long" else prior_low[pos]),
            "entry_price": float(open_[entry_pos]),
            "breakout_high": float(high[pos]),
            "breakout_low": float(low[pos]),
            "retest_high": float(high[pos]),
            "retest_low": float(low[pos]),
            "session": str(session_name[entry_pos]),
            "session_id": int(sessions[entry_pos]),
            "year": int(ts.year),
            "month": ts.strftime("%Y-%m"),
            "day": dates[entry_pos],
        })
        last_signal[direction] = pos
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def prefixed(prefix: str, metrics: dict) -> dict:
    return {prefix + "_" + k: v for k, v in metrics.items()}


def period_report(prefix: str, trades: pd.DataFrame) -> None:
    if trades.empty:
        return
    trades.to_csv(OUTPUT_DIR / f"{prefix}_trades.csv", index=False, encoding="utf-8-sig")
    yearly = trades.groupby("year").agg(trades=("net_points", "size"), net_points=("net_points", "sum"), avg_points=("net_points", "mean"), target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100))).reset_index()
    monthly = trades.groupby("month").agg(trades=("net_points", "size"), net_points=("net_points", "sum"), avg_points=("net_points", "mean"), target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100))).reset_index()
    base115.round_floats(yearly).to_csv(OUTPUT_DIR / f"{prefix}_yearly.csv", index=False, encoding="utf-8-sig")
    base115.round_floats(monthly).to_csv(OUTPUT_DIR / f"{prefix}_monthly.csv", index=False, encoding="utf-8-sig")


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
        for window in COMPRESSION_WINDOWS:
            for comp_mult in COMPRESSION_MULTS:
                for body_min in BODY_MINS:
                    for expansion_min in RANGE_EXPANSION_MINS:
                        for bias_mode in BIAS_MODES:
                            for cooldown in COOLDOWN_BARS:
                                entries = find_entries(df, lookback, window, comp_mult, body_min, expansion_min, bias_mode, cooldown)
                                if entries.empty:
                                    continue
                                for stop_buffer in STOP_BUFFERS:
                                    for min_risk in MIN_RISKS:
                                        for max_risk in MAX_RISKS:
                                            if min_risk >= max_risk:
                                                continue
                                            for hold in MAX_HOLDS:
                                                for cap in CAPS:
                                                    trades = base115.simulate_rr2(df, entries, "retest", stop_buffer, min_risk, max_risk, hold, cap)
                                                    if trades.empty:
                                                        continue
                                                    t26 = trades[trades["entry_time"] >= sample_start]
                                                    row = {
                                                        "config_id": f"lb{lookback}_cw{window}_cm{str(comp_mult).replace('.', 'p')}_body{str(body_min).replace('.', 'p')}_exp{str(expansion_min).replace('.', 'p')}_{bias_mode}_cd{cooldown}_sb{str(stop_buffer).replace('.', 'p')}_min{str(min_risk).replace('.', 'p')}_max{str(max_risk).replace('.', 'p')}_hold{hold}_cap{cap}",
                                                        "lookback": lookback, "compression_window": window, "compression_mult": comp_mult,
                                                        "body_min": body_min, "expansion_min": expansion_min, "bias_mode": bias_mode,
                                                        "cooldown_bars": cooldown, "stop_buffer": stop_buffer, "min_risk": min_risk,
                                                        "max_risk": max_risk, "max_hold_bars": hold, "max_concurrent_positions": cap,
                                                    }
                                                    row.update(prefixed("full", base115.summarize(trades, days)))
                                                    row.update(prefixed("sample2026", base115.summarize(t26, days_2026)))
                                                    row["full_target_frequency"] = 8.0 <= row["full_trades_per_day"] <= 14.0
                                                    row["sample2026_target_frequency"] = 8.0 <= row["sample2026_trades_per_day"] <= 14.0
                                                    row["score"] = row["full_net_points"] + row["sample2026_net_points"] * 0.1 - row["full_max_drawdown_points"] * 0.05 + (1000 if row["full_target_frequency"] else 0)
                                                    rows.append(row)
                                                    if row["sample2026_target_frequency"] and row["sample2026_net_points"] > 0 and (best_target is None or row["sample2026_net_points"] > best_target[0]):
                                                        best_target = (row["sample2026_net_points"], trades.copy())
                                                    if row["full_net_points"] > 0 and (best_quality is None or row["full_net_points"] > best_quality[0]):
                                                        best_quality = (row["full_net_points"], trades.copy())

    summary = pd.DataFrame(rows).sort_values("score", ascending=False) if rows else pd.DataFrame()
    if summary.empty:
        print("NO_RESULTS")
        return
    summary.to_csv(OUTPUT_DIR / "compression_expansion_rr2_summary.csv", index=False, encoding="utf-8-sig")
    period_report("best_2026_target", best_target[1] if best_target else pd.DataFrame())
    period_report("best_full_quality", best_quality[1] if best_quality else pd.DataFrame())
    summary.head(120).to_html(OUTPUT_DIR / "compression_expansion_rr2_report.html", index=False)
    print(summary.head(20).to_string(index=False), flush=True)


if __name__ == "__main__":
    run()
