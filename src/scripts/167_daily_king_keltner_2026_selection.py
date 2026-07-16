# -*- coding: utf-8 -*-
"""Select a gap-aware daily King Keltner config on 2026, then freeze it."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_king_keltner_2026_selection"
COST = 0.5
SELECTION_START = pd.Timestamp("2026-01-01", tz="UTC")
END = pd.Timestamp("2026-06-17", tz="UTC")
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


base = load_module("base165_for_167", SCRIPT_DIR / "165_daily_king_keltner_gap_aware.py")
channel = base.channel


def daily_frame() -> pd.DataFrame:
    source = ROOT / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"
    bars = channel.aggregate_daily(channel.load_bars(str(source)))
    frame = pd.DataFrame({
        "epoch": [bar.epoch for bar in bars],
        "open": [bar.open for bar in bars],
        "high": [bar.high for bar in bars],
        "low": [bar.low for bar in bars],
        "close": [bar.close for bar in bars],
    })
    frame["time"] = pd.to_datetime(frame["epoch"], unit="s", utc=True)
    frame["typical"] = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    previous_close = frame["close"].shift(1)
    frame["tr"] = pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - previous_close).abs(),
        (frame["low"] - previous_close).abs(),
    ], axis=1).max(axis=1)
    return frame


def simulate(frame: pd.DataFrame, center: np.ndarray, atr: np.ndarray, band: float) -> pd.DataFrame:
    open_ = frame["open"].to_numpy(float)
    high = frame["high"].to_numpy(float)
    low = frame["low"].to_numpy(float)
    close = frame["close"].to_numpy(float)
    times = frame["time"].tolist()
    rows = []
    position = 0
    entry_price = math.nan
    entry_time = None
    for i in range(len(frame) - 1):
        if not math.isfinite(center[i]):
            continue
        next_i = i + 1
        if position != 0:
            level = center[i]
            if position == 1 and low[next_i] <= level:
                exit_price = min(level, open_[next_i])
            elif position == -1 and high[next_i] >= level:
                exit_price = max(level, open_[next_i])
            else:
                continue
            gross = (exit_price - entry_price) * position
            rows.append({
                "entry_time": entry_time, "exit_time": times[next_i],
                "direction": "long" if position == 1 else "short",
                "entry_price": entry_price, "exit_price": exit_price,
                "gross_points": gross, "net_points": gross - COST,
                "exit_reason": "ma_stop",
            })
            position = 0
            continue
        if not math.isfinite(atr[i]) or i == 0 or not math.isfinite(center[i - 1]):
            continue
        direction = 1 if center[i] > center[i - 1] else (-1 if center[i] < center[i - 1] else 0)
        if direction == 0:
            continue
        stop = center[i] + direction * atr[i] * band
        if direction == 1 and high[next_i] >= stop:
            fill = max(stop, open_[next_i])
        elif direction == -1 and low[next_i] <= stop:
            fill = min(stop, open_[next_i])
        else:
            continue
        position = direction
        entry_price = float(fill)
        entry_time = times[next_i]
    if position != 0:
        gross = (close[-1] - entry_price) * position
        rows.append({
            "entry_time": entry_time, "exit_time": times[-1],
            "direction": "long" if position == 1 else "short",
            "entry_price": entry_price, "exit_price": close[-1],
            "gross_points": gross, "net_points": gross - COST,
            "exit_reason": "data_end",
        })
    return pd.DataFrame(rows)


def stats(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0, "net": 0.0, "pf": 0.0, "dd": 0.0, "win_rate": 0.0}
    pnl = trades["net_points"]
    gain = pnl[pnl > 0].sum()
    loss = abs(pnl[pnl < 0].sum())
    equity = pnl.cumsum()
    return {
        "trades": len(trades), "net": float(pnl.sum()),
        "pf": float(gain / loss) if loss else math.inf,
        "dd": float((equity.cummax() - equity).max()),
        "win_rate": float((pnl > 0).mean() * 100),
    }


def period(trades: pd.DataFrame, start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DataFrame:
    start_ts = pd.Timestamp(start) if isinstance(start, pd.Timestamp) else pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end) if isinstance(end, pd.Timestamp) else pd.Timestamp(end, tz="UTC")
    return trades[(trades["entry_time"] >= start_ts) & (trades["entry_time"] < end_ts)]


def main() -> None:
    frame = daily_frame()
    ma_lengths = [20, 30, 40, 50, 60, 80, 100, 120]
    atr_lengths = [20, 30, 40, 60, 80]
    centers = {
        length: frame["typical"].rolling(length, min_periods=length).mean().to_numpy(float)
        for length in ma_lengths
    }
    atrs = {
        length: frame["tr"].rolling(length, min_periods=length).mean().to_numpy(float)
        for length in atr_lengths
    }
    rows = []
    trade_cache = {}
    best = None
    for ma_length in ma_lengths:
        for atr_length in atr_lengths:
            for band in [0.5, 0.75, 1.0, 1.25, 1.5]:
                trades = simulate(frame, centers[ma_length], atrs[atr_length], band)
                trade_cache[(ma_length, atr_length, band)] = trades
                selected = period(trades, SELECTION_START, END)
                selected_stats = stats(selected)
                months = selected.assign(month=selected["entry_time"].dt.strftime("%Y-%m")).groupby("month")["net_points"].sum()
                chunk_nets = []
                for start, end in SLICES:
                    chunk_nets.append(stats(period(trades, start, end))["net"])
                full_stats = stats(trades)
                row = {
                    "ma_length": ma_length, "atr_length": atr_length, "band_multiplier": band,
                    "selection_trades": selected_stats["trades"],
                    "selection_active_months": len(months),
                    "selection_positive_month_rate": float((months > 0).mean() * 100) if len(months) else 0.0,
                    "selection_net": selected_stats["net"], "selection_pf": selected_stats["pf"],
                    "selection_dd": selected_stats["dd"],
                    "full_trades": full_stats["trades"], "full_net": full_stats["net"],
                    "full_pf": full_stats["pf"], "full_dd": full_stats["dd"],
                    "positive_chunks": sum(value > 0 for value in chunk_nets),
                    "worst_chunk_net": min(chunk_nets),
                    **{f"chunk_{i + 1}_net": value for i, value in enumerate(chunk_nets)},
                }
                row["selection_score"] = row["selection_net"] - 0.25 * row["selection_dd"]
                rows.append(row)
                eligible = (
                    row["selection_trades"] >= 5 and row["selection_active_months"] >= 3
                    and row["selection_net"] > 0 and row["selection_pf"] > 1.0
                )
                if eligible:
                    rank = (
                        row["selection_positive_month_rate"], row["selection_score"], row["selection_pf"],
                    )
                    if best is None or rank > (
                        best["selection_positive_month_rate"], best["selection_score"], best["selection_pf"],
                    ):
                        best = row.copy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep = pd.DataFrame(rows).sort_values(
        ["selection_positive_month_rate", "selection_score"], ascending=False,
    )
    sweep.round(4).to_csv(OUTPUT / "sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        raise ValueError("No eligible 2026 configuration")
    key = (int(best["ma_length"]), int(best["atr_length"]), float(best["band_multiplier"]))
    chosen = trade_cache[key]
    chosen.to_csv(OUTPUT / "selected_trades.csv", index=False, encoding="utf-8-sig")
    robust_count = int((sweep["positive_chunks"] == 6).sum())
    neighbors = sweep[sweep["positive_chunks"] == 6].sort_values("full_pf", ascending=False)
    neighbors.head(30).round(4).to_csv(OUTPUT / "six_chunk_configs.csv", index=False, encoding="utf-8-sig")
    report = [
        "# Daily King Keltner 2026 Selection", "",
        "Selection uses only 2026 trades: at least five trades, at least three active months, positive net and PF above 1.",
        "Historical chunks are diagnostic only and do not participate in the selected-config rank.", "",
        f"Selected: SMA {key[0]}, simple TR average {key[1]}, band {key[2]:.2f} ATR.",
        f"2026: {best['selection_trades']} trades, net {best['selection_net']:.2f}, PF {best['selection_pf']:.4f}.",
        f"Full: {best['full_trades']} trades, net {best['full_net']:.2f}, PF {best['full_pf']:.4f}, DD {best['full_dd']:.2f}.",
        f"Selected-config positive chunks: {int(best['positive_chunks'])}/6; worst chunk {best['worst_chunk_net']:.2f}.",
        f"Parameter-grid configs positive in all six chunks: {robust_count}/{len(sweep)}.",
        f"Frequency: {best['full_trades'] / 5125:.4f} trades per trading day.", "",
        "This daily family cannot satisfy 1-3 entries/day, even if its long-history stability passes.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("SELECTED", best)
    print("SIX_CHUNK_CONFIGS", robust_count, "OF", len(sweep))
    print(neighbors.head(20).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
