# -*- coding: utf-8 -*-
"""2m BB20 wick -> opposite BB4 pullback, fixed 1:2 RR.

This is a fixed-risk/reward variant of script 103's entry idea.

Default snapshot:
- TEST_START=2026-01-01
- TEST_END=2026-06-17
- STOP_BUFFER_POINTS=0.5
- MAX_HOLD_BARS=20
- MAX_CONCURRENT_POSITIONS=5

The stop is placed beyond the signal-to-entry extreme:
- long: min(low from breakout candle through entry candle) - buffer
- short: max(high from breakout candle through entry candle) + buffer
Target is exactly 2R from entry. Cost is 0.5P round turn.
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
ENTRY_SCRIPT = SCRIPT_DIR / "103_2m_bb20_wick_bb4_grid_concurrent.py"

TEST_START = os.environ.get("TEST_START", "2026-01-01")
TEST_END = os.environ.get("TEST_END", "2026-06-17")
STOP_BUFFER_POINTS = float(os.environ.get("STOP_BUFFER_POINTS", "0.5"))
MAX_HOLD_BARS = int(os.environ.get("MAX_HOLD_BARS", "20"))
MAX_CONCURRENT_POSITIONS = int(os.environ.get("MAX_CONCURRENT_POSITIONS", "5"))
MIN_RISK_POINTS = float(os.environ.get("MIN_RISK_POINTS", "0.8"))
MAX_RISK_POINTS = float(os.environ.get("MAX_RISK_POINTS", "8.0"))
ROUND_TURN_COST_POINTS = float(os.environ.get("ROUND_TURN_COST_POINTS", "0.5"))

PERIOD_LABEL = TEST_START[:10].replace("-", "") + "_" + TEST_END[:10].replace("-", "")
OUTPUT_DIR = ROOT / "result" / ("bb20_wick_bb4_rr2_2m_" + PERIOD_LABEL)


spec = importlib.util.spec_from_file_location("entry103", ENTRY_SCRIPT)
entry103 = importlib.util.module_from_spec(spec)
sys.modules["entry103"] = entry103
assert spec.loader is not None
spec.loader.exec_module(entry103)


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def load_data() -> pd.DataFrame:
    full = quiet_call(entry103.load_full_data)
    start = pd.Timestamp(TEST_START, tz="Asia/Seoul")
    end = pd.Timestamp(TEST_END, tz="Asia/Seoul")
    return full[(full.index >= start) & (full.index < end)].copy()


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


def simulate_rr2(df: pd.DataFrame, entries: pd.DataFrame) -> pd.DataFrame:
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    rows = []

    for _, entry_row in entries.iterrows():
        entry_pos = int(entry_row["entry_pos"])
        breakout_pos = int(entry_row["breakout_pos"])
        direction = str(entry_row["direction"])
        entry_price = float(entry_row["entry_price"])
        if entry_pos >= len(df):
            continue

        if direction == "long":
            stop_price = float(min(low[breakout_pos:entry_pos + 1]) - STOP_BUFFER_POINTS)
            risk = entry_price - stop_price
            target_price = entry_price + 2.0 * risk
        else:
            stop_price = float(max(high[breakout_pos:entry_pos + 1]) + STOP_BUFFER_POINTS)
            risk = stop_price - entry_price
            target_price = entry_price - 2.0 * risk

        if not math.isfinite(risk) or risk < MIN_RISK_POINTS or risk > MAX_RISK_POINTS:
            continue

        end_pos = min(len(df) - 1, entry_pos + MAX_HOLD_BARS)
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
        ts = entry_row["entry_time"]
        rows.append({
            "entry_time": ts,
            "exit_time": idx[exit_pos],
            "direction": direction,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "risk_points": risk,
            "gross_points": gross,
            "net_points": net,
            "r_net": net / risk,
            "exit_reason": exit_reason,
            "year": int(pd.Timestamp(ts).year),
            "month": pd.Timestamp(ts).strftime("%Y-%m"),
            "day": pd.Timestamp(ts).date().isoformat(),
            "session": str(entry_row["session"]),
            "bars_to_fill": int(entry_row["bars_to_fill"]),
            "hold_bars": int(exit_pos - entry_pos + 1),
        })

    trades = pd.DataFrame(rows)
    if trades.empty:
        return trades
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    return apply_concurrency_cap(trades, MAX_CONCURRENT_POSITIONS)


def summarize_group(group: pd.DataFrame, trading_days: int) -> dict:
    pnl = pd.to_numeric(group["net_points"], errors="coerce").fillna(0.0)
    return {
        "trades": int(len(group)),
        "trading_days": int(trading_days),
        "active_days": int(group["day"].nunique()) if len(group) else 0,
        "trades_per_day": float(len(group) / trading_days) if trading_days else 0.0,
        "net_points": float(pnl.sum()),
        "avg_points": float(pnl.mean()) if len(pnl) else 0.0,
        "avg_r_net": float(group["r_net"].mean()) if len(group) else 0.0,
        "profit_factor": profit_factor(pnl),
        "win_rate": float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
        "target_rate": float((group["exit_reason"] == "target_2r").mean() * 100) if len(group) else 0.0,
        "stop_rate": float((group["exit_reason"] == "stop").mean() * 100) if len(group) else 0.0,
        "max_drawdown_points": max_drawdown(pnl),
        "avg_risk": float(group["risk_points"].mean()) if len(group) else 0.0,
        "avg_hold_bars": float(group["hold_bars"].mean()) if len(group) else 0.0,
    }


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def grouped(trades: pd.DataFrame, cols: list[str], trading_days: int) -> pd.DataFrame:
    rows = []
    for key, group in trades.groupby(cols, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        row = dict(zip(cols, key))
        row.update(summarize_group(group, trading_days))
        rows.append(row)
    return round_floats(pd.DataFrame(rows))


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    active_months = set(df.index.strftime("%Y-%m").unique())
    entries = entry103.find_entries(df, active_months)
    trades = simulate_rr2(df, entries)
    if trades.empty:
        raise RuntimeError("No trades generated")

    trading_days = int(pd.Series(df.index.date).nunique())
    overall = round_floats(pd.DataFrame([summarize_group(trades, trading_days)]))
    yearly = grouped(trades, ["year"], trading_days)
    monthly = grouped(trades, ["month"], trading_days)
    exits = grouped(trades, ["exit_reason"], trading_days)

    entries.to_csv(OUTPUT_DIR / "bb20_wick_bb4_rr2_entries.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(OUTPUT_DIR / "bb20_wick_bb4_rr2_trades.csv", index=False, encoding="utf-8-sig")
    overall.to_csv(OUTPUT_DIR / "bb20_wick_bb4_rr2_overall.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "bb20_wick_bb4_rr2_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "bb20_wick_bb4_rr2_monthly.csv", index=False, encoding="utf-8-sig")
    exits.to_csv(OUTPUT_DIR / "bb20_wick_bb4_rr2_exits.csv", index=False, encoding="utf-8-sig")

    print("=== 2M BB20 WICK BB4 RR2 ===")
    print("TEST_START:", TEST_START, "TEST_END:", TEST_END)
    print("STOP_BUFFER_POINTS:", STOP_BUFFER_POINTS, "MAX_HOLD_BARS:", MAX_HOLD_BARS)
    print("MAX_CONCURRENT_POSITIONS:", MAX_CONCURRENT_POSITIONS)
    print(overall.to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
