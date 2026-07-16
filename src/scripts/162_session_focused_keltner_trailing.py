# -*- coding: utf-8 -*-
"""Session-focused candle breakout plus trend strategy with center-line exit."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "session_focused_keltner_trailing"
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


trail = load_module("trail160_for_162", SCRIPT_DIR / "160_intraday_king_keltner_trailing.py")
strategy = trail.strategy
metrics = trail.metrics


def filter_session(entries: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode == "asia":
        mask = entries["session"].eq("asia")
    elif mode == "asia_europe":
        mask = entries["session"].isin(["asia", "europe"])
    elif mode == "all":
        mask = pd.Series(True, index=entries.index)
    else:
        raise ValueError(mode)
    return entries.loc[mask].sort_values("entry_time").reset_index(drop=True)


def main() -> None:
    df = strategy.prepare()
    ma_grid = {"15min": [40, 80, 120], "30min": [20, 40, 60], "1h": [20, 40]}
    signal_cache = {tf: strategy.resample_signal_bars(df, tf) for tf in ma_grid}
    center_cache = {}
    rows = []
    best = None
    for timeframe, ma_lengths in ma_grid.items():
        for ma_length in ma_lengths:
            center = trail.completed_center(signal_cache[timeframe], df.index, ma_length)
            center_cache[(timeframe, ma_length)] = center
            for atr_length in sorted({max(20, ma_length // 2), ma_length}):
                for band_mult in [0.5, 1.0]:
                    raw_entries = strategy.make_entries(
                        df, signal_cache[timeframe], timeframe, ma_length,
                        atr_length, band_mult, SELECTION_START, END,
                    )
                    raw_entries = trail.restrict_entry_hours(raw_entries)
                    for session_mode in ["asia", "asia_europe", "all"]:
                        entries = filter_session(raw_entries, session_mode)
                        for risk_mult in [1.0, 1.5, 2.0]:
                            trades = trail.simulate(df, entries, center, risk_mult, 576)
                            row = {
                                "timeframe": timeframe, "ma_length": ma_length,
                                "atr_length": atr_length, "band_mult": band_mult,
                                "session_mode": session_mode, "risk_mult": risk_mult,
                                "max_hold_bars": 576,
                            }
                            row.update(trail.selection_metrics(trades))
                            row["frequency_pass"] = 1.0 <= row["trades_per_day"] <= 3.0
                            row["score"] = (
                                row["net_points"] - 0.25 * row["max_drawdown"]
                                + 2.0 * row["positive_month_rate"]
                            )
                            rows.append(row)
                            eligible = (
                                row["frequency_pass"] and row["net_points"] > 0
                                and row["profit_factor"] > 1.0
                            )
                            if eligible:
                                rank = (row["positive_month_rate"], row["score"], row["profit_factor"])
                                if best is None or rank > (
                                    best["positive_month_rate"], best["score"], best["profit_factor"]
                                ):
                                    best = row.copy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep = pd.DataFrame(rows).sort_values(
        ["frequency_pass", "positive_month_rate", "score"], ascending=[False, False, False],
    )
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        (OUTPUT / "REPORT.md").write_text(
            "# Session-Focused Keltner Trailing\n\nNo 2026 candidate passed.\n", encoding="utf-8",
        )
        print(sweep.head(20).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    tf = str(best["timeframe"])
    ma_length = int(best["ma_length"])
    raw_entries = strategy.make_entries(
        df, signal_cache[tf], tf, ma_length, int(best["atr_length"]),
        float(best["band_mult"]), START, END,
    )
    raw_entries = trail.restrict_entry_hours(raw_entries)
    entries = filter_session(raw_entries, str(best["session_mode"]))
    fixed = trail.simulate(
        df, entries, center_cache[(tf, ma_length)], float(best["risk_mult"]), 576,
    )
    trail.audit_trades(fixed)
    sample = metrics.select_period(fixed, SELECTION_START, END)
    full = metrics.select_period(fixed, START, END)
    result_rows = [metrics.summarize("selection_2026", SELECTION_START, END, 142, sample)]
    for start, end, days in metrics.SLICES:
        result_rows.append(metrics.summarize(
            "3y_chunk", start, end, days, metrics.select_period(fixed, start, end),
        ))
    result_rows.append(metrics.summarize("full", START, END, 5125, full))
    result = pd.DataFrame(result_rows)
    result["frequency_pass"] = result["trades_per_trading_day"].between(1.0, 3.0, inclusive="both")
    result["passed"] = result["frequency_pass"] & result["performance_pass"]
    result.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(
        OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig",
    )
    chunk_passes = int(result.loc[result["period"] == "3y_chunk", "performance_pass"].sum())
    full_performance = bool(result.loc[result["period"] == "full", "performance_pass"].iloc[0])
    final = (
        "PASSED" if full_performance and chunk_passes == 6
        else ("CONDITIONAL_PASS" if full_performance else "REJECTED")
    )
    keys = [
        "timeframe", "ma_length", "atr_length", "band_mult",
        "session_mode", "risk_mult", "max_hold_bars",
    ]
    report = [
        "# Session-Focused Keltner Trailing", "",
        "- Candle trigger: next-bar break of the completed HTF Keltner channel",
        "- Trend: completed typical-price SMA slope",
        "- Exit: initial ATR stop followed by completed HTF center line",
        "- Controls: KST 08:00-23:59, one position, cap 3/day, cost 0.5",
        "- Important: variable-R trend exit, not fixed 2R", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "Only 2026 selected the parameters; all historical chunks use the frozen configuration.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
