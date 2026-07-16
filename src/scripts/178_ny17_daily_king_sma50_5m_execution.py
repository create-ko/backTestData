# -*- coding: utf-8 -*-
"""NY17 daily King Keltner signals executed chronologically on 5m bars."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "ny17_daily_king_sma50_5m_execution"
COST = 0.5
SLICES = [
    ("2010-01-01", "2013-01-01"), ("2013-01-01", "2016-01-01"),
    ("2016-01-01", "2019-01-01"), ("2019-01-01", "2022-01-01"),
    ("2022-01-01", "2025-01-01"), ("2025-01-01", "2026-06-17"),
]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


boundary = load_module(
    "boundary173_for_178", SCRIPT_DIR / "173_daily_king_keltner_boundary_sensitivity.py",
)
research = boundary.research


def simulate_5m(
    execution: pd.DataFrame,
    daily: pd.DataFrame,
    ma_length: int = 50,
    atr_length: int = 40,
    band: float = 1.0,
) -> pd.DataFrame:
    center = daily["typical"].rolling(ma_length, min_periods=ma_length).mean().to_numpy(float)
    atr = daily["tr"].rolling(atr_length, min_periods=atr_length).mean().to_numpy(float)
    daily_time = pd.DatetimeIndex(daily["time"]).tz_convert("Asia/Seoul")
    exec_index = execution.index
    open_ = execution["open"].to_numpy(float)
    high = execution["high"].to_numpy(float)
    low = execution["low"].to_numpy(float)
    close = execution["close"].to_numpy(float)
    rows = []
    position = 0
    entry_price = math.nan
    entry_time = None
    entry_signal_time = None
    entry_level = math.nan
    entry_center = math.nan
    exit_level = math.nan
    same_bar_round_trips = 0

    for session_i in range(1, len(daily) - 1):
        session_start = daily_time[session_i]
        session_end = daily_time[session_i + 1]
        left = int(exec_index.searchsorted(session_start, side="left"))
        right = int(exec_index.searchsorted(session_end, side="left"))
        if left >= right or left >= len(execution):
            continue
        signal_i = session_i - 1
        order_direction = 0
        order_level = math.nan
        signal_center = center[signal_i]
        if position != 0:
            if math.isfinite(signal_center):
                exit_level = float(signal_center)
        elif (
            signal_i > 0 and math.isfinite(signal_center)
            and math.isfinite(center[signal_i - 1]) and math.isfinite(atr[signal_i])
        ):
            if center[signal_i] > center[signal_i - 1]:
                order_direction = 1
            elif center[signal_i] < center[signal_i - 1]:
                order_direction = -1
            if order_direction:
                order_level = float(signal_center + order_direction * atr[signal_i] * band)

        session_entered = False
        for pos in range(left, right):
            if position != 0:
                if position == 1 and low[pos] <= exit_level:
                    price = min(exit_level, float(open_[pos]))
                elif position == -1 and high[pos] >= exit_level:
                    price = max(exit_level, float(open_[pos]))
                else:
                    continue
                gross = (price - entry_price) * position
                rows.append({
                    "signal_time": entry_signal_time,
                    "entry_time": entry_time,
                    "exit_time": exec_index[pos],
                    "direction": "long" if position == 1 else "short",
                    "entry_level": entry_level,
                    "entry_center": entry_center,
                    "entry_price": entry_price,
                    "exit_level": exit_level,
                    "exit_price": price,
                    "gross_points": gross,
                    "net_points": gross - COST,
                    "exit_reason": "sma_stop",
                    "same_bar_exit": False,
                })
                position = 0
                session_entered = True
                continue

            if session_entered or order_direction == 0:
                continue
            hit = high[pos] >= order_level if order_direction == 1 else low[pos] <= order_level
            if not hit:
                continue
            if order_direction == 1:
                fill = max(order_level, float(open_[pos]))
            else:
                fill = min(order_level, float(open_[pos]))
            position = order_direction
            entry_price = float(fill)
            entry_time = exec_index[pos]
            entry_signal_time = daily_time[signal_i]
            entry_level = order_level
            entry_center = float(signal_center)
            exit_level = float(signal_center)
            session_entered = True
            order_direction = 0

            same_bar_stop = low[pos] <= exit_level if position == 1 else high[pos] >= exit_level
            if same_bar_stop:
                price = exit_level
                gross = (price - entry_price) * position
                rows.append({
                    "signal_time": entry_signal_time,
                    "entry_time": entry_time,
                    "exit_time": exec_index[pos],
                    "direction": "long" if position == 1 else "short",
                    "entry_level": entry_level,
                    "entry_center": entry_center,
                    "entry_price": entry_price,
                    "exit_level": exit_level,
                    "exit_price": price,
                    "gross_points": gross,
                    "net_points": gross - COST,
                    "exit_reason": "same_5m_sma_stop",
                    "same_bar_exit": True,
                })
                same_bar_round_trips += 1
                position = 0

    if position != 0:
        price = float(close[-1])
        gross = (price - entry_price) * position
        rows.append({
            "signal_time": entry_signal_time,
            "entry_time": entry_time,
            "exit_time": exec_index[-1],
            "direction": "long" if position == 1 else "short",
            "entry_level": entry_level,
            "entry_center": entry_center,
            "entry_price": entry_price,
            "exit_level": exit_level,
            "exit_price": price,
            "gross_points": gross,
            "net_points": gross - COST,
            "exit_reason": "data_end",
            "same_bar_exit": False,
        })
    out = pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)
    out.attrs["same_bar_round_trips"] = same_bar_round_trips
    return out


def main() -> None:
    execution = boundary.intraday.prepare()
    daily = boundary.aggregate_new_york(execution, 0)
    trades = simulate_5m(execution, daily)
    trades["year"] = trades["entry_time"].dt.year
    full = research.stats(trades)
    chunks = pd.DataFrame([
        {"start": start, "end": end, **research.stats(research.period(trades, start, end))}
        for start, end in SLICES
    ])
    yearly = pd.DataFrame([
        {"year": year, **research.stats(group)} for year, group in trades.groupby("year")
    ])
    daily_reference = pd.read_csv(
        ROOT / "result" / "ny17_daily_king_sma50" / "summary.csv",
    ).iloc[0]
    same_bar = int(trades["same_bar_exit"].sum())
    positive_chunks = int((chunks["net"] > 0).sum())

    OUTPUT.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUTPUT / "trades.csv", index=False, encoding="utf-8-sig")
    chunks.round(4).to_csv(OUTPUT / "chunks_3y.csv", index=False, encoding="utf-8-sig")
    yearly.round(4).to_csv(OUTPUT / "yearly.csv", index=False, encoding="utf-8-sig")
    report = [
        "# NY17 Daily King Keltner SMA50 with 5m Execution", "",
        "- Daily signal and channel: completed NY17 SMA50 / simple TR40",
        "- Entry order: active for the next NY17 trading session only",
        "- SMA exit: active immediately after entry and updated at each NY17 boundary",
        "- Same-5m entry/SMA touches: conservatively treated as entry then stop",
        "- Carried-position gaps through SMA: adverse 5m opening price",
        "- One position, round-trip cost 0.5", "",
        f"5m execution: {full['trades']} trades, net {full['net']:.2f}, PF {full['pf']:.4f}, DD {full['dd']:.2f}.",
        f"Positive chunks: {positive_chunks}/6. Same-5m round trips: {same_bar}.",
        f"Prior daily-OHLC model: {int(daily_reference['trades'])} trades, net {float(daily_reference['net']):.2f}, PF {float(daily_reference['pf']):.4f}.", "",
        "The 5m result supersedes the daily-OHLC result for execution validity.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("FULL", full, "SAME_BAR", same_bar, "POSITIVE_CHUNKS", positive_chunks)
    print(chunks.round(4).to_string(index=False))
    print(yearly.round(4).to_string(index=False))
    print("DAILY_REFERENCE", daily_reference.to_dict())


if __name__ == "__main__":
    main()
