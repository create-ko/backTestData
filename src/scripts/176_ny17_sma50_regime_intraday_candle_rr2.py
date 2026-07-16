# -*- coding: utf-8 -*-
"""Intraday candle RR2 entries during a completed NY17 SMA50 daily regime."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "ny17_sma50_regime_intraday_candle_rr2"
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


old_regime = load_module(
    "old_regime169_for_176", SCRIPT_DIR / "169_daily_king_regime_intraday_candle_rr2.py",
)
boundary = load_module(
    "boundary173_for_176", SCRIPT_DIR / "173_daily_king_keltner_boundary_sensitivity.py",
)
intraday = old_regime.intraday
metrics = intraday.metrics


def ny17_daily_trades(execution: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = boundary.aggregate_new_york(execution, 0)
    center = frame["typical"].rolling(50, min_periods=50).mean().to_numpy(float)
    atr = frame["tr"].rolling(40, min_periods=40).mean().to_numpy(float)
    trades = boundary.research.simulate(frame, center, atr, 1.0)
    return frame, trades


def completed_regime(
    intraday_index: pd.DatetimeIndex,
    daily_frame: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.Series:
    regime = pd.Series(0, index=intraday_index, dtype="int8")
    daily_index = pd.DatetimeIndex(daily_frame["time"])
    for trade in trades.itertuples(index=False):
        entry_pos = int(daily_index.searchsorted(trade.entry_time, side="left"))
        if entry_pos >= len(daily_index) or daily_index[entry_pos] != trade.entry_time:
            continue
        next_pos = entry_pos + 1
        if next_pos >= len(daily_index):
            continue
        start = daily_index[next_pos].tz_convert("Asia/Seoul")
        end = trade.exit_time.tz_convert("Asia/Seoul")
        if end <= start:
            continue
        direction = 1 if trade.direction == "long" else -1
        regime.loc[(regime.index >= start) & (regime.index < end)] = direction
    return regime


def main() -> None:
    df = intraday.prepare()
    daily_frame, daily_trades = ny17_daily_trades(df)
    timeframes = ["15min", "30min"]
    bar_cache = {tf: intraday.resample_signal_bars(df, tf) for tf in timeframes}
    regime_cache = {
        tf: completed_regime(bar_cache[tf].index, daily_frame, daily_trades)
        for tf in timeframes
    }
    rows = []
    best = None
    for timeframe in timeframes:
        for ema_length in [10, 20, 40]:
            for signal_mode in ["reclaim", "rejection", "engulf", "aligned"]:
                for session_mode in ["all", "no_us", "asia"]:
                    entries = old_regime.make_entries(
                        df, bar_cache[timeframe], regime_cache[timeframe], timeframe,
                        ema_length, signal_mode, session_mode, SELECTION_START, END,
                    )
                    for risk_mult in [1.0, 1.5, 2.0]:
                        for hold in [72, 144]:
                            trades = intraday.simulate(df, entries, risk_mult, hold)
                            row = {
                                "timeframe": timeframe, "ema_length": ema_length,
                                "signal_mode": signal_mode, "session_mode": session_mode,
                                "risk_mult": risk_mult, "max_hold_bars": hold,
                            }
                            row.update(intraday.selection_metrics(trades))
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
                                    best["positive_month_rate"], best["score"], best["profit_factor"],
                                ):
                                    best = row.copy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep = pd.DataFrame(rows).sort_values(
        ["frequency_pass", "positive_month_rate", "score"], ascending=[False, False, False],
    )
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        (OUTPUT / "REPORT.md").write_text(
            "# NY17 SMA50 Regime Intraday Candle RR2\n\nNo 2026 candidate passed.\n",
            encoding="utf-8",
        )
        print(sweep.head(30).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    tf = str(best["timeframe"])
    entries = old_regime.make_entries(
        df, bar_cache[tf], regime_cache[tf], tf, int(best["ema_length"]),
        str(best["signal_mode"]), str(best["session_mode"]), START, END,
    )
    fixed = intraday.simulate(
        df, entries, float(best["risk_mult"]), int(best["max_hold_bars"]),
    )
    metrics.audit_orders(fixed)
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
    keys = ["timeframe", "ema_length", "signal_mode", "session_mode", "risk_mult", "max_hold_bars"]
    report = [
        "# NY17 SMA50 Regime Intraday Candle RR2", "",
        "- Regime: gap-aware NY17 daily HLC3 SMA50 / simple TR40 King Keltner position",
        "- Regime begins only after the daily entry trading-day bar has completed",
        "- Trigger: completed intraday candle pattern relative to EMA",
        "- Entry: next 5m open; exit: fixed 2R with 5m adverse-stop first",
        "- Controls: KST 08:00-23:59, one position, cap 3/day, cost 0.5", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "Intraday parameters were selected on 2026 and frozen historically.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
