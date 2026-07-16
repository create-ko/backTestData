# -*- coding: utf-8 -*-
"""USDJPY KST Asian-range breakout with a fixed 1:2 reward/risk ratio.

Rules (all timestamps are Asia/Seoul):
1. Build the high/low of the 08:00-12:00 range from completed 1-minute bars.
2. From 12:00 through 17:59, take only the first 1-minute close outside it.
3. Enter at the next 1-minute open.  Long uses the range low as stop; short
   uses the range high.  Target is exactly 2R.  There is at most one trade/day.
4. Resolve stop/target on subsequent 1-minute bars.  If both are touched in
   a bar, the stop wins (conservative intrabar assumption).  Close any open
   trade at the final available bar of the KST day.

The input is Dukascopy MID data. ROUND_TURN_COST_JPY is deliberately exposed:
MID does not contain executable bid/ask prices, so a live test must use the
broker's own spread and slippage.  The default 0.010 JPY is one pip round turn.
"""
from __future__ import annotations

import glob
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_GLOB = str(ROOT / "data" / "usdjpy_1m_2010-01-01_*.csv")
OUT_DIR = ROOT / "result" / "usdjpy_asia_range_rr2_1m"
ROUND_TURN_COST_JPY = float(os.environ.get("ROUND_TURN_COST_JPY", "0.010"))

RANGE_START = 8 * 60
RANGE_END = 12 * 60
ENTRY_START = RANGE_END
ENTRY_END = 18 * 60


def load_data() -> pd.DataFrame:
    files = sorted(glob.glob(DATA_GLOB))
    if not files:
        raise FileNotFoundError("USDJPY 1m CSV not found: " + DATA_GLOB)
    path = Path(files[-1])
    df = pd.read_csv(path, usecols=["time", "open", "high", "low", "close"])
    ts = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("Asia/Seoul")
    df["timestamp"] = ts
    df["day"] = ts.dt.date
    df["minute"] = ts.dt.hour * 60 + ts.dt.minute
    df.attrs["source"] = str(path)
    return df


def first_breakout(signal: pd.DataFrame, range_high: float, range_low: float) -> tuple[str, int] | None:
    above = signal.index[signal["close"] > range_high]
    below = signal.index[signal["close"] < range_low]
    if len(above) == 0 and len(below) == 0:
        return None
    if len(above) and (len(below) == 0 or above[0] < below[0]):
        return "long", int(above[0])
    return "short", int(below[0])


def simulate_day(day: pd.DataFrame) -> dict | None:
    day = day.reset_index(drop=True)
    setup = day[(day["minute"] >= RANGE_START) & (day["minute"] < RANGE_END)]
    signal = day[(day["minute"] >= ENTRY_START) & (day["minute"] < ENTRY_END)]
    # Avoid days with a long data outage in the range/session.
    if len(setup) < 220 or len(signal) < 30:
        return None
    range_high = float(setup["high"].max())
    range_low = float(setup["low"].min())
    found = first_breakout(signal, range_high, range_low)
    if found is None:
        return None
    direction, signal_pos = found
    entry_pos = signal_pos + 1
    if entry_pos >= len(day):
        return None
    entry = float(day.at[entry_pos, "open"])
    stop = range_low if direction == "long" else range_high
    risk = abs(entry - stop)
    if not math.isfinite(risk) or risk <= 0:
        return None
    target = entry + 2.0 * risk if direction == "long" else entry - 2.0 * risk
    future = day.iloc[entry_pos:]
    exit_pos = len(day) - 1
    exit_price = float(day.at[exit_pos, "close"])
    exit_reason = "day_close"
    for pos, bar in future.iterrows():
        if direction == "long":
            hit_stop = float(bar["low"]) <= stop
            hit_target = float(bar["high"]) >= target
        else:
            hit_stop = float(bar["high"]) >= stop
            hit_target = float(bar["low"]) <= target
        # The ordering inside an OHLC minute is unknowable; stop-first prevents
        # a free favorable path when both levels occur in that minute.
        if hit_stop:
            exit_pos, exit_price, exit_reason = pos, stop, "stop"
            break
        if hit_target:
            exit_pos, exit_price, exit_reason = pos, target, "target_2r"
            break
    gross_jpy = exit_price - entry if direction == "long" else entry - exit_price
    net_jpy = gross_jpy - ROUND_TURN_COST_JPY
    return {
        "day": str(day.at[0, "day"]),
        "signal_time": day.at[signal_pos, "timestamp"],
        "entry_time": day.at[entry_pos, "timestamp"],
        "exit_time": day.at[exit_pos, "timestamp"],
        "direction": direction,
        "range_high": range_high,
        "range_low": range_low,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "risk_jpy": risk,
        "gross_jpy": gross_jpy,
        "net_jpy": net_jpy,
        "gross_r": gross_jpy / risk,
        "net_r": net_jpy / risk,
        "exit_reason": exit_reason,
    }


