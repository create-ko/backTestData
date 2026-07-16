# -*- coding: utf-8 -*-
"""Historical robustness check for the top 2026 retest expansion candidates."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_trend_adr_retest_expansion_rr2"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


strategy = load_module("strategy152_for_153", SCRIPT_DIR / "152_daily_trend_adr_retest_expansion_rr2.py")


def main() -> None:
    sweep = pd.read_csv(OUTPUT / "selection_2026_sweep.csv").head(8)
    data_path = ROOT / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"
    bars = strategy.base.load_bars(
        data_path,
        strategy.base.parse_kst("2010-01-01 00:00:00"),
        strategy.base.parse_kst("2026-06-17 00:00:00"),
    )
    sessions = strategy.base.build_session_windows(bars[0].epoch, bars[-1].epoch, 300)
    feature_cache = {}
    rows = []
    for rank, candidate in enumerate(sweep.itertuples(index=False), start=1):
        sma_length = int(candidate.sma_length)
        if sma_length not in feature_cache:
            feature_cache[sma_length] = strategy.hybrid.daily_features(bars, sma_length)
        entries = strategy.find_entries(
            bars, sessions, feature_cache[sma_length], "2010-01-01", strategy.END,
            str(candidate.signal_mode), int(candidate.retest_window), float(candidate.body_min),
            float(candidate.risk_fraction), float(candidate.risk_floor),
        )
        trades = strategy.simulate(bars, entries, int(candidate.max_hold_bars))
        full = strategy.metrics.select_period(trades, "2010-01-01", strategy.END)
        summary = strategy.metrics.summarize("full", "2010-01-01", strategy.END, 5125, full)
        chunk_nets = []
        for start, end, _ in strategy.metrics.SLICES:
            part = strategy.metrics.select_period(trades, start, end)
            chunk_nets.append(float(part["net_points"].sum()))
        rows.append({
            "selection_rank": rank,
            "sma_length": sma_length,
            "signal_mode": candidate.signal_mode,
            "retest_window": int(candidate.retest_window),
            "body_min": float(candidate.body_min),
            "risk_fraction": float(candidate.risk_fraction),
            "max_hold_bars": int(candidate.max_hold_bars),
            "selection_net": float(candidate.net_points),
            "full_trades": int(summary["trades"]),
            "full_net": float(summary["net_points"]),
            "full_pf": float(summary["profit_factor"]),
            "full_max_drawdown": float(summary["max_drawdown_points"]),
            "profitable_chunks": sum(value > 0 for value in chunk_nets),
        })
    result = pd.DataFrame(rows)
    result.round(4).to_csv(OUTPUT / "top8_historical_robustness.csv", index=False, encoding="utf-8-sig")
    positive = int((result["full_net"] > 0).sum())
    shown = result.round(4).astype(str)
    table = [
        "| " + " | ".join(shown.columns) + " |",
        "| " + " | ".join(["---"] * len(shown.columns)) + " |",
    ]
    table.extend("| " + " | ".join(row) + " |" for row in shown.to_numpy())
    report = [
        "# Top-8 Historical Robustness", "",
        f"Full-period profitable candidates: **{positive}/8**.", "",
        "\n".join(table), "",
        "Candidates are ranked only with the 2026 selection window; historical results do not alter the selected parameters.",
    ]
    (OUTPUT / "ROBUSTNESS.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(result.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
