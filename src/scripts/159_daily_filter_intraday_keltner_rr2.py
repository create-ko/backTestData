# -*- coding: utf-8 -*-
"""Completed-daily trend/candle filters for the selected intraday Keltner RR2 entry."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_filter_intraday_keltner_rr2"
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


strategy = load_module("strategy157_for_159", SCRIPT_DIR / "157_intraday_king_keltner_rr2.py")
metrics = strategy.metrics


def daily_features(df: pd.DataFrame, sma_length: int, slope_days: int) -> pd.DataFrame:
    daily = df[["open", "high", "low", "close"]].resample("1D", label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
    }).dropna()
    daily["range"] = daily["high"] - daily["low"]
    raw_sma = daily["close"].rolling(sma_length, min_periods=sma_length).mean()
    daily["previous_open"] = daily["open"].shift(1)
    daily["previous_close"] = daily["close"].shift(1)
    daily["sma"] = raw_sma.shift(1)
    daily["sma_slope"] = daily["sma"] - daily["sma"].shift(slope_days)
    daily["adr20"] = daily["range"].rolling(20, min_periods=20).mean().shift(1)
    daily["day"] = daily.index.date.astype(str)
    return daily.reset_index(drop=True)[[
        "day", "previous_open", "previous_close", "sma", "sma_slope", "adr20",
    ]]


def add_features(entries: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    out = entries.merge(features, on="day", how="left")
    long_side = out["direction"].eq("long")
    out["price_aligned"] = np.where(
        long_side, out["previous_close"] >= out["sma"], out["previous_close"] < out["sma"],
    )
    out["slope_aligned"] = np.where(
        long_side, out["sma_slope"] > 0, out["sma_slope"] < 0,
    )
    out["candle_aligned"] = np.where(
        long_side,
        out["previous_close"] > out["previous_open"],
        out["previous_close"] < out["previous_open"],
    )
    out["trend_distance"] = (
        (out["previous_close"] - out["sma"]).abs()
        / out["adr20"].replace(0.0, np.nan)
    )
    return out


def apply_filter(
    entries: pd.DataFrame,
    daily_mode: str,
    distance_min: float,
    candle_mode: str,
    session_mode: str,
) -> pd.DataFrame:
    mask = entries["sma"].notna() & entries["adr20"].notna()
    if daily_mode == "price":
        mask &= entries["price_aligned"]
    elif daily_mode == "slope":
        mask &= entries["slope_aligned"]
    elif daily_mode == "both":
        mask &= entries["price_aligned"] & entries["slope_aligned"]
    elif daily_mode != "none":
        raise ValueError(daily_mode)
    if distance_min > 0:
        mask &= entries["trend_distance"] >= distance_min
    if candle_mode == "aligned":
        mask &= entries["candle_aligned"]
    if session_mode == "no_europe":
        mask &= entries["session"].astype(str).ne("europe")
    return entries.loc[mask].sort_values("entry_time").reset_index(drop=True)


def selection_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "trades": 0, "active_days": 0, "trades_per_day": 0.0,
            "net_points": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0,
            "win_rate": 0.0, "positive_month_rate": 0.0,
        }
    pnl = trades["net_points"]
    monthly = trades.groupby("month")["net_points"].sum()
    return {
        "trades": len(trades), "active_days": trades["day"].nunique(),
        "trades_per_day": len(trades) / 142,
        "net_points": float(pnl.sum()),
        "profit_factor": metrics.profit_factor(pnl),
        "max_drawdown": metrics.max_drawdown(pnl),
        "win_rate": float((pnl > 0).mean() * 100),
        "positive_month_rate": float((monthly > 0).mean() * 100),
    }


def main() -> None:
    df = strategy.prepare()
    signal_bars = strategy.resample_signal_bars(df, "1h")
    raw_entries = strategy.make_entries(
        df, signal_bars, "1h", 20, 20, 1.0, START, END,
    )
    rows = []
    best = None
    best_entries = None
    for sma_length in [60, 120, 200]:
        for slope_days in [5, 20]:
            enriched = add_features(raw_entries, daily_features(df, sma_length, slope_days))
            for daily_mode in ["none", "price", "slope", "both"]:
                for distance_min in [0.0, 0.25, 0.50]:
                    for candle_mode in ["any", "aligned"]:
                        for session_mode in ["all", "no_europe"]:
                            selected_entries = apply_filter(
                                enriched, daily_mode, distance_min, candle_mode, session_mode,
                            )
                            sample_entries = selected_entries[
                                (selected_entries["entry_time"] >= pd.Timestamp(SELECTION_START, tz="Asia/Seoul"))
                                & (selected_entries["entry_time"] < pd.Timestamp(END, tz="Asia/Seoul"))
                            ]
                            trades = strategy.simulate(df, sample_entries, 2.0, 144)
                            row = {
                                "sma_length": sma_length, "slope_days": slope_days,
                                "daily_mode": daily_mode, "distance_min": distance_min,
                                "candle_mode": candle_mode, "session_mode": session_mode,
                            }
                            row.update(selection_metrics(trades))
                            row["frequency_pass"] = 1.0 <= row["trades_per_day"] <= 3.0
                            row["score"] = row["net_points"] - 0.25 * row["max_drawdown"] + 2.0 * row["positive_month_rate"]
                            rows.append(row)
                            if row["frequency_pass"] and row["net_points"] > 0 and row["profit_factor"] > 1.0:
                                rank = (row["positive_month_rate"], row["score"], row["profit_factor"])
                                if best is None or rank > (best["positive_month_rate"], best["score"], best["profit_factor"]):
                                    best = row.copy()
                                    best_entries = selected_entries.copy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep = pd.DataFrame(rows).sort_values(["frequency_pass", "score"], ascending=[False, False])
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None or best_entries is None:
        (OUTPUT / "REPORT.md").write_text("# Daily Filter Intraday Keltner RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8")
        print(sweep.head(20).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    fixed = strategy.simulate(df, best_entries, 2.0, 144)
    metrics.audit_orders(fixed)
    sample = metrics.select_period(fixed, SELECTION_START, END)
    full = metrics.select_period(fixed, START, END)
    result_rows = [metrics.summarize("selection_2026", SELECTION_START, END, 142, sample)]
    for start, end, days in metrics.SLICES:
        result_rows.append(metrics.summarize("3y_chunk", start, end, days, metrics.select_period(fixed, start, end)))
    result_rows.append(metrics.summarize("full", START, END, 5125, full))
    result = pd.DataFrame(result_rows)
    result["frequency_pass"] = result["trades_per_trading_day"].between(1.0, 3.0, inclusive="both")
    result["passed"] = result["frequency_pass"] & result["performance_pass"]
    result.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")
    chunk_passes = int(result.loc[result["period"] == "3y_chunk", "performance_pass"].sum())
    full_performance = bool(result.loc[result["period"] == "full", "performance_pass"].iloc[0])
    final = "PASSED" if full_performance and chunk_passes == 6 else ("CONDITIONAL_PASS" if full_performance else "REJECTED")
    keys = ["sma_length", "slope_days", "daily_mode", "distance_min", "candle_mode", "session_mode"]
    report = [
        "# Daily Filter Intraday Keltner RR2", "",
        "- Base: completed 1h King Keltner trend breakout, ATR2 risk, exact 2R",
        "- Daily filter: only prior completed KST daily candles and SMA state",
        "- Execution: 5m stop-first, one position, at most three KST-day entries, cost 0.5", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "Daily filter parameters are selected on 2026 and fixed in all historical slices.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
