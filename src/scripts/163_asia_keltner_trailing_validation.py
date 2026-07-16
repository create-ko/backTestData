# -*- coding: utf-8 -*-
"""Frozen historical validation of the 2026-selected Asia-session candidate."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
SWEEP = ROOT / "result" / "session_focused_keltner_trailing" / "selection_2026_sweep.csv"
OUTPUT = ROOT / "result" / "asia_keltner_trailing_validation"
START = "2010-01-01"
SELECTION_START = "2026-01-01"
END = "2026-06-17"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


session_strategy = load_module(
    "session162_for_163", SCRIPT_DIR / "162_session_focused_keltner_trailing.py",
)
trail = session_strategy.trail
strategy = trail.strategy
metrics = trail.metrics


def main() -> None:
    sweep = pd.read_csv(SWEEP)
    candidates = sweep[
        sweep["session_mode"].eq("asia")
        & sweep["frequency_pass"].astype(str).str.lower().eq("true")
        & (sweep["net_points"] > 0)
        & (sweep["profit_factor"] > 1.0)
    ].sort_values(["positive_month_rate", "score", "profit_factor"], ascending=False)
    if candidates.empty:
        raise ValueError("No eligible Asia candidate")
    best = candidates.iloc[0]
    df = strategy.prepare()
    timeframe = str(best["timeframe"])
    ma_length = int(best["ma_length"])
    signal_bars = strategy.resample_signal_bars(df, timeframe)
    center = trail.completed_center(signal_bars, df.index, ma_length)
    entries = strategy.make_entries(
        df, signal_bars, timeframe, ma_length, int(best["atr_length"]),
        float(best["band_mult"]), START, END,
    )
    entries = trail.restrict_entry_hours(entries)
    entries = session_strategy.filter_session(entries, "asia")
    fixed = trail.simulate(
        df, entries, center, float(best["risk_mult"]), int(best["max_hold_bars"]),
    )
    trail.audit_trades(fixed)
    sample = metrics.select_period(fixed, SELECTION_START, END)
    full = metrics.select_period(fixed, START, END)
    rows = [metrics.summarize("selection_2026", SELECTION_START, END, 142, sample)]
    for start, end, days in metrics.SLICES:
        rows.append(metrics.summarize(
            "3y_chunk", start, end, days, metrics.select_period(fixed, start, end),
        ))
    rows.append(metrics.summarize("full", START, END, 5125, full))
    result = pd.DataFrame(rows)
    result["frequency_pass"] = result["trades_per_trading_day"].between(1.0, 3.0, inclusive="both")
    result["passed"] = result["frequency_pass"] & result["performance_pass"]
    chunk_passes = int(result.loc[result["period"] == "3y_chunk", "performance_pass"].sum())
    full_performance = bool(result.loc[result["period"] == "full", "performance_pass"].iloc[0])
    final = (
        "PASSED" if full_performance and chunk_passes == 6
        else ("CONDITIONAL_PASS" if full_performance else "REJECTED")
    )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    result.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(sample, "month").round(4).to_csv(
        OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig",
    )
    metrics.breakdown(full, "year").round(4).to_csv(
        OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig",
    )
    keys = [
        "timeframe", "ma_length", "atr_length", "band_mult",
        "session_mode", "risk_mult", "max_hold_bars",
    ]
    report = [
        "# Asia Keltner Trailing Validation", "",
        "- Candle trigger: next-bar break of the completed Keltner channel",
        "- Trend: completed typical-price SMA slope",
        "- Exit: initial ATR stop followed by completed center line",
        "- Entry scope: Asia session within KST 08:00-23:59",
        "- Execution: 5m adverse-stop first, one position, cap 3/day, cost 0.5",
        "- Important: variable-R trend exit, not fixed 2R", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "The numeric parameters were selected only on 2026 and then frozen.",
        "Research caveat: the Asia-only family was introduced after inspecting prior full-history session decomposition, so this is secondary exploration rather than pristine OOS evidence.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_ASIA_2026", best.to_dict())
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
