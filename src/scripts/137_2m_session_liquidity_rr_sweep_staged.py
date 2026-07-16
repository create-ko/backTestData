# -*- coding: utf-8 -*-
"""Staged session-liquidity reversal sweep with configurable target R.

This is the first staged branch that explicitly relaxes the 1:2 target only
when needed. Signal generation stays identical across stages, making the
2026 -> 2024-2026 comparison fast and auditable.
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
OUTPUT_DIR = ROOT / "result" / "session_liquidity_rr_sweep_staged" / STAGE

spec = importlib.util.spec_from_file_location("base115_for_137", BASE115)
base115 = importlib.util.module_from_spec(spec)
sys.modules["base115_for_137"] = base115
assert spec.loader is not None
spec.loader.exec_module(base115)


def ints(name, default):
    raw = os.environ.get(name)
    return [int(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def floats(name, default):
    raw = os.environ.get(name)
    return [float(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def strings(name, default):
    raw = os.environ.get(name)
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else default


LEVEL_SETS = strings("LEVEL_SETS", ["or,pdhpdl,prev_session,session_dynamic"])
RETEST_WINDOWS = ints("RETEST_WINDOWS", [3])
COOLDOWNS = ints("COOLDOWNS", [0, 3])
SIGNAL_MODES = strings("SIGNAL_MODES", ["combined"])
BIAS_MODES = strings("BIAS_MODES", ["price_follow"])
DISPLACEMENTS = strings("DISPLACEMENTS", ["close_extreme", "body35_close_extreme"])
TARGET_RS = floats("TARGET_RS", [0.75, 1.0, 1.25, 1.5, 2.0])
STOP_BUFFERS = floats("STOP_BUFFERS", [0.2])
MIN_RISKS = floats("MIN_RISKS", [0.8])
MAX_RISKS = floats("MAX_RISKS", [5.0])
HOLDS = ints("HOLDS", [10, 20, 30])
CAPS = ints("CAPS", [5])
DIRECTION_MODE = os.environ.get("DIRECTION_MODE", "both")


def load_data():
    old_start, old_end = base115.TEST_START, base115.TEST_END
    base115.TEST_START, base115.TEST_END = TEST_START, TEST_END
    try:
        return base115.add_level_columns(base115.load_data(), 8)
    finally:
        base115.TEST_START, base115.TEST_END = old_start, old_end


def simulate(df, entries, target_r, stop_buffer, min_risk, max_risk, hold, cap):
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    sid = df["session_id"].to_numpy(int)
    rows = []
    for item in entries.itertuples(index=False):
        ep = int(item.entry_pos)
        direction = str(item.direction)
        entry = float(item.entry_price)
        stop = float(item.retest_low) - stop_buffer if direction == "long" else float(item.retest_high) + stop_buffer
        risk = entry - stop if direction == "long" else stop - entry
        if not math.isfinite(risk) or risk < min_risk or risk > max_risk:
            continue
        target = entry + target_r * risk if direction == "long" else entry - target_r * risk
        end = min(len(df) - 1, ep + hold)
        while end > ep and sid[end] != sid[ep]:
            end -= 1
        exit_pos, exit_price, reason = end, float(close[end]), "time_exit"
        for pos in range(ep, end + 1):
            stop_hit = low[pos] <= stop if direction == "long" else high[pos] >= stop
            target_hit = high[pos] >= target if direction == "long" else low[pos] <= target
            if stop_hit:
                exit_pos, exit_price, reason = pos, stop, "stop"
                break
            if target_hit:
                exit_pos, exit_price, reason = pos, target, "target"
                break
        gross = exit_price - entry if direction == "long" else entry - exit_price
        net = gross - base115.ROUND_TURN_COST_POINTS
        rows.append({**item._asdict(), "target_r": target_r, "stop_buffer": stop_buffer, "risk_points": risk, "stop_price": stop, "target_price": target, "exit_time": idx[exit_pos], "gross_points": gross, "net_points": net, "r_net": net / risk, "exit_reason": reason, "hold_bars": int(exit_pos - ep + 1)})
    trades = pd.DataFrame(rows)
    if trades.empty:
        return trades
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    return base115.apply_concurrency_cap(trades, cap)


def period_report(prefix, trades):
    if trades.empty:
        return
    trades.to_csv(OUTPUT_DIR / f"{prefix}_trades.csv", index=False, encoding="utf-8-sig")
    for col in ("year", "month"):
        out = trades.groupby(col).agg(trades=("net_points", "size"), net_points=("net_points", "sum"), avg_points=("net_points", "mean"), target_rate=("exit_reason", lambda s: float((s == "target").mean() * 100))).reset_index()
        base115.round_floats(out).to_csv(OUTPUT_DIR / f"{prefix}_{col}.csv", index=False, encoding="utf-8-sig")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    days = int(pd.Series(df.index.date).nunique())
    rows, best = [], None
    for level_set in LEVEL_SETS:
        for retest in RETEST_WINDOWS:
            for cooldown in COOLDOWNS:
                for signal_mode in SIGNAL_MODES:
                    for bias in BIAS_MODES:
                        for displacement in DISPLACEMENTS:
                            entries = base115.find_entries(df, level_set, retest, cooldown, signal_mode, bias, displacement)
                            if DIRECTION_MODE in {"long", "short"} and not entries.empty:
                                entries = entries[entries["direction"] == DIRECTION_MODE].reset_index(drop=True)
                            if entries.empty:
                                continue
                            for target_r in TARGET_RS:
                                for stop_buffer in STOP_BUFFERS:
                                    for min_risk in MIN_RISKS:
                                        for max_risk in MAX_RISKS:
                                            for hold in HOLDS:
                                                for cap in CAPS:
                                                    trades = simulate(df, entries, target_r, stop_buffer, min_risk, max_risk, hold, cap)
                                                    if trades.empty:
                                                        continue
                                                    m = base115.summarize(trades, days)
                                                    row = {"config_id": f"{level_set.replace(',', '-')}_rt{retest}_{signal_mode}_{bias}_{displacement}_cd{cooldown}_r{str(target_r).replace('.', 'p')}_sb{str(stop_buffer).replace('.', 'p')}_min{str(min_risk).replace('.', 'p')}_max{str(max_risk).replace('.', 'p')}_h{hold}_cap{cap}", "level_set": level_set, "retest_window": retest, "signal_mode": signal_mode, "bias_mode": bias, "displacement": displacement, "cooldown_bars": cooldown, "target_r": target_r, "stop_buffer": stop_buffer, "min_risk": min_risk, "max_risk": max_risk, "max_hold_bars": hold, "max_concurrent_positions": cap}
                                                    row.update({f"full_{k}": v for k, v in m.items()})
                                                    row["target_frequency"] = 8 <= m["trades_per_day"] <= 14
                                                    rows.append(row)
                                                    if row["target_frequency"] and row["full_net_points"] > 0 and (best is None or row["full_net_points"] > best[0]):
                                                        best = (row["full_net_points"], trades.copy())
    summary = pd.DataFrame(rows).sort_values("full_net_points", ascending=False) if rows else pd.DataFrame()
    if summary.empty:
        print("NO_RESULTS")
        return
    summary.to_csv(OUTPUT_DIR / "session_liquidity_rr_sweep_summary.csv", index=False, encoding="utf-8-sig")
    period_report("best_target", best[1] if best else pd.DataFrame())
    summary.head(160).to_html(OUTPUT_DIR / "session_liquidity_rr_sweep_report.html", index=False)
    print(summary.head(30).to_string(index=False), flush=True)


if __name__ == "__main__":
    run()
