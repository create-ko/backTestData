# -*- coding: utf-8 -*-
"""Gap-aware daily King Keltner validation with 0.5-point round-trip cost."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_king_keltner_gap_aware"
COST = 0.5


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


channel = load_module("channel87_for_165", SCRIPT_DIR / "87_earnforex_channel_systems.py")


def backtest(
    bars,
    avg_length: int = 40,
    atr_length: int = 40,
    band_multiplier: float = 1.0,
) -> pd.DataFrame:
    trades = []
    open_trade = None
    typical = channel.hlc3_values(bars)
    for i in range(len(bars) - 1):
        next_bar = bars[i + 1]
        if open_trade is not None:
            level = channel.sma_at(typical, i, avg_length)
            if level is None:
                continue
            direction = int(open_trade["direction"])
            if direction == 1 and next_bar.low <= level:
                exit_price = min(float(level), float(next_bar.open))
            elif direction == -1 and next_bar.high >= level:
                exit_price = max(float(level), float(next_bar.open))
            else:
                continue
            gross = (exit_price - open_trade["entry_price"]) * direction
            trades.append({
                **open_trade,
                "exit_epoch": next_bar.epoch,
                "exit_price": exit_price,
                "gross_points": gross,
                "net_points": gross - COST,
                "exit_reason": "ma_stop",
            })
            open_trade = None
            continue

        ma = channel.sma_at(typical, i, avg_length)
        previous_ma = channel.sma_at(typical, i - 1, avg_length)
        atr = channel.avg_true_range_at(bars, i, atr_length)
        if ma is None or previous_ma is None or atr is None or ma == previous_ma:
            continue
        direction = 1 if ma > previous_ma else -1
        stop = float(ma + direction * atr * band_multiplier)
        if direction == 1 and next_bar.high >= stop:
            entry_price = max(stop, float(next_bar.open))
        elif direction == -1 and next_bar.low <= stop:
            entry_price = min(stop, float(next_bar.open))
        else:
            continue
        open_trade = {
            "direction": direction,
            "signal_epoch": bars[i].epoch,
            "entry_epoch": next_bar.epoch,
            "entry_price": entry_price,
            "entry_stop": stop,
        }

    if open_trade is not None:
        final = bars[-1]
        direction = int(open_trade["direction"])
        gross = (float(final.close) - open_trade["entry_price"]) * direction
        trades.append({
            **open_trade,
            "exit_epoch": final.epoch,
            "exit_price": float(final.close),
            "gross_points": gross,
            "net_points": gross - COST,
            "exit_reason": "data_end",
        })
    out = pd.DataFrame(trades)
    out["direction_name"] = out["direction"].map({1: "long", -1: "short"})
    out["entry_time"] = pd.to_datetime(out["entry_epoch"], unit="s", utc=True)
    out["exit_time"] = pd.to_datetime(out["exit_epoch"], unit="s", utc=True)
    out["year"] = out["entry_time"].dt.year
    return out


def summarize(frame: pd.DataFrame) -> dict:
    pnl = frame["net_points"]
    gains = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    equity = pnl.cumsum()
    drawdown = equity.cummax() - equity
    return {
        "trades": len(frame),
        "net_points": float(pnl.sum()),
        "profit_factor": float(gains / losses) if losses else float("inf"),
        "win_rate": float((pnl > 0).mean() * 100),
        "max_drawdown_points": float(drawdown.max()) if len(frame) else 0.0,
    }


def main() -> None:
    source = ROOT / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"
    bars = channel.aggregate_daily(channel.load_bars(str(source)))
    trades = backtest(bars)
    yearly_rows = []
    for year, frame in trades.groupby("year"):
        yearly_rows.append({"year": year, **summarize(frame)})
    yearly = pd.DataFrame(yearly_rows)
    chunk_rows = []
    slices = [
        ("2010-01-01", "2013-01-01"), ("2013-01-01", "2016-01-01"),
        ("2016-01-01", "2019-01-01"), ("2019-01-01", "2022-01-01"),
        ("2022-01-01", "2025-01-01"), ("2025-01-01", "2026-06-17"),
    ]
    for start, end in slices:
        mask = (trades["entry_time"] >= pd.Timestamp(start, tz="UTC")) & (
            trades["entry_time"] < pd.Timestamp(end, tz="UTC")
        )
        chunk_rows.append({"start": start, "end": end, **summarize(trades.loc[mask])})
    chunks = pd.DataFrame(chunk_rows)
    full = summarize(trades)
    positive_years = int((yearly["net_points"] > 0).sum())
    positive_chunks = int((chunks["net_points"] > 0).sum())

    OUTPUT.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUTPUT / "trades.csv", index=False, encoding="utf-8-sig")
    yearly.round(4).to_csv(OUTPUT / "yearly.csv", index=False, encoding="utf-8-sig")
    chunks.round(4).to_csv(OUTPUT / "chunks_3y.csv", index=False, encoding="utf-8-sig")
    report = [
        "# Daily King Keltner Gap-Aware Validation", "",
        "- Daily UTC bars built from XAUUSD 5m data",
        "- Trend: slope of typical-price SMA40",
        "- Entry: next-day stop at SMA40 plus/minus simple TR-average40",
        "- Exit: next-day stop at current SMA40",
        "- Gap rule: adverse next-day open is used when it crosses the stop",
        "- One position at a time; round-trip cost 0.5 points", "",
        f"Full: {full['trades']} trades, net {full['net_points']:.2f}, PF {full['profit_factor']:.4f}, DD {full['max_drawdown_points']:.2f}.",
        f"Positive calendar years: {positive_years}/{len(yearly)}. Positive 3-year chunks: {positive_chunks}/6.",
        f"Average frequency: {full['trades'] / 5125:.4f} trades per trading day.", "",
        "This is the robust low-frequency benchmark; it does not meet the 1-3 entries/day requirement.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("FULL", full)
    print(yearly.round(4).to_string(index=False))
    print(chunks.round(4).to_string(index=False))
    print("POSITIVE_YEARS", positive_years, "POSITIVE_CHUNKS", positive_chunks)


if __name__ == "__main__":
    main()
