# -*- coding: utf-8 -*-
"""Corrected long-only H1 breakout / 2m SMA120 retest scale-trail test."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "h1_breakout_sma120_retest_corrected"
COST_PER_UNIT = 0.5


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


legacy = load_module(
    "legacy89_for_166", SCRIPT_DIR / "89_strategy1_h1_breakout_120sma_3scale_stop_trail_close.py",
)


def first_entry(data: dict, signal_time: pd.Timestamp) -> tuple[int, float] | None:
    idx = data["idx"]
    left = int(idx.searchsorted(signal_time, side="left"))
    right = int(idx.searchsorted(signal_time + pd.Timedelta(hours=6), side="left"))
    if left >= right:
        return None
    hits = np.flatnonzero(data["low"][left:right] <= data["known_sma"][left:right])
    for offset in hits:
        pos = left + int(offset)
        if math.isfinite(data["known_sma"][pos]) and legacy._entry_time_allowed(idx[pos]):
            return pos, float(data["known_sma"][pos])
    return None


def simulate_trade(data: dict, entry_pos: int, first_level: float) -> dict | None:
    levels = [first_level, first_level - 10.0, first_level - 20.0]
    hard_stop = first_level - 25.0
    filled = [False, False, False]
    fill_prices = []
    fill_times = [pd.NaT, pd.NaT, pd.NaT]
    avg_entry = math.nan
    trail_stop = math.nan
    trail_armed = False
    exit_pos = len(data["idx"]) - 1
    exit_price = float(data["close"][exit_pos])
    reason = "data_end"
    for pos in range(entry_pos, len(data["idx"])):
        open_ = float(data["open"][pos])
        low = float(data["low"][pos])
        close = float(data["close"][pos])
        for level_i, level in enumerate(levels):
            if filled[level_i] or low > level:
                continue
            # Buy limits receive the lower opening price when price gaps through them.
            price = min(level, open_)
            filled[level_i] = True
            fill_prices.append(price)
            fill_times[level_i] = data["idx"][pos]
            avg_entry = sum(fill_prices) / len(fill_prices)
        if not fill_prices:
            continue
        if low <= hard_stop:
            exit_pos = pos
            exit_price = min(hard_stop, open_)
            reason = "hard_stop"
            break
        if trail_armed and low <= trail_stop:
            exit_pos = pos
            exit_price = min(trail_stop, open_)
            reason = "close_trail"
            break
        # A close-confirmed trail becomes active only on the following 2m bar.
        if close >= avg_entry + 5.0:
            next_stop = max(avg_entry, close - 5.0)
            trail_stop = max(trail_stop, next_stop) if trail_armed else next_stop
            trail_armed = True
    if not fill_prices:
        return None
    units = len(fill_prices)
    gross = (exit_price - avg_entry) * units
    return {
        "entry_pos": entry_pos,
        "entry_time": fill_times[0],
        "entry_1_time": fill_times[0],
        "entry_2_time": fill_times[1],
        "entry_3_time": fill_times[2],
        "entry_1_level": levels[0],
        "avg_entry": avg_entry,
        "filled_entries": units,
        "hard_stop": hard_stop,
        "exit_pos": exit_pos,
        "exit_time": data["idx"][exit_pos],
        "exit_price": exit_price,
        "exit_reason": reason,
        "gross_points_total": gross,
        "cost_points_total": COST_PER_UNIT * units,
        "net_points_total": gross - COST_PER_UNIT * units,
    }


def summarize(frame: pd.DataFrame, days: int) -> dict:
    pnl = frame["net_points_total"]
    gains = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    equity = pnl.cumsum()
    return {
        "trades": len(frame),
        "trades_per_day": len(frame) / days,
        "net_points": float(pnl.sum()),
        "profit_factor": float(gains / losses) if losses else float("inf"),
        "win_rate": float((pnl > 0).mean() * 100),
        "max_drawdown_points": float((equity.cummax() - equity).max()) if len(frame) else 0.0,
    }


def main() -> None:
    df10 = legacy.load_entry_tf("10m")
    signals = legacy.make_h1_breakout_signals(df10)
    signals = signals[signals["direction"].eq("long")].sort_values("h1_signal_time")
    df = legacy.load_entry_tf("2m")
    known_sma = df["close"].rolling(120, min_periods=120).mean().shift(1)
    data = {
        "idx": df.index,
        "open": df["open"].to_numpy(float),
        "low": df["low"].to_numpy(float),
        "close": df["close"].to_numpy(float),
        "known_sma": known_sma.to_numpy(float),
    }
    rows = []
    active_exit_pos = -1
    for signal in signals.itertuples(index=False):
        entry = first_entry(data, signal.h1_signal_time)
        if entry is None or entry[0] <= active_exit_pos:
            continue
        trade = simulate_trade(data, entry[0], entry[1])
        if trade is None:
            continue
        trade["signal_time"] = signal.h1_signal_time
        rows.append(trade)
        active_exit_pos = int(trade["exit_pos"])
    trades = pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)
    trades["year"] = trades["entry_time"].dt.year
    slices = [
        ("2010-01-01", "2013-01-01", 939), ("2013-01-01", "2016-01-01", 935),
        ("2016-01-01", "2019-01-01", 931), ("2019-01-01", "2022-01-01", 934),
        ("2022-01-01", "2025-01-01", 932), ("2025-01-01", "2026-06-17", 454),
    ]
    chunk_rows = []
    for start, end, days in slices:
        mask = (trades["entry_time"] >= pd.Timestamp(start, tz="Asia/Seoul")) & (
            trades["entry_time"] < pd.Timestamp(end, tz="Asia/Seoul")
        )
        chunk_rows.append({"start": start, "end": end, **summarize(trades.loc[mask], days)})
    chunks = pd.DataFrame(chunk_rows)
    full = summarize(trades, 5125)
    positive_chunks = int((chunks["net_points"] > 0).sum())

    OUTPUT.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUTPUT / "trades.csv", index=False, encoding="utf-8-sig")
    chunks.round(4).to_csv(OUTPUT / "chunks_3y.csv", index=False, encoding="utf-8-sig")
    report = [
        "# Corrected H1 Breakout / 2m SMA120 Retest", "",
        "- Long-only completed H1 double-Bollinger breakout",
        "- First 2m retest of prior-bar-known SMA120 within six hours",
        "- Three buy-limit units at 10-point spacing; hard stop 5 points below unit 3",
        "- Close-confirmed 5-point trailing stop; one position at a time",
        "- Gap-aware fills and 0.5-point round-trip cost per filled unit", "",
        f"Full: {full['trades']} trades, {full['trades_per_day']:.4f}/day, net {full['net_points']:.2f}, PF {full['profit_factor']:.4f}, DD {full['max_drawdown_points']:.2f}.",
        f"Positive 3-year chunks: {positive_chunks}/6.", "",
        "This corrects same-bar SMA look-ahead and overlapping independent trades in the legacy result.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("FULL", full)
    print(chunks.round(4).to_string(index=False))
    print("POSITIVE_CHUNKS", positive_chunks)


if __name__ == "__main__":
    main()
