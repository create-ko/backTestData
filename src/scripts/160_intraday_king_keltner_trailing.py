# -*- coding: utf-8 -*-
"""Intraday King Keltner breakout with a completed-HTF center-line exit."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "intraday_king_keltner_trailing"
START = "2010-01-01"
SELECTION_START = "2026-01-01"
END = "2026-06-17"
COST = 0.5
DAILY_CAP = 3


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


strategy = load_module("strategy157_for_160", SCRIPT_DIR / "157_intraday_king_keltner_rr2.py")
metrics = strategy.metrics


def completed_center(
    signal_bars: pd.DataFrame,
    execution_index: pd.DatetimeIndex,
    ma_length: int,
) -> np.ndarray:
    typical = (signal_bars["high"] + signal_bars["low"] + signal_bars["close"]) / 3.0
    center = typical.rolling(ma_length, min_periods=ma_length).mean()
    # A signal bar labelled T is not known until the next HTF bar starts.
    known_center = center.shift(1).reindex(execution_index, method="ffill")
    return known_center.to_numpy(float)


def restrict_entry_hours(entries: pd.DataFrame) -> pd.DataFrame:
    if entries.empty:
        return entries
    hour = entries["entry_time"].dt.hour
    return entries.loc[hour.between(8, 23)].sort_values("entry_time").reset_index(drop=True)


def simulate(
    df: pd.DataFrame,
    entries: pd.DataFrame,
    center: np.ndarray,
    risk_mult: float,
    max_hold_bars: int,
    daily_cap: int = DAILY_CAP,
) -> pd.DataFrame:
    if entries.empty:
        return pd.DataFrame()
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    rows = []
    active_exit_pos = -1
    day_counts: dict[str, int] = {}
    for row in entries.itertuples(index=False):
        pos = int(row.entry_pos)
        if pos <= active_exit_pos:
            continue
        if day_counts.get(row.day, 0) >= daily_cap:
            continue
        risk = max(2.0, float(row.atr) * risk_mult)
        if not math.isfinite(risk) or risk <= 0:
            continue
        hard_stop = (
            float(row.entry_price - risk)
            if row.direction == "long"
            else float(row.entry_price + risk)
        )
        end = min(len(df) - 1, pos + max_hold_bars)
        exit_pos, exit_price, reason = end, float(close[end]), "time_exit"
        last_exit_level = hard_stop
        for p in range(pos, end + 1):
            center_value = center[p]
            if row.direction == "long":
                exit_level = max(hard_stop, center_value) if math.isfinite(center_value) else hard_stop
                if low[p] <= exit_level:
                    exit_pos, exit_price = p, float(exit_level)
                    reason = "center_exit" if exit_level > hard_stop + 1e-10 else "hard_stop"
                    last_exit_level = float(exit_level)
                    break
            else:
                exit_level = min(hard_stop, center_value) if math.isfinite(center_value) else hard_stop
                if high[p] >= exit_level:
                    exit_pos, exit_price = p, float(exit_level)
                    reason = "center_exit" if exit_level < hard_stop - 1e-10 else "hard_stop"
                    last_exit_level = float(exit_level)
                    break
            last_exit_level = float(exit_level)
        active_exit_pos = exit_pos
        day_counts[row.day] = day_counts.get(row.day, 0) + 1
        gross = exit_price - row.entry_price if row.direction == "long" else row.entry_price - exit_price
        rows.append({
            **row._asdict(),
            "stop_price": hard_stop,
            "target_price": np.nan,
            "final_center_stop": last_exit_level,
            "risk_points": risk,
            "exit_time": df.index[exit_pos],
            "exit_price": exit_price,
            "gross_points": gross,
            "net_points": gross - COST,
            "r_net": (gross - COST) / risk,
            "exit_reason": reason,
            "hold_bars": exit_pos - pos + 1,
        })
    return pd.DataFrame(rows)


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


def audit_trades(trades: pd.DataFrame) -> None:
    if trades.empty:
        return
    expected = trades["gross_points"] - COST
    if not (expected - trades["net_points"]).abs().lt(1e-8).all():
        raise ValueError("Round-trip cost audit failed")
    if (trades["exit_time"] < trades["entry_time"]).any():
        raise ValueError("Exit precedes entry")
    if trades.groupby("day").size().max() > DAILY_CAP:
        raise ValueError("Daily cap audit failed")
    if not trades["entry_time"].dt.hour.between(8, 23).all():
        raise ValueError("Entry-hour audit failed")


def main() -> None:
    df = strategy.prepare()
    signal_cache = {tf: strategy.resample_signal_bars(df, tf) for tf in ["30min", "1h"]}
    center_cache: dict[tuple[str, int], np.ndarray] = {}
    rows = []
    best = None
    for timeframe in ["30min", "1h"]:
        for ma_length in [20, 40, 60]:
            center = completed_center(signal_cache[timeframe], df.index, ma_length)
            center_cache[(timeframe, ma_length)] = center
            for atr_length in [20, 40]:
                for band_mult in [0.5, 1.0]:
                    entries = strategy.make_entries(
                        df, signal_cache[timeframe], timeframe, ma_length,
                        atr_length, band_mult, SELECTION_START, END,
                    )
                    entries = restrict_entry_hours(entries)
                    for risk_mult in [1.0, 1.5, 2.0]:
                        for hold in [288, 576, 1440]:
                            trades = simulate(df, entries, center, risk_mult, hold)
                            row = {
                                "timeframe": timeframe, "ma_length": ma_length,
                                "atr_length": atr_length, "band_mult": band_mult,
                                "risk_mult": risk_mult, "max_hold_bars": hold,
                            }
                            row.update(selection_metrics(trades))
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
            "# Intraday King Keltner Trailing\n\nNo 2026 candidate passed.\n", encoding="utf-8",
        )
        print(sweep.head(20).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    tf = str(best["timeframe"])
    ma_length = int(best["ma_length"])
    entries = strategy.make_entries(
        df, signal_cache[tf], tf, ma_length, int(best["atr_length"]),
        float(best["band_mult"]), START, END,
    )
    entries = restrict_entry_hours(entries)
    fixed = simulate(
        df, entries, center_cache[(tf, ma_length)],
        float(best["risk_mult"]), int(best["max_hold_bars"]),
    )
    audit_trades(fixed)
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
    metrics.breakdown(sample, "month").round(4).to_csv(
        OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig",
    )
    metrics.breakdown(full, "year").round(4).to_csv(
        OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig",
    )
    chunk_passes = int(result.loc[result["period"] == "3y_chunk", "performance_pass"].sum())
    full_performance = bool(result.loc[result["period"] == "full", "performance_pass"].iloc[0])
    final = (
        "PASSED" if full_performance and chunk_passes == 6
        else ("CONDITIONAL_PASS" if full_performance else "REJECTED")
    )
    keys = ["timeframe", "ma_length", "atr_length", "band_mult", "risk_mult", "max_hold_bars"]
    report = [
        "# Intraday King Keltner Trailing", "",
        "- Trend: completed intraday typical-price SMA slope",
        "- Entry: next HTF bar stop at center plus/minus ATR channel, KST 08:00-23:59",
        "- Exit: initial ATR stop followed by the latest completed HTF center line",
        "- Execution: 5m adverse-stop first, one position, daily cap 3, round-trip cost 0.5",
        "- Important: this is a variable-R trend exit, not the fixed 2R model", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "Parameters are selected on 2026 and remain fixed in all historical slices.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
