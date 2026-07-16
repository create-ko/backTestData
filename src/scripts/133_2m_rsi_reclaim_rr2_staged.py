# -*- coding: utf-8 -*-
"""Fast staged 2m RSI reclaim fixed 1:2 RR sweep."""
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
OUTPUT_DIR = ROOT / "result" / "rsi_reclaim_rr2_staged" / STAGE

spec = importlib.util.spec_from_file_location("base115_for_133", BASE115)
base115 = importlib.util.module_from_spec(spec)
sys.modules["base115_for_133"] = base115
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


RSI_LENGTHS = ints("RSI_LENGTHS", [2, 5, 14])
OVERSOLDS = floats("OVERSOLDS", [10, 20, 30])
OVERBOUGHTS = floats("OVERBOUGHTS", [70, 80, 90])
REGIMES = strings("REGIMES", ["none", "ema20", "vwap"])
COOLDOWNS = ints("COOLDOWNS", [0, 3])
STOP_BUFFERS = floats("STOP_BUFFERS", [0.2, 0.5])
MIN_RISKS = floats("MIN_RISKS", [0.8])
MAX_RISKS = floats("MAX_RISKS", [3.0, 5.0])
HOLDS = ints("HOLDS", [10, 20, 30])
CAPS = ints("CAPS", [5])


def load_data():
    old_start, old_end = base115.TEST_START, base115.TEST_END
    base115.TEST_START, base115.TEST_END = TEST_START, TEST_END
    try:
        df = base115.load_data()
    finally:
        base115.TEST_START, base115.TEST_END = old_start, old_end
    delta = df["close"].diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi2"] = 100 - 100 / (1 + up / down.replace(0, math.nan))
    for n in RSI_LENGTHS:
        u = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
        d = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
        df[f"rsi{n}"] = 100 - 100 / (1 + u / d.replace(0, math.nan))
    df["ema20"] = df["close"].ewm(span=20, adjust=False, min_periods=20).mean()
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    volume = pd.to_numeric(df.get("volume", pd.Series(1.0, index=df.index)), errors="coerce").fillna(1.0).clip(lower=1.0)
    df["vwap"] = (typical * volume).groupby(df["session_id"]).cumsum() / volume.groupby(df["session_id"]).cumsum()
    return df


def find_entries(df, length, oversold, overbought, regime, cooldown):
    idx = df.index
    rsi = df[f"rsi{length}"].to_numpy(float)
    close = df["close"].to_numpy(float)
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    ema = df["ema20"].to_numpy(float)
    vwap = df["vwap"].to_numpy(float)
    sid = df["session_id"].to_numpy(int)
    names = df["session_name"].astype(str).to_numpy()
    dates = df["kst_date"].astype(str).to_numpy()
    rows = []
    last = {"long": -10**9, "short": -10**9}
    for pos in range(122, len(df) - 2):
        if sid[pos] != sid[pos - 1] or not all(math.isfinite(float(x)) for x in (rsi[pos - 1], rsi[pos], ema[pos], vwap[pos])):
            continue
        long_signal = rsi[pos - 1] <= oversold and rsi[pos] > oversold and close[pos] > open_[pos]
        short_signal = rsi[pos - 1] >= overbought and rsi[pos] < overbought and close[pos] < open_[pos]
        if regime == "ema20":
            long_signal = long_signal and close[pos] > ema[pos]
            short_signal = short_signal and close[pos] < ema[pos]
        elif regime == "vwap":
            long_signal = long_signal and close[pos] > vwap[pos]
            short_signal = short_signal and close[pos] < vwap[pos]
        if long_signal == short_signal:
            continue
        direction = "long" if long_signal else "short"
        if pos - last[direction] <= cooldown:
            continue
        entry_pos = pos + 1
        if not base115.entry_time_allowed(idx[entry_pos]):
            continue
        ts = idx[entry_pos]
        rows.append({
            "rsi_length": length, "oversold": oversold, "overbought": overbought, "regime": regime, "cooldown_bars": cooldown,
            "direction": direction, "breakout_pos": pos, "retest_pos": pos, "entry_pos": entry_pos,
            "breakout_time": idx[pos], "retest_time": idx[pos], "entry_time": ts,
            "level": float(ema[pos]), "entry_price": float(open_[entry_pos]),
            "breakout_high": float(high[pos]), "breakout_low": float(low[pos]),
            "retest_high": float(high[pos]), "retest_low": float(low[pos]),
            "session": str(names[entry_pos]), "session_id": int(sid[entry_pos]),
            "year": int(ts.year), "month": ts.strftime("%Y-%m"), "day": dates[entry_pos],
        })
        last[direction] = pos
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
    for length in RSI_LENGTHS:
        for oversold in OVERSOLDS:
            for overbought in OVERBOUGHTS:
                if oversold >= overbought:
                    continue
                for regime in REGIMES:
                    for cooldown in COOLDOWNS:
                        entries = find_entries(df, length, oversold, overbought, regime, cooldown)
                        if entries.empty:
                            continue
                        for stop_buffer in STOP_BUFFERS:
                            for min_risk in MIN_RISKS:
                                for max_risk in MAX_RISKS:
                                    for hold in HOLDS:
                                        for cap in CAPS:
                                            trades = base115.simulate_rr2(df, entries, "retest", stop_buffer, min_risk, max_risk, hold, cap)
                                            if trades.empty:
                                                continue
                                            t26 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
                                            full = base115.summarize(trades, days)
                                            sample = base115.summarize(t26, days26)
                                            row = {"config_id": f"rsi{length}_os{int(oversold)}_ob{int(overbought)}_{regime}_cd{cooldown}_sb{str(stop_buffer).replace('.', 'p')}_min{str(min_risk).replace('.', 'p')}_max{str(max_risk).replace('.', 'p')}_h{hold}_cap{cap}", "rsi_length": length, "oversold": oversold, "overbought": overbought, "regime": regime, "cooldown_bars": cooldown, "stop_buffer": stop_buffer, "min_risk": min_risk, "max_risk": max_risk, "max_hold_bars": hold, "max_concurrent_positions": cap}
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
    summary.to_csv(OUTPUT_DIR / "rsi_reclaim_rr2_summary.csv", index=False, encoding="utf-8-sig")
    period_report("best_2026_target", best[1] if best else pd.DataFrame())
    summary.head(120).to_html(OUTPUT_DIR / "rsi_reclaim_rr2_report.html", index=False)
    print(summary.head(20).to_string(index=False), flush=True)


if __name__ == "__main__":
    run()
