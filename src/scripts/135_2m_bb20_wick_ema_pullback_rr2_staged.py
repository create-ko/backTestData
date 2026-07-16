# -*- coding: utf-8 -*-
"""Staged 2m BB20 wick -> EMA pullback fixed 1:2 RR sweep.

This is a different entry anchor from BB20->BB4: after a BB20 wick extreme,
the order waits for a pullback to a selected EMA.  Only the selected date
range is simulated so 2026 can be screened before longer expansions.
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
OUTPUT_DIR = ROOT / "result" / "bb20_wick_ema_pullback_rr2_staged" / STAGE

spec = importlib.util.spec_from_file_location("base115_for_135", BASE115)
base115 = importlib.util.module_from_spec(spec)
sys.modules["base115_for_135"] = base115
assert spec.loader is not None
spec.loader.exec_module(base115)


def list_int(name, default):
    raw = os.environ.get(name)
    return [int(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def list_float(name, default):
    raw = os.environ.get(name)
    return [float(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def list_str(name, default):
    raw = os.environ.get(name)
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else default


EMA_LENGTHS = list_int("EMA_LENGTHS", [10, 20, 30])
PENDING_BARS_SET = list_int("PENDING_BARS_SET", [10, 20, 30])
BIAS_MODES = list_str("BIAS_MODES", ["none", "price_follow"])
COOLDOWNS = list_int("COOLDOWNS", [0, 3])
STOP_BUFFERS = list_float("STOP_BUFFERS", [0.2, 0.5])
MIN_RISKS = list_float("MIN_RISKS", [0.8])
MAX_RISKS = list_float("MAX_RISKS", [3.0, 5.0])
HOLDS = list_int("HOLDS", [10, 20])
CAPS = list_int("CAPS", [5])


def load_data():
    old_start, old_end = base115.TEST_START, base115.TEST_END
    base115.TEST_START, base115.TEST_END = TEST_START, TEST_END
    try:
        df = base115.load_data()
    finally:
        base115.TEST_START, base115.TEST_END = old_start, old_end
    close = df["close"]
    df["bb20_mid"] = close.rolling(20, min_periods=20).mean()
    df["bb20_std"] = close.rolling(20, min_periods=20).std(ddof=0)
    for n in EMA_LENGTHS:
        df[f"ema{n}"] = close.ewm(span=n, adjust=False, min_periods=n).mean()
    return df


def find_entries(df, ema_length, pending_bars, bias_mode, cooldown):
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    upper = (df["bb20_mid"] + 2.0 * df["bb20_std"]).to_numpy(float)
    lower = (df["bb20_mid"] - 2.0 * df["bb20_std"]).to_numpy(float)
    ema = df[f"ema{ema_length}"].to_numpy(float)
    sid = df["session_id"].to_numpy(int)
    names = df["session_name"].astype(str).to_numpy()
    dates = df["kst_date"].astype(str).to_numpy()
    rows = []
    last = {"long": -10**9, "short": -10**9}
    for signal_pos in range(120, len(df) - pending_bars - 2):
        if not all(math.isfinite(float(x)) for x in (upper[signal_pos], lower[signal_pos], ema[signal_pos])):
            continue
        long_signal = high[signal_pos] > upper[signal_pos]
        short_signal = low[signal_pos] < lower[signal_pos]
        if long_signal == short_signal:
            continue
        direction = "long" if long_signal else "short"
        if signal_pos - last[direction] <= cooldown:
            continue
        limit_price = ema[signal_pos]
        entry_pos = None
        search_end = min(len(df) - 2, signal_pos + pending_bars)
        for pos in range(signal_pos + 1, search_end + 1):
            if (low[pos] <= limit_price if direction == "long" else high[pos] >= limit_price) and base115.entry_time_allowed(idx[pos]):
                entry_pos = pos
                break
        if entry_pos is None:
            continue
        if not base115.bias_allowed(df, entry_pos, direction, bias_mode):
            continue
        ts = idx[entry_pos]
        rows.append({
            "ema_length": ema_length, "pending_bars": pending_bars, "bias_mode": bias_mode, "cooldown_bars": cooldown,
            "direction": direction, "breakout_pos": signal_pos, "retest_pos": entry_pos, "entry_pos": entry_pos,
            "breakout_time": idx[signal_pos], "retest_time": idx[entry_pos], "entry_time": ts,
            "level": float(limit_price), "entry_price": float(limit_price),
            "breakout_high": float(high[signal_pos]), "breakout_low": float(low[signal_pos]),
            "retest_high": float(high[signal_pos]), "retest_low": float(low[signal_pos]),
            "session": str(names[entry_pos]), "session_id": int(sid[entry_pos]),
            "year": int(ts.year), "month": ts.strftime("%Y-%m"), "day": dates[entry_pos],
        })
        last[direction] = signal_pos
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def period_report(prefix, trades):
    if trades.empty:
        return
    trades.to_csv(OUTPUT_DIR / f"{prefix}_trades.csv", index=False, encoding="utf-8-sig")
    for col in ("year", "month"):
        out = trades.groupby(col).agg(trades=("net_points", "size"), net_points=("net_points", "sum"), avg_points=("net_points", "mean"), target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100))).reset_index()
        base115.round_floats(out).to_csv(OUTPUT_DIR / f"{prefix}_{col}.csv", index=False, encoding="utf-8-sig")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    days = int(pd.Series(df.index.date).nunique())
    days26 = int(pd.Series(df[df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")].index.date).nunique())
    rows, best = [], None
    for ema in EMA_LENGTHS:
        for pending in PENDING_BARS_SET:
            for bias in BIAS_MODES:
                for cooldown in COOLDOWNS:
                    entries = find_entries(df, ema, pending, bias, cooldown)
                    if entries.empty:
                        continue
                    for stop_buffer in STOP_BUFFERS:
                        for min_risk in MIN_RISKS:
                            for max_risk in MAX_RISKS:
                                for hold in HOLDS:
                                    for cap in CAPS:
                                        if min_risk >= max_risk:
                                            continue
                                        trades = base115.simulate_rr2(df, entries, "retest", stop_buffer, min_risk, max_risk, hold, cap)
                                        if trades.empty:
                                            continue
                                        t26 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
                                        full = base115.summarize(trades, days)
                                        sample = base115.summarize(t26, days26)
                                        row = {"config_id": f"ema{ema}_pb{pending}_{bias}_cd{cooldown}_sb{str(stop_buffer).replace('.', 'p')}_min{str(min_risk).replace('.', 'p')}_max{str(max_risk).replace('.', 'p')}_h{hold}_cap{cap}", "ema_length": ema, "pending_bars": pending, "bias_mode": bias, "cooldown_bars": cooldown, "stop_buffer": stop_buffer, "min_risk": min_risk, "max_risk": max_risk, "max_hold_bars": hold, "max_concurrent_positions": cap}
                                        row.update({f"full_{k}": v for k, v in full.items()})
                                        row.update({f"sample2026_{k}": v for k, v in sample.items()})
                                        row["sample2026_target_frequency"] = 8 <= sample["trades_per_day"] <= 14
                                        rows.append(row)
                                        if row["sample2026_target_frequency"] and row["sample2026_net_points"] > 0 and (best is None or row["sample2026_net_points"] > best[0]):
                                            best = (row["sample2026_net_points"], trades.copy())
    summary = pd.DataFrame(rows).sort_values("sample2026_net_points", ascending=False) if rows else pd.DataFrame()
    if summary.empty:
        print("NO_RESULTS")
        return
    summary.to_csv(OUTPUT_DIR / "bb20_wick_ema_pullback_rr2_summary.csv", index=False, encoding="utf-8-sig")
    period_report("best_2026_target", best[1] if best else pd.DataFrame())
    summary.head(120).to_html(OUTPUT_DIR / "bb20_wick_ema_pullback_rr2_report.html", index=False)
    print(summary.head(20).to_string(index=False), flush=True)


if __name__ == "__main__":
    run()
