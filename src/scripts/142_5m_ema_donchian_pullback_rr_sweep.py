# -*- coding: utf-8 -*-
"""New 5m trend impulse -> EMA pullback strategy sweep."""
from __future__ import annotations

import importlib.util
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE = SCRIPT_DIR / "100_strategy2_grid_multitimeframe_month_filter.py"
spec = importlib.util.spec_from_file_location("base100_for_142", BASE)
base = importlib.util.module_from_spec(spec)
sys.modules["base100_for_142"] = base
assert spec.loader is not None
spec.loader.exec_module(base)

OUTPUT = ROOT / "result" / "ema_donchian_pullback_rr_sweep"
TIMEFRAME = os.environ.get("TIMEFRAME", "5m")
ROUND_TRIP_COST = 0.5
TRADING_DAYS = 5125


def prepare() -> pd.DataFrame:
    df = base.load_tf(TIMEFRAME).copy()
    df["day"] = df.index.tz_convert("Asia/Seoul").date.astype(str)
    df["bar_range"] = df["high"] - df["low"]
    df["body_ratio"] = (df["close"] - df["open"]).abs() / df["bar_range"].replace(0, np.nan)
    df["atr14"] = df["bar_range"].rolling(14, min_periods=14).mean()
    df["session"] = df["session"].astype(str)
    return df


def entries(df: pd.DataFrame, lookback: int, fast: int, slow: int, body_min: float, pullback_window: int) -> pd.DataFrame:
    x = df.copy()
    x["ema_fast"] = x["close"].ewm(span=fast, adjust=False, min_periods=fast).mean()
    x["ema_slow"] = x["close"].ewm(span=slow, adjust=False, min_periods=slow).mean()
    x["prior_high"] = x["high"].shift(1).rolling(lookback, min_periods=lookback).max()
    x["prior_low"] = x["low"].shift(1).rolling(lookback, min_periods=lookback).min()
    rows = []
    i = max(slow, lookback) + 1
    last_day = None
    while i < len(x) - pullback_window - 2:
        day = x["day"].iloc[i]
        if day != last_day:
            last_day = day
        close = float(x["close"].iloc[i])
        fast_v = float(x["ema_fast"].iloc[i])
        slow_v = float(x["ema_slow"].iloc[i])
        ratio = float(x["body_ratio"].iloc[i])
        long_break = close > float(x["prior_high"].iloc[i]) and fast_v > slow_v and close > fast_v and ratio >= body_min
        short_break = close < float(x["prior_low"].iloc[i]) and fast_v < slow_v and close < fast_v and ratio >= body_min
        if not (long_break or short_break):
            i += 1
            continue
        direction = "long" if long_break else "short"
        found = None
        for j in range(i + 1, min(len(x) - 1, i + pullback_window + 1)):
            if x["day"].iloc[j] != day:
                break
            ema = float(x["ema_fast"].iloc[j])
            if not math.isfinite(ema):
                continue
            touched = float(x["low"].iloc[j]) <= ema if direction == "long" else float(x["high"].iloc[j]) >= ema
            confirmed = float(x["close"].iloc[j]) > ema if direction == "long" else float(x["close"].iloc[j]) < ema
            if touched and confirmed:
                found = j
                break
        if found is None:
            i += 1
            continue
        entry_pos = found + 1
        if entry_pos >= len(x) or x["day"].iloc[entry_pos] != day:
            i += 1
            continue
        rows.append({
            "entry_pos": entry_pos,
            "entry_time": x.index[entry_pos],
            "day": day,
            "session": x["session"].iloc[entry_pos],
            "direction": direction,
            "entry_price": float(x["open"].iloc[entry_pos]),
            "pullback_high": float(x["high"].iloc[found]),
            "pullback_low": float(x["low"].iloc[found]),
            "atr": float(x["atr14"].iloc[found]),
            "breakout_pos": i,
        })
        i = found + 1
    return pd.DataFrame(rows)


