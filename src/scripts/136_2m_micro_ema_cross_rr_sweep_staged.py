# -*- coding: utf-8 -*-
"""Staged 2m micro EMA cross-continuation sweep with configurable RR.

Long/short signals occur when price reclaims EMA20/30 in the direction of a
slower EMA trend.  The stop uses the recent pullback extreme and target R is
explicitly swept, so the 1:2 requirement can be tested instead of assumed.
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
OUTPUT_DIR = ROOT / "result" / "micro_ema_cross_rr_sweep_staged" / STAGE

spec = importlib.util.spec_from_file_location("base115_for_136", BASE115)
base115 = importlib.util.module_from_spec(spec)
sys.modules["base115_for_136"] = base115
assert spec.loader is not None
spec.loader.exec_module(base115)


def vals(name, default, cast):
    raw = os.environ.get(name)
    return [cast(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


FAST_EMAS = vals("FAST_EMAS", [10, 20, 30], int)
SLOW_EMAS = vals("SLOW_EMAS", [60, 120], int)
PULLBACK_WINDOWS = vals("PULLBACK_WINDOWS", [2, 3, 5], int)
TREND_MODES = vals("TREND_MODES", ["stack", "slope"], str)
TARGET_RS = vals("TARGET_RS", [1.0, 1.25, 1.5, 2.0], float)
COOLDOWNS = vals("COOLDOWNS", [0, 3], int)
STOP_BUFFERS = vals("STOP_BUFFERS", [0.2, 0.5], float)
MIN_RISKS = vals("MIN_RISKS", [0.5, 0.8], float)
MAX_RISKS = vals("MAX_RISKS", [3.0, 5.0], float)
HOLDS = vals("HOLDS", [5, 10, 20], int)
CAPS = vals("CAPS", [5], int)


def load_data():
    old_start, old_end = base115.TEST_START, base115.TEST_END
    base115.TEST_START, base115.TEST_END = TEST_START, TEST_END
    try:
        df = base115.load_data()
    finally:
        base115.TEST_START, base115.TEST_END = old_start, old_end
    for n in sorted(set(FAST_EMAS + SLOW_EMAS)):
        df[f"ema{n}"] = df["close"].ewm(span=n, adjust=False, min_periods=n).mean()
        df[f"ema{n}_slope"] = df[f"ema{n}"] - df[f"ema{n}"].shift(5)
    return df


def find_entries(df, fast, slow, window, trend_mode, cooldown):
    idx = df.index
    close = df["close"].to_numpy(float)
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    ef = df[f"ema{fast}"].to_numpy(float)
    es = df[f"ema{slow}"].to_numpy(float)
    slope = df[f"ema{slow}_slope"].to_numpy(float)
    sid = df["session_id"].to_numpy(int)
    names = df["session_name"].astype(str).to_numpy()
    dates = df["kst_date"].astype(str).to_numpy()
    recent_low = df["low"].rolling(window, min_periods=window).min().to_numpy(float)
    recent_high = df["high"].rolling(window, min_periods=window).max().to_numpy(float)
    rows = []
    last = {"long": -10**9, "short": -10**9}
    for pos in range(max(120, slow, window) + 1, len(df) - 2):
        if sid[pos] != sid[pos - 1] or not all(math.isfinite(float(x)) for x in (ef[pos - 1], ef[pos], es[pos], slope[pos], recent_low[pos], recent_high[pos])):
            continue
        long_cross = close[pos - 1] <= ef[pos - 1] and close[pos] > ef[pos]
        short_cross = close[pos - 1] >= ef[pos - 1] and close[pos] < ef[pos]
        long_trend = ef[pos] > es[pos] and (slope[pos] > 0 if trend_mode == "slope" else True)
        short_trend = ef[pos] < es[pos] and (slope[pos] < 0 if trend_mode == "slope" else True)
        long_signal, short_signal = long_cross and long_trend, short_cross and short_trend
        if long_signal == short_signal:
            continue
        direction = "long" if long_signal else "short"
        if pos - last[direction] <= cooldown or not base115.entry_time_allowed(idx[pos + 1]):
            continue
        entry_pos = pos + 1
        ts = idx[entry_pos]
        rows.append({
            "fast_ema": fast, "slow_ema": slow, "pullback_window": window, "trend_mode": trend_mode, "cooldown_bars": cooldown,
            "direction": direction, "breakout_pos": pos, "retest_pos": pos, "entry_pos": entry_pos,
            "breakout_time": idx[pos], "retest_time": idx[pos], "entry_time": ts,
            "level": float(ef[pos]), "entry_price": float(open_[entry_pos]),
            "breakout_high": float(high[pos]), "breakout_low": float(low[pos]),
            "retest_high": float(recent_high[pos]), "retest_low": float(recent_low[pos]),
            "session": str(names[entry_pos]), "session_id": int(sid[entry_pos]),
            "year": int(ts.year), "month": ts.strftime("%Y-%m"), "day": dates[entry_pos],
        })
        last[direction] = pos
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


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
        stop = (float(item.retest_low) - stop_buffer) if direction == "long" else (float(item.retest_high) + stop_buffer)
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
    for fast in FAST_EMAS:
        for slow in SLOW_EMAS:
            if fast >= slow:
                continue
            for window in PULLBACK_WINDOWS:
                for trend in TREND_MODES:
                    for cooldown in COOLDOWNS:
                        entries = find_entries(df, fast, slow, window, trend, cooldown)
                        if entries.empty:
                            continue
                        for target_r in TARGET_RS:
                            for stop_buffer in STOP_BUFFERS:
                                for min_risk in MIN_RISKS:
                                    for max_risk in MAX_RISKS:
                                        for hold in HOLDS:
                                            for cap in CAPS:
                                                if min_risk >= max_risk:
                                                    continue
                                                trades = simulate(df, entries, target_r, stop_buffer, min_risk, max_risk, hold, cap)
                                                if trades.empty:
                                                    continue
                                                metrics = base115.summarize(trades, days)
                                                row = {"config_id": f"ema{fast}_{slow}_w{window}_{trend}_cd{cooldown}_r{str(target_r).replace('.', 'p')}_sb{str(stop_buffer).replace('.', 'p')}_min{str(min_risk).replace('.', 'p')}_max{str(max_risk).replace('.', 'p')}_h{hold}_cap{cap}", "fast_ema": fast, "slow_ema": slow, "pullback_window": window, "trend_mode": trend, "cooldown_bars": cooldown, "target_r": target_r, "stop_buffer": stop_buffer, "min_risk": min_risk, "max_risk": max_risk, "max_hold_bars": hold, "max_concurrent_positions": cap}
                                                row.update({f"full_{k}": v for k, v in metrics.items()})
                                                row["target_frequency"] = 8 <= metrics["trades_per_day"] <= 14
                                                rows.append(row)
                                                if row["target_frequency"] and row["full_net_points"] > 0 and (best is None or row["full_net_points"] > best[0]):
                                                    best = (row["full_net_points"], trades.copy())
    summary = pd.DataFrame(rows).sort_values("full_net_points", ascending=False) if rows else pd.DataFrame()
    if summary.empty:
        print("NO_RESULTS")
        return
    summary.to_csv(OUTPUT_DIR / "micro_ema_cross_rr_summary.csv", index=False, encoding="utf-8-sig")
    period_report("best_target", best[1] if best else pd.DataFrame())
    summary.head(120).to_html(OUTPUT_DIR / "micro_ema_cross_rr_report.html", index=False)
    print(summary.head(20).to_string(index=False), flush=True)


if __name__ == "__main__":
    run()
