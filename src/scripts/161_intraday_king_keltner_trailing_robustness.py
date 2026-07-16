# -*- coding: utf-8 -*-
"""Full-history robustness check for diverse top-2026 trailing Keltner configs."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
INPUT = ROOT / "result" / "intraday_king_keltner_trailing" / "selection_2026_sweep.csv"
OUTPUT = ROOT / "result" / "intraday_king_keltner_trailing"
START = "2010-01-01"
END = "2026-06-17"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


trail = load_module("trail160_for_161", SCRIPT_DIR / "160_intraday_king_keltner_trailing.py")
strategy = trail.strategy
metrics = trail.metrics


def markdown_table(frame: pd.DataFrame) -> str:
    shown = frame.round(4).astype(str)
    lines = [
        "| " + " | ".join(shown.columns) + " |",
        "| " + " | ".join(["---"] * len(shown.columns)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in shown.to_numpy().tolist())
    return "\n".join(lines)


def main() -> None:
    if "--report-only" in sys.argv:
        result = pd.read_csv(OUTPUT / "robustness_top10.csv")
        write_report(result)
        print(result.round(4).to_string(index=False))
        return
    sweep = pd.read_csv(INPUT)
    eligible = sweep[
        sweep["frequency_pass"].astype(str).str.lower().eq("true")
        & (sweep["net_points"] > 0)
        & (sweep["profit_factor"] > 1.0)
    ].copy()
    structural = ["timeframe", "ma_length", "atr_length", "band_mult", "risk_mult"]
    candidates = eligible.drop_duplicates(structural).head(10).reset_index(drop=True)

    df = strategy.prepare()
    signal_cache = {
        tf: strategy.resample_signal_bars(df, tf)
        for tf in sorted(candidates["timeframe"].unique())
    }
    center_cache = {}
    rows = []
    for rank, config in candidates.iterrows():
        tf = str(config["timeframe"])
        ma_length = int(config["ma_length"])
        center_key = (tf, ma_length)
        if center_key not in center_cache:
            center_cache[center_key] = trail.completed_center(signal_cache[tf], df.index, ma_length)
        entries = strategy.make_entries(
            df, signal_cache[tf], tf, ma_length, int(config["atr_length"]),
            float(config["band_mult"]), START, END,
        )
        entries = trail.restrict_entry_hours(entries)
        trades = trail.simulate(
            df, entries, center_cache[center_key], float(config["risk_mult"]),
            int(config["max_hold_bars"]),
        )
        trail.audit_trades(trades)
        full = metrics.select_period(trades, START, END)
        chunk_metrics = []
        for start, end, days in metrics.SLICES:
            chunk = metrics.select_period(trades, start, end)
            chunk_metrics.append(metrics.summarize("chunk", start, end, days, chunk))
        full_summary = metrics.summarize("full", START, END, 5125, full)
        row = {
            "selection_rank": rank + 1,
            **{key: config[key] for key in structural + ["max_hold_bars"]},
            "selection_net_points": config["net_points"],
            "selection_profit_factor": config["profit_factor"],
            "full_trades": full_summary["trades"],
            "full_trades_per_day": full_summary["trades_per_trading_day"],
            "full_net_points": full_summary["net_points"],
            "full_profit_factor": full_summary["profit_factor"],
            "full_max_drawdown": full_summary["max_drawdown_points"],
            "profitable_chunks": sum(item["performance_pass"] for item in chunk_metrics),
            "worst_chunk_net": min(item["net_points"] for item in chunk_metrics),
            "pre_2025_net": sum(item["net_points"] for item in chunk_metrics[:5]),
        }
        rows.append(row)
        print("DONE", rank + 1, tf, ma_length, row["full_net_points"], row["profitable_chunks"])

    result = pd.DataFrame(rows)
    result.round(4).to_csv(OUTPUT / "robustness_top10.csv", index=False, encoding="utf-8-sig")
    write_report(result)
    robust = int(((result["profitable_chunks"] == 6) & (result["full_profit_factor"] > 1.0)).sum())
    positive_pre_2025 = int((result["pre_2025_net"] > 0).sum())
    print(result.round(4).to_string(index=False))
    print("ROBUST", robust, "PRE2025_POSITIVE", positive_pre_2025)


def write_report(result: pd.DataFrame) -> None:
    robust = int(((result["profitable_chunks"] == 6) & (result["full_profit_factor"] > 1.0)).sum())
    positive_pre_2025 = int((result["pre_2025_net"] > 0).sum())
    lines = [
        "# Trailing Keltner Robustness", "",
        "Top 10 structurally distinct 2026 configurations were frozen and run on 2010-2026.", "",
        f"- Six-of-six profitable chunks: **{robust}/10**",
        f"- Positive combined result before 2025: **{positive_pre_2025}/10**",
        "- This is a robustness diagnostic; historical results were not used to re-select parameters.", "",
        markdown_table(result),
    ]
    (OUTPUT / "ROBUSTNESS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
