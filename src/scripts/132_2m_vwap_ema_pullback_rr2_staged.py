# -*- coding: utf-8 -*-
"""Fast staged 2m session-VWAP/EMA pullback fixed 1:2 RR sweep.

The setup follows an intraday directional regime and buys/sells a shallow
EMA pullback that closes back with the trend.  Session VWAP uses the CFD's
available volume field as a tick-volume proxy; it is not exchange VWAP.
Signals are vectorized, and only the selected date range is simulated.
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
OUTPUT_DIR = ROOT / "result" / "vwap_ema_pullback_rr2_staged" / STAGE

spec = importlib.util.spec_from_file_location("base115_for_132", BASE115)
base115 = importlib.util.module_from_spec(spec)
sys.modules["base115_for_132"] = base115
assert spec.loader is not None
spec.loader.exec_module(base115)


def ints(name: str, default: list[int]) -> list[int]:
    raw = os.environ.get(name)
    return [int(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def floats(name: str, default: list[float]) -> list[float]:
    raw = os.environ.get(name)
    return [float(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def strings(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else default


FAST_EMAS = ints("FAST_EMAS", [20, 30])
SLOW_EMAS = ints("SLOW_EMAS", [60, 120])
PULLBACK_WINDOWS = ints("PULLBACK_WINDOWS", [3, 5])
TOUCH_BUFFERS = floats("TOUCH_BUFFERS", [0.2, 0.5])
BODY_MINS = floats("BODY_MINS", [0.2, 0.35])
REGIME_MODES = strings("REGIME_MODES", ["vwap_ema", "ema_slope"])
COOLDOWNS = ints("COOLDOWNS", [0, 3])
STOP_BUFFERS = floats("STOP_BUFFERS", [0.2])
MIN_RISKS = floats("MIN_RISKS", [0.8])
MAX_RISKS = floats("MAX_RISKS", [3.0, 5.0])
HOLDS = ints("HOLDS", [10, 20])
CAPS = ints("CAPS", [5])


def load_data() -> pd.DataFrame:
    old_start, old_end = base115.TEST_START, base115.TEST_END
    base115.TEST_START, base115.TEST_END = TEST_START, TEST_END
    try:
        df = base115.load_data()
    finally:
        base115.TEST_START, base115.TEST_END = old_start, old_end
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    volume = pd.to_numeric(df.get("volume", pd.Series(1.0, index=df.index)), errors="coerce").fillna(1.0).clip(lower=1.0)
    pv = typical * volume
    df["session_vwap"] = pv.groupby(df["session_id"]).cumsum() / volume.groupby(df["session_id"]).cumsum()
    for n in sorted(set(FAST_EMAS + SLOW_EMAS)):
        df[f"ema{n}"] = df["close"].ewm(span=n, adjust=False, min_periods=n).mean()
        df[f"ema{n}_slope"] = df[f"ema{n}"] - df[f"ema{n}"].shift(5)
    df["body_ratio"] = df["body_ratio"].replace([math.inf, -math.inf], math.nan)
    return df


def find_entries(df: pd.DataFrame, fast: int, slow: int, window: int, touch: float, body_min: float, regime: str, cooldown: int) -> pd.DataFrame:
    idx = df.index
    close = df["close"].to_numpy(float)
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    body = df["body_ratio"].to_numpy(float)
    vwap = df["session_vwap"].to_numpy(float)
    ef = df[f"ema{fast}"].to_numpy(float)
    es = df[f"ema{slow}"].to_numpy(float)
    slope = df[f"ema{slow}_slope"].to_numpy(float)
    sid = df["session_id"].to_numpy(int)
    sessions = df["session_name"].astype(str).to_numpy()
    dates = df["kst_date"].astype(str).to_numpy()
    roll_low = df["low"].rolling(window, min_periods=window).min().to_numpy(float)
    roll_high = df["high"].rolling(window, min_periods=window).max().to_numpy(float)
    rows = []
    last = {"long": -10**9, "short": -10**9}
    for pos in range(max(120, slow, window) + 1, len(df) - 2):
        if sid[pos] != sid[max(0, pos - window + 1)]:
            continue
        if not all(math.isfinite(float(x)) for x in (close[pos], body[pos], vwap[pos], ef[pos], es[pos], slope[pos], roll_low[pos], roll_high[pos])):
            continue
        common = body[pos] >= body_min
        long_regime = close[pos] > ef[pos] > es[pos] and slope[pos] > 0
        short_regime = close[pos] < ef[pos] < es[pos] and slope[pos] < 0
        if regime == "vwap_ema":
            long_regime = long_regime and close[pos] > vwap[pos]
            short_regime = short_regime and close[pos] < vwap[pos]
        elif regime != "ema_slope":
            raise ValueError("unknown regime")
        long_signal = long_regime and common and low[pos] <= ef[pos] + touch and close[pos] > ef[pos] and close[pos] > open_[pos]
        short_signal = short_regime and common and high[pos] >= ef[pos] - touch and close[pos] < ef[pos] and close[pos] < open_[pos]
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
            "fast_ema": fast, "slow_ema": slow, "pullback_window": window, "touch_buffer": touch,
            "body_min": body_min, "regime_mode": regime, "cooldown_bars": cooldown,
            "direction": direction, "breakout_pos": pos, "retest_pos": pos, "entry_pos": entry_pos,
            "breakout_time": idx[pos], "retest_time": idx[pos], "entry_time": ts,
            "level": float(ef[pos]), "entry_price": float(open_[entry_pos]),
            "breakout_high": float(high[pos]), "breakout_low": float(low[pos]),
            "retest_high": float(roll_high[pos]), "retest_low": float(roll_low[pos]),
            "session": str(sessions[entry_pos]), "session_id": int(sid[entry_pos]),
            "year": int(ts.year), "month": ts.strftime("%Y-%m"), "day": dates[entry_pos],
        })
        last[direction] = pos
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def report_period(prefix: str, trades: pd.DataFrame) -> None:
    if trades.empty:
        return
    trades.to_csv(OUTPUT_DIR / f"{prefix}_trades.csv", index=False, encoding="utf-8-sig")
    for col in ("year", "month"):
        grouped = trades.groupby(col).agg(trades=("net_points", "size"), net_points=("net_points", "sum"), avg_points=("net_points", "mean"), target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100))).reset_index()
        base115.round_floats(grouped).to_csv(OUTPUT_DIR / f"{prefix}_{col}.csv", index=False, encoding="utf-8-sig")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    days = int(pd.Series(df.index.date).nunique())
    days26 = int(pd.Series(df[df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")].index.date).nunique())
    rows = []
    best = None
    for fast in FAST_EMAS:
        for slow in SLOW_EMAS:
            if fast >= slow:
                continue
            for window in PULLBACK_WINDOWS:
                for touch in TOUCH_BUFFERS:
                    for body_min in BODY_MINS:
                        for regime in REGIME_MODES:
                            for cooldown in COOLDOWNS:
                                entries = find_entries(df, fast, slow, window, touch, body_min, regime, cooldown)
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
                                                    row = {"config_id": f"ema{fast}_{slow}_w{window}_tb{str(touch).replace('.', 'p')}_b{str(body_min).replace('.', 'p')}_{regime}_cd{cooldown}_sb{str(stop_buffer).replace('.', 'p')}_min{str(min_risk).replace('.', 'p')}_max{str(max_risk).replace('.', 'p')}_h{hold}_cap{cap}", "fast_ema": fast, "slow_ema": slow, "pullback_window": window, "touch_buffer": touch, "body_min": body_min, "regime_mode": regime, "cooldown_bars": cooldown, "stop_buffer": stop_buffer, "min_risk": min_risk, "max_risk": max_risk, "max_hold_bars": hold, "max_concurrent_positions": cap}
                                                    row.update({f"full_{k}": v for k, v in full.items()})
                                                    row.update({f"sample2026_{k}": v for k, v in sample.items()})
                                                    row["full_target_frequency"] = 8 <= full["trades_per_day"] <= 14
                                                    row["sample2026_target_frequency"] = 8 <= sample["trades_per_day"] <= 14
                                                    rows.append(row)
                                                    if row["sample2026_target_frequency"] and row["sample2026_net_points"] > 0 and (best is None or row["sample2026_net_points"] > best[0]):
                                                        best = (row["sample2026_net_points"], trades.copy())
    summary = pd.DataFrame(rows).sort_values("sample2026_net_points", ascending=False) if rows else pd.DataFrame()
    if summary.empty:
        print("NO_RESULTS")
        return
    summary.to_csv(OUTPUT_DIR / "vwap_ema_pullback_rr2_summary.csv", index=False, encoding="utf-8-sig")
    report_period("best_2026_target", best[1] if best else pd.DataFrame())
    summary.head(120).to_html(OUTPUT_DIR / "vwap_ema_pullback_rr2_report.html", index=False)
    print(summary.head(20).to_string(index=False), flush=True)


if __name__ == "__main__":
    run()
