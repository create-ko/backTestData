# -*- coding: utf-8 -*-
"""Full daily King Keltner grid using New York 17:00 trading-day bars."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "ny17_daily_king_full_grid"
MA_LENGTHS = [20, 30, 40, 50, 60, 80, 100, 120]
ATR_LENGTHS = [20, 30, 40, 60, 80]
BANDS = [0.5, 0.75, 1.0, 1.25, 1.5]
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
    "boundary173_for_174", SCRIPT_DIR / "173_daily_king_keltner_boundary_sensitivity.py",
)
research = boundary.research


def main() -> None:
    execution = boundary.intraday.prepare()
    frame = boundary.aggregate_new_york(execution, 0)
    centers = {
        length: frame["typical"].rolling(length, min_periods=length).mean().to_numpy(float)
        for length in MA_LENGTHS
    }
    atrs = {
        length: frame["tr"].rolling(length, min_periods=length).mean().to_numpy(float)
        for length in ATR_LENGTHS
    }
    rows = []
    cache = {}
    for ma_length in MA_LENGTHS:
        for atr_length in ATR_LENGTHS:
            for band in BANDS:
                config = (ma_length, atr_length, band)
                trades = research.simulate(frame, centers[ma_length], atrs[atr_length], band)
                cache[config] = trades
                nets = [
                    research.stats(research.period(trades, start, end))["net"]
                    for start, end in SLICES
                ]
                full = research.stats(trades)
                rows.append({
                    "ma_length": ma_length, "atr_length": atr_length, "band": band,
                    "trades": full["trades"], "net_points": full["net"],
                    "profit_factor": full["pf"], "max_drawdown": full["dd"],
                    "train_positive_chunks": sum(value > 0 for value in nets[:3]),
                    "holdout_positive_chunks": sum(value > 0 for value in nets[3:]),
                    "positive_chunks": sum(value > 0 for value in nets),
                    "worst_chunk_net": min(nets),
                    **{f"chunk_{i + 1}_net": value for i, value in enumerate(nets)},
                })
    grid = pd.DataFrame(rows)
    by_ma = grid.groupby("ma_length").agg(
        configs=("ma_length", "size"),
        train_3of3=("train_positive_chunks", lambda values: int((values == 3).sum())),
        holdout_3of3=("holdout_positive_chunks", lambda values: int((values == 3).sum())),
        full_6of6=("positive_chunks", lambda values: int((values == 6).sum())),
        median_pf=("profit_factor", "median"),
        median_worst_chunk=("worst_chunk_net", "median"),
    ).reset_index()

    eligible_lengths = by_ma[by_ma["train_3of3"] == len(ATR_LENGTHS) * len(BANDS)]
    selected_config = None
    selected_summary = None
    selected_chunks = None
    if not eligible_lengths.empty:
        selected_ma = int(eligible_lengths["ma_length"].max())
        selected_config = (selected_ma, 40, 1.0)
        selected = cache[selected_config]
        selected_chunks = grid[
            (grid["ma_length"] == selected_ma)
            & (grid["atr_length"] == 40)
            & (grid["band"] == 1.0)
        ].iloc[0].to_dict()
        selected_summary = research.stats(research.period(selected, "2019-01-01", "2026-06-17"))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    grid.sort_values(["positive_chunks", "profit_factor"], ascending=False).round(4).to_csv(
        OUTPUT / "grid.csv", index=False, encoding="utf-8-sig",
    )
    by_ma.round(4).to_csv(OUTPUT / "by_ma.csv", index=False, encoding="utf-8-sig")
    best = grid.sort_values(["positive_chunks", "worst_chunk_net", "profit_factor"], ascending=False).head(30)
    best.round(4).to_csv(OUTPUT / "top_configs.csv", index=False, encoding="utf-8-sig")
    report = [
        "# NY17 Daily King Keltner Full Grid", "",
        "All 200 configurations use New York 17:00 trading-day bars built from 5m data.", "",
        by_ma.round(4).to_string(index=False), "",
        f"Six-of-six configurations: {int((grid['positive_chunks'] == 6).sum())}/{len(grid)}.",
    ]
    if selected_config is None:
        report.extend(["No MA length had all 25 parameter neighbors positive in all three training chunks."])
    else:
        report.extend([
            f"Training-only robust-length rule selected: SMA {selected_config[0]}, TR {selected_config[1]}, band {selected_config[2]:.2f}.",
            f"Unseen holdout: {selected_summary['trades']} trades, net {selected_summary['net']:.2f}, PF {selected_summary['pf']:.4f}.",
            f"Selected config holdout chunks: {int(selected_chunks['holdout_positive_chunks'])}/3.",
        ])
    report.extend(["", "The legacy UTC partial-bar results are not used in this grid."])
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BY_MA")
    print(by_ma.round(4).to_string(index=False))
    print("SIX_OF_SIX", int((grid["positive_chunks"] == 6).sum()), "OF", len(grid))
    print("TOP")
    print(best.round(4).to_string(index=False))
    print("SELECTED", selected_config, selected_summary, selected_chunks)


if __name__ == "__main__":
    main()
