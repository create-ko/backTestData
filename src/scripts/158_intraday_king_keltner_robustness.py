# -*- coding: utf-8 -*-
"""Historical robustness of top 2026 intraday King Keltner RR2 candidates."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "intraday_king_keltner_rr2"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


strategy = load_module("strategy157_for_158", SCRIPT_DIR / "157_intraday_king_keltner_rr2.py")


def markdown_table(df: pd.DataFrame) -> str:
    shown = df.round(4).astype(str)
    lines = [
        "| " + " | ".join(shown.columns) + " |",
        "| " + " | ".join(["---"] * len(shown.columns)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in shown.to_numpy())
    return "\n".join(lines)


def main() -> None:
    top = pd.read_csv(OUTPUT / "selection_2026_sweep.csv").head(10)
    df = strategy.prepare()
    signal_cache = {tf: strategy.resample_signal_bars(df, tf) for tf in top["timeframe"].unique()}
    entry_cache = {}
    rows = []
    for rank, candidate in enumerate(top.itertuples(index=False), start=1):
        key = (candidate.timeframe, int(candidate.ma_length), int(candidate.atr_length), float(candidate.band_mult))
        if key not in entry_cache:
            entry_cache[key] = strategy.make_entries(
                df, signal_cache[key[0]], key[0], key[1], key[2], key[3],
                strategy.START, strategy.END,
            )
        trades = strategy.simulate(df, entry_cache[key], float(candidate.risk_mult), int(candidate.max_hold_bars))
        full = strategy.metrics.select_period(trades, strategy.START, strategy.END)
        summary = strategy.metrics.summarize("full", strategy.START, strategy.END, 5125, full)
        chunks = []
        for start, end, _ in strategy.metrics.SLICES:
            part = strategy.metrics.select_period(trades, start, end)
            chunks.append(float(part["net_points"].sum()))
        rows.append({
            "selection_rank": rank,
            "timeframe": candidate.timeframe,
            "ma_length": int(candidate.ma_length),
            "atr_length": int(candidate.atr_length),
            "band_mult": float(candidate.band_mult),
            "risk_mult": float(candidate.risk_mult),
            "max_hold_bars": int(candidate.max_hold_bars),
            "full_trades": int(summary["trades"]),
            "full_net": float(summary["net_points"]),
            "full_pf": float(summary["profit_factor"]),
            "full_max_drawdown": float(summary["max_drawdown_points"]),
            "profitable_chunks": sum(value > 0 for value in chunks),
        })
    result = pd.DataFrame(rows)
    result.round(4).to_csv(OUTPUT / "top10_historical_robustness.csv", index=False, encoding="utf-8-sig")
    positive = int((result["full_net"] > 0).sum())
    report = [
        "# Top-10 Historical Robustness", "",
        f"Full-period profitable candidates: **{positive}/10**.", "",
        markdown_table(result), "",
        "Candidates are ranked on 2026 only; historical outcomes do not change the selected rule.",
    ]
    (OUTPUT / "ROBUSTNESS.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(result.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
