# -*- coding: utf-8 -*-
"""Completed-daily trend plus intraday candle MA-reclaim strategy at fixed 2R."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_trend_candle_reclaim_rr2"
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


strategy = load_module("strategy157_for_164", SCRIPT_DIR / "157_intraday_king_keltner_rr2.py")
metrics = strategy.metrics


def completed_daily_direction(df: pd.DataFrame, length: int, index: pd.DatetimeIndex) -> pd.Series:
    daily = df[["high", "low", "close"]].resample("1D", label="left", closed="left").agg({
        "high": "max", "low": "min", "close": "last",
    }).dropna()
    typical = (daily["high"] + daily["low"] + daily["close"]) / 3.0
    center = typical.rolling(length, min_periods=length).mean()
    raw = pd.Series(
        np.where(center > center.shift(1), 1, np.where(center < center.shift(1), -1, 0)),
        index=daily.index,
    )
    # The bar labelled D becomes usable only when D+1 starts.
    return raw.shift(1).reindex(index, method="ffill")


def make_entries(
    df: pd.DataFrame,
    timeframe: str,
    daily_length: int,
    intraday_length: int,
    session_mode: str,
    start: str,
    end: str,
) -> pd.DataFrame:
    bars = strategy.resample_signal_bars(df, timeframe)
    ema = bars["close"].ewm(span=intraday_length, adjust=False, min_periods=intraday_length).mean()
    atr = strategy.true_range(bars).rolling(14, min_periods=14).mean()
    daily_direction = completed_daily_direction(df, daily_length, bars.index)
    bullish = (bars["close"] > bars["open"]) & (bars["close"] > ema) & (bars["close"].shift(1) <= ema.shift(1))
    bearish = (bars["close"] < bars["open"]) & (bars["close"] < ema) & (bars["close"].shift(1) >= ema.shift(1))
    direction = np.where((daily_direction == 1) & bullish, 1, np.where((daily_direction == -1) & bearish, -1, 0))
    signals = pd.DataFrame({"direction": direction, "atr": atr}, index=bars.index)
    signals = signals[(signals["direction"] != 0) & signals["atr"].notna()]
    start_ts = pd.Timestamp(start, tz="Asia/Seoul")
    end_ts = pd.Timestamp(end, tz="Asia/Seoul")
    offset = pd.tseries.frequencies.to_offset(timeframe)
    signals = signals[(signals.index >= start_ts - offset) & (signals.index < end_ts - offset)]
    rows = []
    for ts, signal in signals.iterrows():
        entry_time = ts + offset
        if entry_time < start_ts or entry_time >= end_ts or not 8 <= entry_time.hour <= 23:
            continue
        pos = int(df.index.searchsorted(entry_time, side="left"))
        if pos >= len(df) or df.index[pos] != entry_time:
            continue
        session = str(df["session"].iloc[pos])
        if session_mode == "asia" and session != "asia":
            continue
        if session_mode == "no_us" and session == "us_open":
            continue
        direction_name = "long" if int(signal["direction"]) == 1 else "short"
        rows.append({
            "entry_pos": pos,
            "entry_time": entry_time,
            "entry_price": float(df["open"].iloc[pos]),
            "direction": direction_name,
            "signal_time": ts,
            "atr": float(signal["atr"]),
            "day": entry_time.date().isoformat(),
            "session": session,
            "year": int(entry_time.year),
            "month": entry_time.strftime("%Y-%m"),
        })
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def main() -> None:
    df = strategy.prepare()
    rows = []
    best = None
    for timeframe in ["15min", "30min"]:
        for daily_length in [20, 40, 80]:
            for intraday_length in [10, 20, 40]:
                for session_mode in ["all", "no_us", "asia"]:
                    entries = make_entries(
                        df, timeframe, daily_length, intraday_length,
                        session_mode, SELECTION_START, END,
                    )
                    for risk_mult in [1.0, 1.5, 2.0]:
                        for hold in [72, 144]:
                            trades = strategy.simulate(df, entries, risk_mult, hold)
                            row = {
                                "timeframe": timeframe,
                                "daily_length": daily_length,
                                "intraday_length": intraday_length,
                                "session_mode": session_mode,
                                "risk_mult": risk_mult,
                                "max_hold_bars": hold,
                            }
                            row.update(strategy.selection_metrics(trades))
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
            "# Daily Trend Candle Reclaim RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8",
        )
        print(sweep.head(20).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    entries = make_entries(
        df, str(best["timeframe"]), int(best["daily_length"]),
        int(best["intraday_length"]), str(best["session_mode"]), START, END,
    )
    fixed = strategy.simulate(
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
    keys = [
        "timeframe", "daily_length", "intraday_length",
        "session_mode", "risk_mult", "max_hold_bars",
    ]
    report = [
        "# Daily Trend Candle Reclaim RR2", "",
        "- Direction: slope of a completed KST daily typical-price SMA",
        "- Candle trigger: completed bullish/bearish intraday candle reclaims its EMA",
        "- Entry: next 5m open after the signal candle",
        "- Exit: ATR risk with 2-point floor, exact 2R, 5m adverse-stop first",
        "- Controls: KST 08:00-23:59, one position, cap 3/day, cost 0.5", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "Parameters were selected on 2026 and frozen for every historical slice.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
