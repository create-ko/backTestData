# -*- coding: utf-8 -*-
"""Chronological holdout and three-year walk-forward for daily King Keltner."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_king_keltner_chronological_oos"
CONFIGS = [
    (ma, atr, band)
    for ma in [20, 30, 40, 50, 60, 80, 100, 120]
    for atr in [20, 30, 40, 60, 80]
    for band in [0.5, 0.75, 1.0, 1.25, 1.5]
]
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


research = load_module(
    "research167_for_170", SCRIPT_DIR / "167_daily_king_keltner_2026_selection.py",
)


def select_config(
    cache: dict[tuple[int, int, float], pd.DataFrame],
    train_start: str,
    train_end: str,
    require_positive_subchunks: list[tuple[str, str]] | None = None,
) -> tuple[tuple[int, int, float], dict]:
    candidates = []
    for config, trades in cache.items():
        train = research.period(trades, train_start, train_end)
        summary = research.stats(train)
        if summary["trades"] < 8 or summary["net"] <= 0 or summary["pf"] <= 1.0:
            continue
        subchunk_nets = []
        if require_positive_subchunks:
            subchunk_nets = [
                research.stats(research.period(trades, start, end))["net"]
                for start, end in require_positive_subchunks
            ]
            if not all(value > 0 for value in subchunk_nets):
                continue
        score = summary["net"] - 0.25 * summary["dd"]
        rank = (
            min(subchunk_nets) if subchunk_nets else score,
            summary["pf"], score,
        )
        candidates.append((rank, config, summary))
    if not candidates:
        raise ValueError(f"No eligible config for {train_start} to {train_end}")
    _, config, summary = max(candidates, key=lambda item: item[0])
    return config, summary


def main() -> None:
    frame = research.daily_frame()
    centers = {
        length: frame["typical"].rolling(length, min_periods=length).mean().to_numpy(float)
        for length in sorted({config[0] for config in CONFIGS})
    }
    atrs = {
        length: frame["tr"].rolling(length, min_periods=length).mean().to_numpy(float)
        for length in sorted({config[1] for config in CONFIGS})
    }
    cache = {
        config: research.simulate(frame, centers[config[0]], atrs[config[1]], config[2])
        for config in CONFIGS
    }

    fixed_config, fixed_train = select_config(
        cache, "2010-01-01", "2019-01-01", require_positive_subchunks=SLICES[:3],
    )
    fixed_trades = cache[fixed_config]
    fixed_rows = []
    for start, end in SLICES:
        fixed_rows.append({
            "start": start, "end": end,
            "phase": "train" if end <= "2019-01-01" else "holdout",
            **research.stats(research.period(fixed_trades, start, end)),
        })
    fixed = pd.DataFrame(fixed_rows)
    fixed_holdout = research.stats(research.period(fixed_trades, "2019-01-01", "2026-06-17"))

    walk_rows = []
    walk_trades = []
    for target_i in range(1, len(SLICES)):
        train_start, train_end = SLICES[target_i - 1]
        test_start, test_end = SLICES[target_i]
        config, train_summary = select_config(cache, train_start, train_end)
        test = research.period(cache[config], test_start, test_end).copy()
        test_summary = research.stats(test)
        walk_rows.append({
            "train_start": train_start, "train_end": train_end,
            "test_start": test_start, "test_end": test_end,
            "ma_length": config[0], "atr_length": config[1], "band_multiplier": config[2],
            "train_trades": train_summary["trades"], "train_net": train_summary["net"],
            "train_pf": train_summary["pf"], "test_trades": test_summary["trades"],
            "test_net": test_summary["net"], "test_pf": test_summary["pf"],
            "test_dd": test_summary["dd"],
        })
        test["walk_config"] = f"{config[0]}_{config[1]}_{config[2]}"
        walk_trades.append(test)
    walk = pd.DataFrame(walk_rows)
    combined_walk = pd.concat(walk_trades, ignore_index=True).sort_values("entry_time").reset_index(drop=True)
    combined_walk_stats = research.stats(combined_walk)
    walk_positive = int((walk["test_net"] > 0).sum())
    holdout_positive = int((fixed.loc[fixed["phase"].eq("holdout"), "net"] > 0).sum())

    OUTPUT.mkdir(parents=True, exist_ok=True)
    fixed.round(4).to_csv(OUTPUT / "fixed_selection_chunks.csv", index=False, encoding="utf-8-sig")
    fixed_trades.to_csv(OUTPUT / "fixed_selection_trades.csv", index=False, encoding="utf-8-sig")
    walk.round(4).to_csv(OUTPUT / "walkforward_chunks.csv", index=False, encoding="utf-8-sig")
    combined_walk.to_csv(OUTPUT / "walkforward_trades.csv", index=False, encoding="utf-8-sig")
    report = [
        "# Daily King Keltner Chronological OOS", "",
        "## Fixed chronological holdout", "",
        "The parameter grid is selected using only 2010-2018. Eligibility requires all three training chunks to be profitable.",
        f"Selected config: SMA {fixed_config[0]}, simple TR {fixed_config[1]}, band {fixed_config[2]:.2f}.",
        f"Training: {fixed_train['trades']} trades, net {fixed_train['net']:.2f}, PF {fixed_train['pf']:.4f}.",
        f"Unseen 2019-2026 holdout: {fixed_holdout['trades']} trades, net {fixed_holdout['net']:.2f}, PF {fixed_holdout['pf']:.4f}, DD {fixed_holdout['dd']:.2f}.",
        f"Positive holdout chunks: {holdout_positive}/3.", "",
        "## Three-year walk-forward", "",
        "Each test chunk uses the single best eligible configuration from only the immediately preceding three-year chunk.",
        f"Combined OOS: {combined_walk_stats['trades']} trades, net {combined_walk_stats['net']:.2f}, PF {combined_walk_stats['pf']:.4f}, DD {combined_walk_stats['dd']:.2f}.",
        f"Positive OOS chunks: {walk_positive}/{len(walk)}.", "",
        "No test-period result participates in its parameter selection.",
        "This validates the low-frequency family chronologically, but does not solve the 1-3 entries/day requirement.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("FIXED_CONFIG", fixed_config, "TRAIN", fixed_train, "HOLDOUT", fixed_holdout)
    print(fixed.round(4).to_string(index=False))
    print("WALKFORWARD")
    print(walk.round(4).to_string(index=False))
    print("COMBINED", combined_walk_stats, "POSITIVE", walk_positive, "OF", len(walk))


if __name__ == "__main__":
    main()
