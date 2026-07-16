# -*- coding: utf-8 -*-
"""Detailed NY17 validation for the robust SMA50 daily King Keltner family."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "ny17_daily_king_sma50"
MA_LENGTH = 50
ATR_LENGTH = 40
BAND = 1.0
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
    "boundary173_for_175", SCRIPT_DIR / "173_daily_king_keltner_boundary_sensitivity.py",
)
research = boundary.research


def run_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict, pd.DataFrame, pd.DataFrame]:
    center = frame["typical"].rolling(MA_LENGTH, min_periods=MA_LENGTH).mean().to_numpy(float)
    atr = frame["tr"].rolling(ATR_LENGTH, min_periods=ATR_LENGTH).mean().to_numpy(float)
    trades = research.simulate(frame, center, atr, BAND)
    trades["year"] = trades["entry_time"].dt.year
    full = research.stats(trades)
    chunks = pd.DataFrame([
        {"start": start, "end": end, **research.stats(research.period(trades, start, end))}
        for start, end in SLICES
    ])
    yearly = pd.DataFrame([
        {"year": year, **research.stats(group)} for year, group in trades.groupby("year")
    ])
    return trades, full, chunks, yearly


def main() -> None:
    execution = boundary.intraday.prepare()
    frames = {
        "holiday_partial_kept": boundary.aggregate_new_york(execution, 0),
        "under100_removed": boundary.aggregate_new_york(execution, 100),
    }
    summaries = []
    primary_trades = None
    primary_chunks = None
    primary_yearly = None
    for name, frame in frames.items():
        trades, full, chunks, yearly = run_frame(frame)
        summaries.append({
            "variant": name, "daily_bars": len(frame), **full,
            "positive_chunks": int((chunks["net"] > 0).sum()),
            "worst_chunk_net": float(chunks["net"].min()),
            "positive_years": int((yearly["net"] > 0).sum()),
        })
        trades.to_csv(OUTPUT / f"trades_{name}.csv", index=False, encoding="utf-8-sig") if OUTPUT.exists() else None
        if name == "holiday_partial_kept":
            primary_trades, primary_chunks, primary_yearly = trades, chunks, yearly
    assert primary_trades is not None and primary_chunks is not None and primary_yearly is not None

    neighbor_rows = []
    for name, frame in frames.items():
        center = frame["typical"].rolling(MA_LENGTH, min_periods=MA_LENGTH).mean().to_numpy(float)
        for atr_length in [20, 30, 40, 60, 80]:
            atr = frame["tr"].rolling(atr_length, min_periods=atr_length).mean().to_numpy(float)
            for band in [0.5, 0.75, 1.0, 1.25, 1.5]:
                trades = research.simulate(frame, center, atr, band)
                nets = [
                    research.stats(research.period(trades, start, end))["net"]
                    for start, end in SLICES
                ]
                summary = research.stats(trades)
                neighbor_rows.append({
                    "variant": name, "atr_length": atr_length, "band": band,
                    "trades": summary["trades"], "net": summary["net"], "pf": summary["pf"],
                    "positive_chunks": sum(value > 0 for value in nets),
                    "worst_chunk_net": min(nets),
                })
    neighbors = pd.DataFrame(neighbor_rows)
    neighbor_summary = neighbors.groupby("variant").agg(
        configs=("variant", "size"),
        six_chunk_configs=("positive_chunks", lambda values: int((values == 6).sum())),
        pf_min=("pf", "min"), pf_max=("pf", "max"),
        minimum_worst_chunk=("worst_chunk_net", "min"),
    ).reset_index()

    costs = []
    for cost in [0.5, 1.0, 2.0]:
        adjusted = primary_trades.copy()
        adjusted["net_points"] = adjusted["gross_points"] - cost
        summary = research.stats(adjusted)
        nets = [
            research.stats(research.period(adjusted, start, end))["net"]
            for start, end in SLICES
        ]
        costs.append({
            "round_trip_cost": cost, **summary,
            "positive_chunks": sum(value > 0 for value in nets),
            "worst_chunk_net": min(nets),
        })
    cost_table = pd.DataFrame(costs)
    holdout = research.stats(research.period(primary_trades, "2019-01-01", "2026-06-17"))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        trades, _, _, _ = run_frame(frame)
        trades.to_csv(OUTPUT / f"trades_{name}.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(summaries).round(4).to_csv(OUTPUT / "summary.csv", index=False, encoding="utf-8-sig")
    primary_chunks.round(4).to_csv(OUTPUT / "chunks_3y.csv", index=False, encoding="utf-8-sig")
    primary_yearly.round(4).to_csv(OUTPUT / "yearly.csv", index=False, encoding="utf-8-sig")
    neighbors.round(4).to_csv(OUTPUT / "parameter_neighbors.csv", index=False, encoding="utf-8-sig")
    neighbor_summary.round(4).to_csv(OUTPUT / "neighbor_summary.csv", index=False, encoding="utf-8-sig")
    cost_table.round(4).to_csv(OUTPUT / "cost_sensitivity.csv", index=False, encoding="utf-8-sig")
    primary = summaries[0]
    report = [
        "# NY17 Daily King Keltner SMA50", "",
        "- Trading day: New York 17:00 to next New York 17:00, DST aware",
        "- Trend: completed HLC3 SMA50 slope",
        "- Entry: next trading-day stop at SMA50 plus/minus simple TR40",
        "- Exit: next trading-day stop at latest completed SMA50",
        "- Gap-aware fills, one position, round-trip cost 0.5", "",
        f"Full: {primary['trades']} trades, net {primary['net']:.2f}, PF {primary['pf']:.4f}, DD {primary['dd']:.2f}.",
        f"Positive chunks: {primary['positive_chunks']}/6; positive years: {primary['positive_years']}/{len(primary_yearly)}.",
        f"Unseen 2019-2026 holdout: {holdout['trades']} trades, net {holdout['net']:.2f}, PF {holdout['pf']:.4f}, DD {holdout['dd']:.2f}.",
        f"Frequency: {primary['trades'] / 5125:.4f} trades per trading day.", "",
        "Training-only selection: on 2010-2018, SMA50 was the slowest MA length whose 25/25 TR/band neighbors were positive in all three training chunks.",
        "Both holiday-partial handling variants retained 25/25 profitable six-chunk neighbors.", "",
        "Decision: robust low-frequency swing research candidate on proper NY17 bars.",
        "It still fails the original 1-3 entries/day requirement and requires prospective data before live deployment.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(pd.DataFrame(summaries).round(4).to_string(index=False))
    print(primary_chunks.round(4).to_string(index=False))
    print(primary_yearly.round(4).to_string(index=False))
    print(neighbor_summary.round(4).to_string(index=False))
    print(cost_table.round(4).to_string(index=False))
    print("HOLDOUT", holdout)


if __name__ == "__main__":
    main()