def profit_factor(values: pd.Series) -> float:
    gain = float(values[values > 0].sum())
    loss = abs(float(values[values < 0].sum()))
    return gain / loss if loss else float("inf")


def summary(trades: pd.DataFrame, market_days: int) -> dict:
    values = trades["net_r"]
    equity = values.cumsum()
    drawdown = equity.cummax() - equity
    return {
        "trades": int(len(trades)),
        "market_days": int(market_days),
        "trades_per_market_day": float(len(trades) / market_days) if market_days else 0.0,
        "average_gross_r": float(trades["gross_r"].mean()),
        "average_net_r": float(values.mean()),
        "total_net_r": float(values.sum()),
        "net_r_profit_factor": profit_factor(values),
        "net_r_win_rate": float((values > 0).mean()),
        "target_rate": float((trades["exit_reason"] == "target_2r").mean()),
        "stop_rate": float((trades["exit_reason"] == "stop").mean()),
        "average_risk_jpy": float(trades["risk_jpy"].mean()),
        "median_risk_jpy": float(trades["risk_jpy"].median()),
        "max_drawdown_r": float(drawdown.max()),
    }


def run() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    market_days = int(data["day"].nunique())
    rows = [result for _, day in data.groupby("day", sort=False) if (result := simulate_day(day)) is not None]
    trades = pd.DataFrame(rows)
    if trades.empty:
        raise RuntimeError("No trades generated")
    for col in ["signal_time", "entry_time", "exit_time"]:
        trades[col] = pd.to_datetime(trades[col])
    trades["year"] = trades["entry_time"].dt.year
    trades["period"] = np.select(
        [trades["year"] <= 2021, trades["year"] <= 2024],
        ["development_2010_2021", "holdout_2022_2024"],
        default="recent_2025_2026H1",
    )
    period_rows = []
    for period, group in trades.groupby("period", sort=False):
        period_days = int(data[data["timestamp"].dt.year.isin(group["year"].unique())]["day"].nunique())
        period_rows.append({"period": period, **summary(group, period_days)})
    yearly_rows = []
    for year, group in trades.groupby("year", sort=True):
        period_days = int(data[data["timestamp"].dt.year == year]["day"].nunique())
        yearly_rows.append({"year": int(year), **summary(group, period_days)})
    overall = {"source": data.attrs["source"], "round_turn_cost_jpy": ROUND_TURN_COST_JPY, **summary(trades, market_days)}
    trades.to_csv(OUT_DIR / "trades.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(period_rows).to_csv(OUT_DIR / "period_summary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(yearly_rows).to_csv(OUT_DIR / "yearly_summary.csv", index=False, encoding="utf-8-sig")
    (OUT_DIR / "summary.json").write_text(json.dumps(overall, indent=2), encoding="utf-8")
    print("USDJPY Asia range RR2")
    print("source", data.attrs["source"])
    print("cost", ROUND_TURN_COST_JPY)
    print(pd.DataFrame([overall]).drop(columns=["source"]).round(4).to_string(index=False))
    print(pd.DataFrame(period_rows).round(4).to_string(index=False))
    print("wrote", OUT_DIR)


if __name__ == "__main__":
    run()
