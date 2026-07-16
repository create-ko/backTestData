# -*- coding: utf-8 -*-
"""Candle/trend quality filters for the 15m/5m retest strategy, one position at a time."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "candle_trend_filter_single_position_rr2"
START = "2010-01-01"
SELECTION_START = "2026-01-01"
END = "2026-06-17"
COST = 0.5


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


strategy = load_module("strategy152_for_154", SCRIPT_DIR / "152_daily_trend_adr_retest_expansion_rr2.py")
metrics = strategy.metrics


def build_quality_features(bars, sma_length: int = 120) -> pd.DataFrame:
    rows = [{
        "day": str(strategy.base.kst_day(bar.epoch)),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
    } for bar in bars]
    frame = pd.DataFrame(rows)
    daily = frame.groupby("day", sort=True).agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
    )
    daily["range"] = daily["high"] - daily["low"]
    daily["sma"] = daily["close"].rolling(sma_length, min_periods=sma_length).mean().shift(1)
    daily["adr20"] = daily["range"].rolling(20, min_periods=20).mean().shift(1)
    daily["previous_open"] = daily["open"].shift(1)
    daily["previous_close"] = daily["close"].shift(1)
    previous_range = daily["range"].shift(1)
    daily["previous_body_ratio"] = (
        (daily["previous_close"] - daily["previous_open"]).abs()
        / previous_range.replace(0.0, np.nan)
    ).fillna(0.0)
    daily["trend_strength"] = (
        (daily["previous_close"] - daily["sma"]).abs()
        / daily["adr20"].replace(0.0, np.nan)
    )
    daily["sma_slope_5"] = daily["sma"] - daily["sma"].shift(5)
    return daily.reset_index()[[
        "day", "previous_open", "previous_close", "previous_body_ratio",
        "trend_strength", "sma_slope_5",
    ]]


def add_quality(trades: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    out = trades.merge(quality, on="day", how="left")
    out["candle_aligned"] = np.where(
        out["direction"].eq("long"),
        out["previous_close"] > out["previous_open"],
        out["previous_close"] < out["previous_open"],
    )
    out["slope_aligned"] = np.where(
        out["direction"].eq("long"), out["sma_slope_5"] > 0, out["sma_slope_5"] < 0,
    )
    return out


def one_position(trades: pd.DataFrame) -> pd.DataFrame:
    kept = []
    active_exit = None
    for idx, row in trades.sort_values("entry_time").iterrows():
        if active_exit is None or row["entry_time"] >= active_exit:
            kept.append(idx)
            active_exit = row["exit_time"]
    return trades.loc[kept].sort_values("entry_time").reset_index(drop=True)


def apply_filter(
    trades: pd.DataFrame,
    trend_min: float,
    candle_mode: str,
    body_min: float,
    slope_mode: str,
) -> pd.DataFrame:
    mask = trades["trend_strength"].ge(trend_min)
    if candle_mode == "aligned":
        mask &= trades["candle_aligned"] & trades["previous_body_ratio"].ge(body_min)
    if slope_mode == "aligned":
        mask &= trades["slope_aligned"]
    return one_position(trades.loc[mask].copy())


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
        "trades": len(trades),
        "active_days": trades["day"].nunique(),
        "trades_per_day": len(trades) / 142,
        "net_points": float(pnl.sum()),
        "profit_factor": metrics.profit_factor(pnl),
        "max_drawdown": metrics.max_drawdown(pnl),
        "win_rate": float((pnl > 0).mean() * 100),
        "positive_month_rate": float((monthly > 0).mean() * 100),
    }


def main() -> None:
    data_path = ROOT / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"
    bars = strategy.base.load_bars(
        data_path,
        strategy.base.parse_kst("2010-01-01 00:00:00"),
        strategy.base.parse_kst("2026-06-17 00:00:00"),
    )
    sessions = strategy.base.build_session_windows(bars[0].epoch, bars[-1].epoch, 300)
    daily = strategy.hybrid.daily_features(bars, 120)
    entries = strategy.find_entries(
        bars, sessions, daily, START, END,
        "either", 6, 0.0, 0.50, 1.5,
    )
    quality = build_quality_features(bars, 120)
    candidates_by_hold = {}
    rows = []
    best = None
    for hold in [144, 288, 576]:
        raw = strategy.simulate(bars, entries, hold, concurrency_cap=1000)
        raw = add_quality(raw, quality)
        candidates_by_hold[hold] = raw
        sample_raw = metrics.select_period(raw, SELECTION_START, END)
        for trend_min in [0.0, 0.25, 0.50, 1.0]:
            for candle_mode in ["any", "aligned"]:
                body_values = [0.0] if candle_mode == "any" else [0.0, 0.30, 0.60]
                for body_min in body_values:
                    for slope_mode in ["any", "aligned"]:
                        trades = apply_filter(sample_raw, trend_min, candle_mode, body_min, slope_mode)
                        row = {
                            "max_hold_bars": hold,
                            "trend_strength_min": trend_min,
                            "candle_mode": candle_mode,
                            "previous_body_min": body_min,
                            "slope_mode": slope_mode,
                        }
                        row.update(selection_metrics(trades))
                        row["frequency_pass"] = 1.0 <= row["trades_per_day"] <= 3.0
                        row["score"] = row["net_points"] - 0.25 * row["max_drawdown"] + 2.0 * row["positive_month_rate"]
                        rows.append(row)
                        if row["frequency_pass"] and row["net_points"] > 0 and row["profit_factor"] > 1.0:
                            rank = (row["positive_month_rate"], row["score"], row["profit_factor"])
                            if best is None or rank > (best["positive_month_rate"], best["score"], best["profit_factor"]):
                                best = row.copy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep = pd.DataFrame(rows).sort_values(["frequency_pass", "score"], ascending=[False, False])
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        (OUTPUT / "REPORT.md").write_text("# Candle Trend Filter Single Position RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8")
        print(sweep.head(20).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    raw = candidates_by_hold[int(best["max_hold_bars"])]
    fixed = apply_filter(
        raw, float(best["trend_strength_min"]), str(best["candle_mode"]),
        float(best["previous_body_min"]), str(best["slope_mode"]),
    )
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
    full_pass = bool(result.loc[result["period"] == "full", "passed"].iloc[0])
    final = "PASSED" if full_pass and chunk_passes == 6 else ("CONDITIONAL_PASS" if full_pass else "REJECTED")
    keys = ["max_hold_bars", "trend_strength_min", "candle_mode", "previous_body_min", "slope_mode"]
    report = [
        "# Candle Trend Filter Single Position RR2", "",
        "- Base signal: daily SMA120 trend plus first-15m range and completed 5m retest",
        "- Quality candidates: trend distance, prior daily candle, and five-day SMA slope",
        "- Risk: prior ADR20 times 0.50, minimum 1.5; target: exact 2R; cost: 0.5",
        "- Execution: one position at a time", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "The filter is selected on 2026 only and then fixed for all historical slices.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
