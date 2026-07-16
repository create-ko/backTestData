# -*- coding: utf-8 -*-
"""Robustness checks for the selected daily-trend ADR session strategy."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_trend_adr_session_rr2"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


strategy = load_module("strategy149_for_150", SCRIPT_DIR / "149_daily_trend_adr_session_rr2.py")
metrics = load_module("metrics144_for_150", SCRIPT_DIR / "144_bb20_rr2_daily2_validation.py")

CONFIGS = [
    ("selected", 120, "trend", 0.50, 0.8, 1440, 10),
    ("sma60_r50_h1440", 60, "trend", 0.50, 0.8, 1440, 10),
    ("sma120_r50_h720", 120, "trend", 0.50, 0.8, 720, 10),
    ("sma60_r30_h720", 60, "trend", 0.30, 0.8, 720, 5),
    ("sma120_r30_h720", 120, "trend", 0.30, 0.8, 720, 10),
    ("sma20_fade_r30_h1440", 20, "fade", 0.30, 0.8, 1440, 10),
]


def pnl_metrics(pnl: pd.Series) -> dict:
    return {
        "net_points": pnl.sum(),
        "profit_factor": metrics.profit_factor(pnl),
        "max_drawdown_points": metrics.max_drawdown(pnl),
    }


def main() -> None:
    df = strategy.base.load_data()
    rows = []
    selected_trades = None
    for name, sma, mode, fraction, floor, hold, cap in CONFIGS:
        daily = strategy.build_daily_features(df, sma)
        entries = strategy.make_entries(df, daily, mode, fraction, floor)
        trades = strategy.base.simulate(df, entries, hold, concurrency_cap=cap)
        full = metrics.select_period(trades, "2010-01-01", "2026-06-17")
        full_summary = metrics.summarize("full", "2010-01-01", "2026-06-17", 5125, full)
        chunk_passes = 0
        chunk_net = []
        for start, end, days in metrics.SLICES:
            chunk = metrics.select_period(trades, start, end)
            summary = metrics.summarize("chunk", start, end, days, chunk)
            chunk_passes += int(summary["performance_pass"])
            chunk_net.append(summary["net_points"])
        rows.append({
            "config": name,
            "sma_length": sma,
            "direction_mode": mode,
            "risk_fraction": fraction,
            "max_hold_bars": hold,
            "concurrency_cap": cap,
            "trades_per_day": full_summary["trades_per_trading_day"],
            "net_points": full_summary["net_points"],
            "profit_factor": full_summary["profit_factor"],
            "max_drawdown_points": full_summary["max_drawdown_points"],
            "positive_chunks": chunk_passes,
            "min_chunk_net": min(chunk_net),
            "full_pass": full_summary["passed"],
        })
        if name == "selected":
            selected_trades = full.copy()

    robustness = pd.DataFrame(rows)
    robustness.round(4).to_csv(OUTPUT / "parameter_robustness.csv", index=False, encoding="utf-8-sig")

    if selected_trades is None:
        raise RuntimeError("Selected config was not evaluated")
    cost_rows = []
    gross = selected_trades["gross_points"].astype(float)
    for cost in [0.3, 0.5, 0.7, 1.0]:
        pnl = gross - cost
        row = {"round_trip_cost": cost}
        row.update(pnl_metrics(pnl))
        cost_rows.append(row)
    costs = pd.DataFrame(cost_rows)
    costs.round(4).to_csv(OUTPUT / "cost_sensitivity.csv", index=False, encoding="utf-8-sig")

    passed_neighbors = int(robustness["full_pass"].sum())
    report = [
        "# Daily Trend ADR Robustness",
        "",
        f"Full-period passing configurations: {passed_neighbors}/{len(robustness)}.",
        "",
        "## Parameter Neighbors",
        "",
        metrics.markdown_table(robustness.rename(columns={
            "config": "period",
            "net_points": "net_points",
            "profit_factor": "profit_factor",
            "max_drawdown_points": "max_drawdown_points",
            "full_pass": "passed",
        }).assign(start="2010-01-01", end="2026-06-17", trades=0, trades_per_trading_day=robustness["trades_per_day"])),
        "",
        "## Cost Sensitivity",
        "",
        costs.round(4).to_csv(index=False),
    ]
    (OUTPUT / "ROBUSTNESS.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("PARAMETER ROBUSTNESS")
    print(robustness.round(4).to_string(index=False))
    print("COST SENSITIVITY")
    print(costs.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
