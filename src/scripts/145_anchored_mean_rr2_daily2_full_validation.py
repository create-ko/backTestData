# -*- coding: utf-8 -*-
"""Fixed full-history validation for the 2026 anchored-mean RR2 candidate."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "anchored_mean_rr2_daily2_full_validation"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


strategy = load_module("strategy129_for_145", SCRIPT_DIR / "129_2m_anchored_mean_reversion_rr2_sweep.py")
metrics = load_module("metrics144_for_145", SCRIPT_DIR / "144_bb20_rr2_daily2_validation.py")

START = "2010-01-01"
END = "2026-06-17"
SLICES = metrics.SLICES


def generate_raw_trades() -> pd.DataFrame:
    strategy.TEST_START = START
    strategy.TEST_END = END
    df = strategy.load_data()
    entries = strategy.find_entries(
        df=df,
        anchor_mode="day_mean",
        trigger_mode="wick",
        reclaim_mode="both",
        bias_mode="price_follow",
        displacement_mode="body35_close_extreme",
        min_anchor_bars=20,
        distance_mult=1.6,
        cooldown_bars=3,
    )
    trades = strategy.base115.simulate_rr2(
        df=df,
        entries=entries,
        stop_mode="retest",
        stop_buffer=0.2,
        min_risk=0.8,
        max_risk=8.0,
        max_hold_bars=30,
        cap=5,
    )
    return trades.sort_values("entry_time").reset_index(drop=True)


def main() -> None:
    raw = generate_raw_trades()
    metrics.audit_orders(raw)
    sample = metrics.select_period(raw, "2026-01-01", END)
    full = metrics.select_period(raw, START, END)
    rows = [metrics.summarize("selection_2026", "2026-01-01", END, 142, sample)]
    for start, end, trading_days in SLICES:
        rows.append(metrics.summarize("3y_chunk", start, end, trading_days, metrics.select_period(raw, start, end)))
    rows.append(metrics.summarize("full", START, END, 5125, full))
    summary = pd.DataFrame(rows)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary.round(4).to_csv(OUTPUT / "summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")

    selection_pass = bool(summary.loc[summary["period"] == "selection_2026", "passed"].iloc[0])
    full_pass = bool(summary.loc[summary["period"] == "full", "passed"].iloc[0])
    final = "PASSED" if selection_pass and full_pass else "REJECTED"
    report = [
        "# Anchored Mean RR2 Daily-2 Full Validation",
        "",
        "- Signal: wick stretch from the expanding KST day mean, then candle reclaim toward the mean",
        "- Confirmation: price-follow bias and body-35 close-extreme displacement",
        "- Entry: next 2-minute open after at least 20 anchor bars and 1.6 median-range stretch",
        "- Exit: signal-extreme stop plus 0.2 points, fixed 2R target, maximum hold 30 bars",
        "- Risk bounds: 0.8-8.0 points; round-trip cost: 0.5 points",
        "- Frequency: retain the first three entries per trading day; required average: 2.0-3.0",
        "",
        f"Final decision: **{final}**.",
        "",
        metrics.markdown_table(summary),
        "",
        "The 2026-selected parameters remain fixed in every historical slice.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("RAW_TRADES", len(raw))
    print(summary.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
