# -*- coding: utf-8 -*-
"""5m parameter-neighborhood, bootstrap, and tail-risk audit for NY17 SMA50."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "ny17_daily_king_sma50_5m_robustness"
ATR_LENGTHS = [20, 30, 40, 60, 80]
BANDS = [0.5, 0.75, 1.0, 1.25, 1.5]
SLICES = [
    ("2010-01-01", "2013-01-01"), ("2013-01-01", "2016-01-01"),
    ("2016-01-01", "2019-01-01"), ("2019-01-01", "2022-01-01"),
    ("2022-01-01", "2025-01-01"), ("2025-01-01", "2026-06-17"),
]
SEED = 20260714
IID_SAMPLES = 20_000
YEAR_BLOCK_SAMPLES = 10_000


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


execution_model = load_module(
    "execution178_for_179",
    SCRIPT_DIR / "178_ny17_daily_king_sma50_5m_execution.py",
)
boundary = execution_model.boundary
research = execution_model.research


def max_drawdown(values: np.ndarray) -> float:
    equity = np.cumsum(values)
    peaks = np.maximum.accumulate(np.maximum(equity, 0.0))
    return float(np.max(peaks - equity)) if len(values) else 0.0


def longest_losing_streak(values: np.ndarray) -> int:
    longest = current = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def net_profit_factor(values: np.ndarray) -> float:
    wins = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    return wins / losses if losses else float("inf")


def bootstrap_iid(pnl: np.ndarray, rng: np.random.Generator) -> dict:
    samples = rng.choice(pnl, size=(IID_SAMPLES, len(pnl)), replace=True)
    equity = samples.cumsum(axis=1)
    peaks = np.maximum.accumulate(np.maximum(equity, 0.0), axis=1)
    drawdowns = (peaks - equity).max(axis=1)
    endings = equity[:, -1]
    return bootstrap_row("iid_trade", IID_SAMPLES, endings, drawdowns)


def bootstrap_year_blocks(trades: pd.DataFrame, rng: np.random.Generator) -> dict:
    blocks = [
        group["net_points"].to_numpy(float)
        for _, group in trades.groupby(trades["entry_time"].dt.year, sort=True)
    ]
    endings = np.empty(YEAR_BLOCK_SAMPLES, dtype=float)
    drawdowns = np.empty(YEAR_BLOCK_SAMPLES, dtype=float)
    for sample_i in range(YEAR_BLOCK_SAMPLES):
        indices = rng.integers(0, len(blocks), size=len(blocks))
        values = np.concatenate([blocks[index] for index in indices])
        endings[sample_i] = values.sum()
        drawdowns[sample_i] = max_drawdown(values)
    return bootstrap_row("calendar_year_block", YEAR_BLOCK_SAMPLES, endings, drawdowns)


def bootstrap_row(method: str, samples: int, endings: np.ndarray, drawdowns: np.ndarray) -> dict:
    return {
        "method": method,
        "samples": samples,
        "net_p05": np.quantile(endings, 0.05),
        "net_median": np.quantile(endings, 0.50),
        "net_p95": np.quantile(endings, 0.95),
        "probability_net_le_zero_pct": 100.0 * np.mean(endings <= 0),
        "dd_median": np.quantile(drawdowns, 0.50),
        "dd_p95": np.quantile(drawdowns, 0.95),
        "dd_p99": np.quantile(drawdowns, 0.99),
    }


def direction_period_rows(trades: pd.DataFrame) -> list[dict]:
    masks = {
        "all": pd.Series(True, index=trades.index),
        "long": trades["direction"].eq("long"),
        "short": trades["direction"].eq("short"),
        "pre_2025": trades["entry_time"].dt.year < 2025,
        "2025_plus": trades["entry_time"].dt.year >= 2025,
    }
    rows = []
    for name, mask in masks.items():
        subset = trades.loc[mask]
        stats = research.stats(subset)
        rows.append({
            "segment": name,
            **stats,
            "average_net": subset["net_points"].mean(),
            "median_net": subset["net_points"].median(),
            "median_hold_days": subset["hold_days"].median(),
            "average_initial_risk": subset["initial_risk_points"].mean(),
            "average_net_r": subset["net_r"].mean(),
        })
    return rows


def concentration_rows(trades: pd.DataFrame) -> list[dict]:
    pnl = trades["net_points"].to_numpy(float)
    total = pnl.sum()
    rows = []
    for remove_count in [0, 1, 3, 5, 10]:
        if remove_count:
            keep = trades.drop(trades.nlargest(remove_count, "net_points").index)
        else:
            keep = trades
        values = keep["net_points"].to_numpy(float)
        rows.append({
            "largest_wins_removed": remove_count,
            "trades": len(values),
            "net": values.sum(),
            "pf": net_profit_factor(values),
            "dd": max_drawdown(values),
            "net_retained_pct": 100.0 * values.sum() / total,
        })
    return rows


def main() -> None:
    execution = boundary.intraday.prepare()
    daily = boundary.aggregate_new_york(execution, 0)
    neighbor_rows = []
    central = None

    for atr_length in ATR_LENGTHS:
        for band in BANDS:
            trades = execution_model.simulate_5m(
                execution, daily, ma_length=50, atr_length=atr_length, band=band,
            )
            full = research.stats(trades)
            chunk_nets = [
                research.stats(research.period(trades, start, end))["net"]
                for start, end in SLICES
            ]
            row = {
                "ma_length": 50,
                "tr_length": atr_length,
                "band": band,
                **full,
                "positive_chunks": sum(value > 0 for value in chunk_nets),
                "worst_chunk_net": min(chunk_nets),
                "same_5m_round_trips": int(trades["same_bar_exit"].sum()),
            }
            row.update({f"chunk_{i + 1}_net": value for i, value in enumerate(chunk_nets)})
            neighbor_rows.append(row)
            if atr_length == 40 and band == 1.0:
                central = trades.copy()
            print("CONFIG", atr_length, band, full["trades"], round(full["net"], 2), row["positive_chunks"])

    assert central is not None
    neighbors = pd.DataFrame(neighbor_rows)
    neighbor_summary = pd.DataFrame([{
        "configs": len(neighbors),
        "six_positive_chunk_configs": int(neighbors["positive_chunks"].eq(6).sum()),
        "positive_full_net_configs": int(neighbors["net"].gt(0).sum()),
        "pf_min": neighbors["pf"].min(),
        "pf_median": neighbors["pf"].median(),
        "pf_max": neighbors["pf"].max(),
        "net_min": neighbors["net"].min(),
        "net_median": neighbors["net"].median(),
        "net_max": neighbors["net"].max(),
        "minimum_worst_chunk_net": neighbors["worst_chunk_net"].min(),
    }])

    central["initial_risk_points"] = (central["entry_price"] - central["entry_center"]).abs()
    central["net_r"] = central["net_points"] / central["initial_risk_points"]
    central["hold_days"] = (
        central["exit_time"] - central["entry_time"]
    ).dt.total_seconds() / 86_400.0
    central["year"] = central["entry_time"].dt.year
    pnl = central["net_points"].to_numpy(float)

    rng = np.random.default_rng(SEED)
    bootstraps = pd.DataFrame([
        bootstrap_iid(pnl, rng),
        bootstrap_year_blocks(central, rng),
    ])
    directions = pd.DataFrame(direction_period_rows(central))
    concentration = pd.DataFrame(concentration_rows(central))
    rolling_30 = central["net_points"].rolling(30).sum().dropna()
    risk = pd.DataFrame([{
        "trades": len(central),
        "longest_losing_streak": longest_losing_streak(pnl),
        "largest_loss_points": pnl.min(),
        "loss_p05_points": np.quantile(pnl, 0.05),
        "initial_risk_median": central["initial_risk_points"].median(),
        "initial_risk_p95": central["initial_risk_points"].quantile(0.95),
        "net_r_p05": central["net_r"].quantile(0.05),
        "net_r_median": central["net_r"].median(),
        "net_r_p95": central["net_r"].quantile(0.95),
        "positive_rolling_30_windows_pct": 100.0 * rolling_30.gt(0).mean(),
        "rolling_30_net_min": rolling_30.min(),
        "top_1_win_pct_of_total_net": 100.0 * central["net_points"].nlargest(1).sum() / pnl.sum(),
        "top_3_wins_pct_of_total_net": 100.0 * central["net_points"].nlargest(3).sum() / pnl.sum(),
        "top_5_wins_pct_of_total_net": 100.0 * central["net_points"].nlargest(5).sum() / pnl.sum(),
    }])

    OUTPUT.mkdir(parents=True, exist_ok=True)
    neighbors.round(6).to_csv(OUTPUT / "neighbor_configs_5m.csv", index=False, encoding="utf-8-sig")
    neighbor_summary.round(6).to_csv(OUTPUT / "neighbor_summary_5m.csv", index=False, encoding="utf-8-sig")
    bootstraps.round(6).to_csv(OUTPUT / "bootstrap_summary.csv", index=False, encoding="utf-8-sig")
    directions.round(6).to_csv(OUTPUT / "direction_period_summary.csv", index=False, encoding="utf-8-sig")
    concentration.round(6).to_csv(OUTPUT / "concentration_summary.csv", index=False, encoding="utf-8-sig")
    risk.round(6).to_csv(OUTPUT / "risk_summary.csv", index=False, encoding="utf-8-sig")
    central.to_csv(OUTPUT / "central_trades_with_risk.csv", index=False, encoding="utf-8-sig")

    central_stats = research.stats(central)
    ns = neighbor_summary.iloc[0]
    iid = bootstraps.loc[bootstraps["method"].eq("iid_trade")].iloc[0]
    year_block = bootstraps.loc[bootstraps["method"].eq("calendar_year_block")].iloc[0]
    r = risk.iloc[0]
    report = [
        "# NY17 SMA50 5m Robustness and Tail-Risk Audit", "",
        "## Central 5m execution", "",
        f"- {central_stats['trades']} trades, net {central_stats['net']:.2f}, PF {central_stats['pf']:.4f}, DD {central_stats['dd']:.2f}.",
        "- Round-trip cost 0.5; NY17 DST-aware daily signals; chronological 5m stop execution.", "",
        "## 5m parameter neighborhood", "",
        f"- Six profitable three-year chunks: {int(ns['six_positive_chunk_configs'])}/{int(ns['configs'])} configurations.",
        f"- Full-net positive: {int(ns['positive_full_net_configs'])}/{int(ns['configs'])}; PF range {ns['pf_min']:.4f} to {ns['pf_max']:.4f}.",
        f"- Worst single chunk across all neighbors: {ns['minimum_worst_chunk_net']:.2f} points.", "",
        "## Resampling risk", "",
        f"- IID trade bootstrap ({IID_SAMPLES:,}): loss probability {iid['probability_net_le_zero_pct']:.2f}%, net p05 {iid['net_p05']:.2f}, DD p95 {iid['dd_p95']:.2f}, DD p99 {iid['dd_p99']:.2f}.",
        f"- Calendar-year block bootstrap ({YEAR_BLOCK_SAMPLES:,}): loss probability {year_block['probability_net_le_zero_pct']:.2f}%, net p05 {year_block['net_p05']:.2f}, DD p95 {year_block['dd_p95']:.2f}, DD p99 {year_block['dd_p99']:.2f}.", "",
        "## Tail concentration", "",
        f"- Largest win contributes {r['top_1_win_pct_of_total_net']:.2f}% of total net; top five contribute {r['top_5_wins_pct_of_total_net']:.2f}%.",
        f"- Positive rolling 30-trade windows: {r['positive_rolling_30_windows_pct']:.2f}%; longest losing streak: {int(r['longest_losing_streak'])}.",
        "- Trend following is expected to be right-tail dependent, but this concentration limits confidence in the historical point estimate.", "",
        "## Decision", "",
        "Retain only as a low-frequency research and forward-paper candidate. It is not evidence for a 1-3 entries/day strategy and is not ready for live deployment.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("NEIGHBOR_SUMMARY")
    print(neighbor_summary.round(4).to_string(index=False))
    print("BOOTSTRAP")
    print(bootstraps.round(4).to_string(index=False))
    print("RISK")
    print(risk.round(4).to_string(index=False))
    print("CONCENTRATION")
    print(concentration.round(4).to_string(index=False))
    print("DIRECTION_PERIOD")
    print(directions.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