def simulate(df: pd.DataFrame, signal: pd.DataFrame, rr: float, atr_stop: float, max_hold: int) -> pd.DataFrame:
    if signal.empty:
        return signal
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    rows = []
    for row in signal.itertuples(index=False):
        pos = int(row.entry_pos)
        risk_atr = float(row.atr) * atr_stop
        if not math.isfinite(risk_atr) or risk_atr <= 0:
            continue
        if row.direction == "long":
            stop = float(row.pullback_low) - risk_atr
            risk = row.entry_price - stop
            target = row.entry_price + rr * risk
        else:
            stop = float(row.pullback_high) + risk_atr
            risk = stop - row.entry_price
            target = row.entry_price - rr * risk
        if risk <= 0 or risk > 20:
            continue
        end = min(len(df) - 1, pos + max_hold)
        exit_pos, exit_price, reason = end, float(close[end]), "time_exit"
        for p in range(pos, end + 1):
            if row.direction == "long":
                if low[p] <= stop:
                    exit_pos, exit_price, reason = p, stop, "stop"
                    break
                if high[p] >= target:
                    exit_pos, exit_price, reason = p, target, "target"
                    break
            else:
                if high[p] >= stop:
                    exit_pos, exit_price, reason = p, stop, "stop"
                    break
                if low[p] <= target:
                    exit_pos, exit_price, reason = p, target, "target"
                    break
        gross = exit_price - row.entry_price if row.direction == "long" else row.entry_price - exit_price
        rows.append({**row._asdict(), "stop_price": stop, "target_price": target, "risk_points": risk, "exit_time": df.index[exit_pos], "exit_reason": reason, "net_points": gross - ROUND_TRIP_COST, "hold_bars": exit_pos - pos + 1})
    return pd.DataFrame(rows)


def cap_daily(trades: pd.DataFrame, cap: int = 3) -> pd.DataFrame:
    if trades.empty:
        return trades
    return trades.sort_values("entry_time").groupby("day", sort=False).head(cap).sort_values("entry_time").reset_index(drop=True)


def summarize(trades: pd.DataFrame) -> dict:
    pnl = pd.to_numeric(trades["net_points"], errors="coerce").fillna(0.0)
    gain = pnl[pnl > 0].sum()
    loss = abs(pnl[pnl < 0].sum())
    eq = pnl.cumsum()
    return {"trades": len(trades), "trades_per_day": len(trades) / TRADING_DAYS, "net_points": pnl.sum(), "profit_factor": gain / loss if loss else 0.0, "win_rate": (pnl > 0).mean() * 100 if len(pnl) else 0.0, "max_drawdown": (eq.cummax() - eq).max() if len(pnl) else 0.0, "target_rate": (trades["exit_reason"] == "target").mean() * 100 if len(trades) else 0.0}


def main() -> None:
    df = prepare()
    quick = os.environ.get("QUICK_SCREEN", "")
    lookbacks = [24] if quick else [12, 24, 48]
    body_mins = [0.50] if quick else [0.35, 0.50]
    rrs = [1.5] if quick else [1.0, 1.5, 2.0]
    atr_stops = [0.5] if quick else [0.2, 0.5]
    rows = []
    best = None
    for lookback in lookbacks:
        for body_min in body_mins:
            signal = entries(df, lookback, 20, 50, body_min, 8)
            for rr in rrs:
                for atr_stop in atr_stops:
                    trades = cap_daily(simulate(df, signal, rr, atr_stop, 24))
                    row = {"lookback": lookback, "body_min": body_min, "rr": rr, "atr_stop": atr_stop}
                    row.update(summarize(trades))
                    rows.append(row)
                    if best is None or (row["profit_factor"], row["net_points"]) > (best["profit_factor"], best["net_points"]):
                        best = {**row, "trades_df": trades}
    summary = pd.DataFrame(rows).sort_values(["profit_factor", "net_points"], ascending=False)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary.round(4).to_csv(OUTPUT / "summary.csv", index=False, encoding="utf-8-sig")
    if best is not None:
        best["trades_df"].to_csv(OUTPUT / "best_trades.csv", index=False, encoding="utf-8-sig")
    print(summary.head(30).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
