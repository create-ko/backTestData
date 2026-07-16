# -*- coding: utf-8 -*-
"""Detailed validation for the exploratory SMA60 daily King Keltner candidate."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_king_keltner_sma60"
SWEEP = ROOT / "result" / "daily_king_keltner_2026_selection" / "sweep.csv"
MA_LENGTH = 60
ATR_LENGTH = 40
BAND = 1.0


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


research = load_module(
    "research167_for_168", SCRIPT_DIR / "167_daily_king_keltner_2026_selection.py",
)


def main() -> None:
    frame = research.daily_frame()
    center = frame["typical"].rolling(MA_LENGTH, min_periods=MA_LENGTH).mean().to_numpy(float)
    atr = frame["tr"].rolling(ATR_LENGTH, min_periods=ATR_LENGTH).mean().to_numpy(float)
    trades = research.simulate(frame, center, atr, BAND)
    trades["year"] = trades["entry_time"].dt.year
    trades["month"] = trades["entry_time"].dt.strftime("%Y-%m")

    selected = research.period(trades, research.SELECTION_START, research.END)
    selected_stats = research.stats(selected)
    chunk_rows = []
    for start, end in research.SLICES:
        chunk = research.period(trades, start, end)
        chunk_rows.append({"start": start, "end": end, **research.stats(chunk)})
    chunks = pd.DataFrame(chunk_rows)
    yearly_rows = []
    for year, group in trades.groupby("year"):
        yearly_rows.append({"year": year, **research.stats(group)})
    yearly = pd.DataFrame(yearly_rows)
    direction_rows = []
    for direction, group in trades.groupby("direction"):
        direction_rows.append({"direction": direction, **research.stats(group)})
    directions = pd.DataFrame(direction_rows)

    cost_rows = []
    for cost in [0.5, 1.0, 2.0, 5.0]:
        adjusted = trades.copy()
        adjusted["net_points"] = adjusted["gross_points"] - cost
        summary = research.stats(adjusted)
        adjusted_chunks = [
            research.stats(research.period(adjusted, start, end))["net"]
            for start, end in research.SLICES
        ]
        cost_rows.append({
            "round_trip_cost": cost, **summary,
            "positive_chunks": sum(value > 0 for value in adjusted_chunks),
            "worst_chunk_net": min(adjusted_chunks),
        })
    costs = pd.DataFrame(cost_rows)

    sweep = pd.read_csv(SWEEP)
    ma60 = sweep[sweep["ma_length"].eq(MA_LENGTH)].copy()
    neighborhood = {
        "configs": len(ma60),
        "six_chunk_configs": int((ma60["positive_chunks"] == 6).sum()),
        "min_full_pf": float(ma60["full_pf"].min()),
        "max_full_pf": float(ma60["full_pf"].max()),
        "min_worst_chunk": float(ma60["worst_chunk_net"].min()),
    }
    full = research.stats(trades)
    positive_years = int((yearly["net"] > 0).sum())
    positive_chunks = int((chunks["net"] > 0).sum())

    OUTPUT.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUTPUT / "trades.csv", index=False, encoding="utf-8-sig")
    chunks.round(4).to_csv(OUTPUT / "chunks_3y.csv", index=False, encoding="utf-8-sig")
    yearly.round(4).to_csv(OUTPUT / "yearly.csv", index=False, encoding="utf-8-sig")
    directions.round(4).to_csv(OUTPUT / "directions.csv", index=False, encoding="utf-8-sig")
    costs.round(4).to_csv(OUTPUT / "cost_sensitivity.csv", index=False, encoding="utf-8-sig")
    ma60.round(4).to_csv(OUTPUT / "parameter_neighborhood.csv", index=False, encoding="utf-8-sig")
    report = [
        "# Daily King Keltner SMA60 Exploratory Candidate", "",
        "- Daily UTC XAUUSD bars",
        "- Trend: completed HLC3 SMA60 slope",
        "- Entry: next-day stop at SMA60 plus/minus simple TR-average40",
        "- Exit: next-day stop at the latest completed SMA60",
        "- Gap-aware fills, one position, 0.5-point round-trip cost", "",
        f"2026 selection window: {selected_stats['trades']} trades, net {selected_stats['net']:.2f}, PF {selected_stats['pf']:.4f}.",
        f"Full: {full['trades']} trades, net {full['net']:.2f}, PF {full['pf']:.4f}, DD {full['dd']:.2f}.",
        f"Positive years: {positive_years}/{len(yearly)}; positive 3-year chunks: {positive_chunks}/6.",
        f"Frequency: {full['trades'] / 5125:.4f} trades per trading day.", "",
        f"SMA60 neighborhood: {neighborhood['six_chunk_configs']}/{neighborhood['configs']} ATR-length/band combinations were positive in all chunks.",
        f"Neighborhood full PF range: {neighborhood['min_full_pf']:.4f}-{neighborhood['max_full_pf']:.4f}.",
        f"Worst result among every SMA60 config's weakest chunk: {neighborhood['min_worst_chunk']:.2f} points.", "",
        "Decision: strong low-frequency research candidate, but not a clean 2026-selected result because 2026 contains only three trades.",
        "It also fails the requested 1-3 entries/day requirement and needs genuinely future data before live confirmation.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("SELECTION_2026", selected_stats)
    print("FULL", full)
    print(chunks.round(4).to_string(index=False))
    print(yearly.round(4).to_string(index=False))
    print(costs.round(4).to_string(index=False))
    print("NEIGHBORHOOD", neighborhood)


if __name__ == "__main__":
    main()
