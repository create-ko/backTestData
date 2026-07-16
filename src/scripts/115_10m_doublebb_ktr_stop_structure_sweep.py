# -*- coding: utf-8 -*-
"""Compare 3/4/5-entry stop structures using the same 10m Double-BB setup."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
BASE_PATH = SCRIPT_DIR / "114_10m_doublebb_ktr_six_grid.py"
MAX_ENTRY_VARIANTS = tuple(int(value) for value in os.getenv("MAX_ENTRY_VARIANTS", "3,4,5").split(","))


def load_base():
    spec = importlib.util.spec_from_file_location("doublebb_ktr_grid", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load %s" % BASE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    base = load_base()
    df10, df1, _ = base.load_market_data()
    print("Loaded once: 10m=%s, 1m=%s" % (len(df10), len(df1)), flush=True)
    summaries = []

    for max_entries in MAX_ENTRY_VARIANTS:
        base.MAX_ENTRIES = max_entries
        print("Running max_entries=%s" % max_entries, flush=True)
        trades = pd.concat(
            [base.simulate_entry_type(df10, df1, entry_type) for entry_type in base.ENTRY_TYPES],
            ignore_index=True,
        )
        summary = base.summarize(trades)
        output_dir = ROOT / "result" / (
            "strategy_10m_doublebb_ktr_grid%s_%s_%s"
            % (max_entries, base.TEST_START[:10].replace("-", ""), base.TEST_END[:10].replace("-", ""))
        )
        base.write_report(output_dir, summary, trades)
        summaries.append(summary)
        print(summary.round(3).to_string(index=False), flush=True)

    comparison = pd.concat(summaries, ignore_index=True)
    comparison_path = ROOT / "result" / (
        "strategy_10m_doublebb_ktr_stop_structure_%s_comparison.csv" % base.GRID_UNIT_MODE
    )
    comparison.round(3).to_csv(comparison_path, index=False, encoding="utf-8-sig")
    print("Saved comparison: %s" % comparison_path, flush=True)


if __name__ == "__main__":
    main()
