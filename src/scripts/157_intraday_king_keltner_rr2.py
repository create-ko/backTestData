# -*- coding: utf-8 -*-
"""Intraday King Keltner trend breakout with fixed 2R and 5m execution."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "intraday_king_keltner_rr2"
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


base = load_module("base100_for_157", SCRIPT_DIR / "100_strategy2_grid_multitimeframe_month_filter.py")
metrics = load_module("metrics144_for_157", SCRIPT_DIR / "144_bb20_rr2_daily2_validation.py")


def prepare() -> pd.DataFrame:
    df = base.load_tf("5m").copy()
    df["day"] = df.index.tz_convert("Asia/Seoul").date.astype(str)
    return df


def resample_signal_bars(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    bars = df[["open", "high", "low", "close", "volume"]].resample(
        timeframe, label="left", closed="left",
    ).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"])
    return bars


def true_range(frame: pd.DataFrame) -> pd.Series:
    previous_close = frame["close"].shift(1)
    return pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - previous_close).abs(),
        (frame["low"] - previous_close).abs(),
    ], axis=1).max(axis=1)


def make_entries(
    execution: pd.DataFrame,
    signal_bars: pd.DataFrame,
    timeframe: str,
    ma_length: int,
    atr_length: int,
    band_mult: float,
    start: str,
    end: str,
) -> pd.DataFrame:
    typical = (signal_bars["high"] + signal_bars["low"] + signal_bars["close"]) / 3.0
    center = typical.rolling(ma_length, min_periods=ma_length).mean()
    atr = true_range(signal_bars).rolling(atr_length, min_periods=atr_length).mean()
    direction = np.where(center > center.shift(1), 1, np.where(center < center.shift(1), -1, 0))
    level = np.where(direction == 1, center + atr * band_mult, center - atr * band_mult)
    signal = pd.DataFrame({"direction": direction, "level": level, "atr": atr}, index=signal_bars.index).dropna()
    start_ts = pd.Timestamp(start, tz="Asia/Seoul")
    end_ts = pd.Timestamp(end, tz="Asia/Seoul")
    offset = pd.tseries.frequencies.to_offset(timeframe)
    signal = signal[(signal.index >= start_ts - offset) & (signal.index < end_ts - offset)]
    exec_index = execution.index
    open_ = execution["open"].to_numpy(float)
    high = execution["high"].to_numpy(float)
    low = execution["low"].to_numpy(float)
    rows = []
    for ts, row in signal.iterrows():
        next_start = ts + offset
        next_end = next_start + offset
        if next_start < start_ts or next_start >= end_ts:
            continue
        left = int(exec_index.searchsorted(next_start, side="left"))
        right = int(exec_index.searchsorted(next_end, side="left"))
        if left >= right or left >= len(execution):
            continue
        price = float(row["level"])
        if int(row["direction"]) == 1:
            hits = np.flatnonzero(high[left:right] >= price)
        else:
            hits = np.flatnonzero(low[left:right] <= price)
        if len(hits) == 0:
            continue
        pos = left + int(hits[0])
        if int(row["direction"]) == 1:
            entry_price = max(price, float(open_[pos]))
            direction_name = "long"
        else:
            entry_price = min(price, float(open_[pos]))
            direction_name = "short"
        entry_time = exec_index[pos]
        rows.append({
            "entry_pos": pos,
            "entry_time": entry_time,
            "entry_price": entry_price,
            "direction": direction_name,
            "signal_time": ts,
            "channel_level": price,
            "atr": float(row["atr"]),
            "day": entry_time.date().isoformat(),
            "session": str(execution["session"].iloc[pos]),
            "year": int(entry_time.year),
            "month": entry_time.strftime("%Y-%m"),
        })
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def simulate(
    df: pd.DataFrame,
    entries: pd.DataFrame,
    risk_mult: float,
    max_hold_bars: int,
    daily_cap: int = 3,
) -> pd.DataFrame:
    if entries.empty:
        return pd.DataFrame()
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    rows = []
    active_exit = None
    day_counts = {}
    for row in entries.itertuples(index=False):
        if active_exit is not None and row.entry_time < active_exit:
            continue
        if day_counts.get(row.day, 0) >= daily_cap:
            continue
        risk = max(2.0, float(row.atr) * risk_mult)
        if not math.isfinite(risk) or risk <= 0:
            continue
        if row.direction == "long":
            stop = float(row.entry_price - risk)
            target = float(row.entry_price + 2.0 * risk)
        else:
            stop = float(row.entry_price + risk)
            target = float(row.entry_price - 2.0 * risk)
        pos = int(row.entry_pos)
        end = min(len(df) - 1, pos + max_hold_bars)
        exit_pos, exit_price, reason = end, float(close[end]), "time_exit"
        for p in range(pos, end + 1):
            if row.direction == "long":
                if low[p] <= stop:
                    exit_pos, exit_price, reason = p, stop, "stop"
                    break
                if high[p] >= target:
                    exit_pos, exit_price, reason = p, target, "target_2r"
                    break
            else:
                if high[p] >= stop:
                    exit_pos, exit_price, reason = p, stop, "stop"
                    break
                if low[p] <= target:
                    exit_pos, exit_price, reason = p, target, "target_2r"
                    break
        active_exit = df.index[exit_pos]
        day_counts[row.day] = day_counts.get(row.day, 0) + 1
        gross = exit_price - row.entry_price if row.direction == "long" else row.entry_price - exit_price
        rows.append({
            **row._asdict(),
            "stop_price": stop, "target_price": target, "risk_points": risk,
            "exit_time": active_exit, "gross_points": gross,
            "net_points": gross - COST, "r_net": (gross - COST) / risk,
            "exit_reason": reason, "hold_bars": exit_pos - pos + 1,
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
        "trades": len(trades), "active_days": trades["day"].nunique(),
        "trades_per_day": len(trades) / 142,
        "net_points": float(pnl.sum()),
        "profit_factor": metrics.profit_factor(pnl),
        "max_drawdown": metrics.max_drawdown(pnl),
        "win_rate": float((pnl > 0).mean() * 100),
        "positive_month_rate": float((monthly > 0).mean() * 100),
    }


def main() -> None:
    df = prepare()
    signal_cache = {tf: resample_signal_bars(df, tf) for tf in ["30min", "1h"]}
    entry_cache = {}
    rows = []
    best = None
    for timeframe in ["30min", "1h"]:
        for ma_length in [20, 40, 60]:
            for atr_length in [20, 40]:
                for band_mult in [0.5, 1.0]:
                    entries = make_entries(
                        df, signal_cache[timeframe], timeframe, ma_length,
                        atr_length, band_mult, SELECTION_START, END,
                    )
                    entry_cache[(timeframe, ma_length, atr_length, band_mult)] = entries
                    for risk_mult in [1.0, 1.5, 2.0]:
                        for hold in [24, 72, 144]:
                            trades = simulate(df, entries, risk_mult, hold)
                            row = {
                                "timeframe": timeframe, "ma_length": ma_length,
                                "atr_length": atr_length, "band_mult": band_mult,
                                "risk_mult": risk_mult, "max_hold_bars": hold,
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
        (OUTPUT / "REPORT.md").write_text("# Intraday King Keltner RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8")
        print(sweep.head(20).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    tf = str(best["timeframe"])
    entries = make_entries(
        df, signal_cache[tf], tf, int(best["ma_length"]), int(best["atr_length"]),
        float(best["band_mult"]), START, END,
    )
    fixed = simulate(df, entries, float(best["risk_mult"]), int(best["max_hold_bars"]))
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
    keys = ["timeframe", "ma_length", "atr_length", "band_mult", "risk_mult", "max_hold_bars"]
    report = [
        "# Intraday King Keltner RR2", "",
        "- Trend: completed intraday typical-price SMA slope",
        "- Entry: next signal-bar stop at center plus/minus ATR channel",
        "- Exit: ATR risk with 2-point floor, exact 2R, 0.5 cost, 5m stop-first execution",
        "- Controls: one position at a time and at most three entries per KST day", "",
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
