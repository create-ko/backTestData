# -*- coding: utf-8 -*-
"""Select the slowest fully stable MA on 2010-2018, then hold out 2019-2026."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_king_keltner_robust_length_holdout"
MA_LENGTHS = [20, 30, 40, 50, 60, 80, 100, 120]
ATR_LENGTHS = [20, 30, 40, 60, 80]
BANDS = [0.5, 0.75, 1.0, 1.25, 1.5]
TRAIN_CHUNKS = [
    ("2010-01-01", "2013-01-01"),
    ("2013-01-01", "2016-01-01"),
    ("2016-01-01", "2019-01-01"),
]
HOLDOUT_CHUNKS = [
    ("2019-01-01", "2022-01-01"),
    ("2022-01-01", "2025-01-01"),
    ("2025-01-01", "2026-06-17"),
]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


research = load_module(
    "research167_for_172", SCRIPT_DIR / "167_daily_king_keltner_2026_selection.py",
)


def main() -> None:
    frame = research.daily_frame()
    centers = {
        length: frame["typical"].rolling(length, min_periods=length).mean().to_numpy(float)
        for length in MA_LENGTHS
    }
    atrs = {
        length: frame["tr"].rolling(length, min_periods=length).mean().to_numpy(float)
        for length in ATR_LENGTHS
    }
    cache = {}
    rows = []
    for ma_length in MA_LENGTHS:
        stable = 0
        worst_values = []
        for atr_length in ATR_LENGTHS:
            for band in BANDS:
                trades = research.simulate(frame, centers[ma_length], atrs[atr_length], band)
                cache[(ma_length, atr_length, band)] = trades
                nets = [
                    research.stats(research.period(trades, start, end))["net"]
                    for start, end in TRAIN_CHUNKS
                ]
                if all(value > 0 for value in nets):
                    stable += 1
                worst_values.append(min(nets))
        rows.append({
            "ma_length": ma_length,
            "stable_configs": stable,
            "total_configs": len(ATR_LENGTHS) * len(BANDS),
            "stable_rate": stable / (len(ATR_LENGTHS) * len(BANDS)) * 100,
            "median_worst_train_chunk": float(pd.Series(worst_values).median()),
            "minimum_worst_train_chunk": min(worst_values),
        })
    stability = pd.DataFrame(rows)
    fully_stable = stability[stability["stable_configs"] == stability["total_configs"]]
    if fully_stable.empty:
        raise ValueError("No fully stable MA length in training")
    # With fixed cost, prefer the slowest fully stable trend length to reduce turnover.
    selected_ma = int(fully_stable["ma_length"].max())
    selected_config = (selected_ma, 40, 1.0)
    selected = cache[selected_config]
    train = research.period(selected, "2010-01-01", "2019-01-01")
    holdout = research.period(selected, "2019-01-01", "2026-06-17")
    train_stats = research.stats(train)
    holdout_stats = research.stats(holdout)
    chunk_rows = []
    for start, end in TRAIN_CHUNKS + HOLDOUT_CHUNKS:
        phase = "train" if end <= "2019-01-01" else "holdout"
        chunk_rows.append({
            "start": start, "end": end, "phase": phase,
            **research.stats(research.period(selected, start, end)),
        })
    chunks = pd.DataFrame(chunk_rows)
    holdout_positive = int((chunks.loc[chunks["phase"].eq("holdout"), "net"] > 0).sum())

    costs = []
    for cost in [0.5, 1.0, 2.0]:
        adjusted = holdout.copy()
        adjusted["net_points"] = adjusted["gross_points"] - cost
        summary = research.stats(adjusted)
        chunk_nets = []
        for start, end in HOLDOUT_CHUNKS:
            chunk_nets.append(research.stats(research.period(adjusted, start, end))["net"])
        costs.append({
            "round_trip_cost": cost, **summary,
            "positive_holdout_chunks": sum(value > 0 for value in chunk_nets),
            "worst_holdout_chunk": min(chunk_nets),
        })
    cost_table = pd.DataFrame(costs)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    stability.round(4).to_csv(OUTPUT / "training_stability_by_ma.csv", index=False, encoding="utf-8-sig")
    chunks.round(4).to_csv(OUTPUT / "selected_chunks.csv", index=False, encoding="utf-8-sig")
    selected.to_csv(OUTPUT / "selected_trades.csv", index=False, encoding="utf-8-sig")
    cost_table.round(4).to_csv(OUTPUT / "holdout_cost_sensitivity.csv", index=False, encoding="utf-8-sig")
    report = [
        "# Daily King Keltner Robust-Length Holdout", "",
        "Selection data: 2010-2018 only.",
        "For each MA length, all 25 combinations of TR length and band width are tested across three training chunks.",
        "Eligible MA lengths require 25/25 combinations to be profitable in every training chunk.",
        "The slowest eligible length is selected to minimize turnover under fixed trading cost; TR40 and band 1.0 are central defaults.", "",
        f"Selected config: SMA {selected_config[0]}, simple TR {selected_config[1]}, band {selected_config[2]:.2f}.",
        f"Training: {train_stats['trades']} trades, net {train_stats['net']:.2f}, PF {train_stats['pf']:.4f}.",
        f"Unseen 2019-2026 holdout: {holdout_stats['trades']} trades, net {holdout_stats['net']:.2f}, PF {holdout_stats['pf']:.4f}, DD {holdout_stats['dd']:.2f}.",
        f"Positive holdout chunks: {holdout_positive}/3.",
        f"Holdout frequency: {holdout_stats['trades'] / (934 + 932 + 454):.4f} trades per trading day.", "",
        "The holdout does not participate in parameter selection.",
        "Caveat: this robustness selection rule was formulated during the current full-history research process, so only future data can provide pristine prospective confirmation.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(stability.round(4).to_string(index=False))
    print("SELECTED", selected_config, "TRAIN", train_stats, "HOLDOUT", holdout_stats)
    print(chunks.round(4).to_string(index=False))
    print(cost_table.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
