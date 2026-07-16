# -*- coding: utf-8 -*-
"""Intraday candle RR2 entries only during a completed daily King Keltner regime."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_king_regime_intraday_candle_rr2"
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


intraday = load_module("intraday157_for_169", SCRIPT_DIR / "157_intraday_king_keltner_rr2.py")
daily = load_module("daily167_for_169", SCRIPT_DIR / "167_daily_king_keltner_2026_selection.py")
metrics = intraday.metrics


def daily_trades() -> pd.DataFrame:
    frame = daily.daily_frame()
    center = frame["typical"].rolling(60, min_periods=60).mean().to_numpy(float)
    atr = frame["tr"].rolling(40, min_periods=40).mean().to_numpy(float)
    return daily.simulate(frame, center, atr, 1.0)


def completed_regime(index: pd.DatetimeIndex, trades: pd.DataFrame) -> pd.Series:
    regime = pd.Series(0, index=index, dtype="int8")
    for trade in trades.itertuples(index=False):
        # The daily entry bar is not used because its intraday fill time is unknown.
        start = (trade.entry_time + pd.Timedelta(days=1)).tz_convert("Asia/Seoul")
        end = trade.exit_time.tz_convert("Asia/Seoul")
        if end <= start:
            continue
        direction = 1 if trade.direction == "long" else -1
        regime.loc[(regime.index >= start) & (regime.index < end)] = direction
    return regime


def signal_mask(bars: pd.DataFrame, ema: pd.Series, mode: str) -> tuple[pd.Series, pd.Series]:
    bullish = bars["close"] > bars["open"]
    bearish = bars["close"] < bars["open"]
    if mode == "reclaim":
        long_signal = bullish & (bars["close"] > ema) & (bars["close"].shift(1) <= ema.shift(1))
        short_signal = bearish & (bars["close"] < ema) & (bars["close"].shift(1) >= ema.shift(1))
    elif mode == "rejection":
        long_signal = bullish & (bars["low"] <= ema) & (bars["close"] > ema)
        short_signal = bearish & (bars["high"] >= ema) & (bars["close"] < ema)
    elif mode == "engulf":
        long_signal = bullish & bearish.shift(1).fillna(False) & (bars["close"] > bars["high"].shift(1)) & (bars["close"] > ema)
        short_signal = bearish & bullish.shift(1).fillna(False) & (bars["close"] < bars["low"].shift(1)) & (bars["close"] < ema)
    elif mode == "aligned":
        long_signal = bullish & (bars["close"] > ema)
        short_signal = bearish & (bars["close"] < ema)
    else:
        raise ValueError(mode)
    return long_signal.fillna(False), short_signal.fillna(False)


def make_entries(
    execution: pd.DataFrame,
    bars: pd.DataFrame,
    regime: pd.Series,
    timeframe: str,
    ema_length: int,
    mode: str,
    session_mode: str,
    start: str,
    end: str,
) -> pd.DataFrame:
    ema = bars["close"].ewm(span=ema_length, adjust=False, min_periods=ema_length).mean()
    atr = intraday.true_range(bars).rolling(14, min_periods=14).mean()
    long_signal, short_signal = signal_mask(bars, ema, mode)
    direction = np.where((regime == 1) & long_signal, 1, np.where((regime == -1) & short_signal, -1, 0))
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
        pos = int(execution.index.searchsorted(entry_time, side="left"))
        if pos >= len(execution) or execution.index[pos] != entry_time:
            continue
        session = str(execution["session"].iloc[pos])
        if session_mode == "asia" and session != "asia":
            continue
        if session_mode == "no_us" and session == "us_open":
            continue
        rows.append({
            "entry_pos": pos,
            "entry_time": entry_time,
            "entry_price": float(execution["open"].iloc[pos]),
            "direction": "long" if int(signal["direction"]) == 1 else "short",
            "signal_time": ts,
            "atr": float(signal["atr"]),
            "day": entry_time.date().isoformat(),
            "session": session,
            "year": int(entry_time.year),
            "month": entry_time.strftime("%Y-%m"),
        })
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def main() -> None:
    df = intraday.prepare()
    regime_trades = daily_trades()
    timeframe_grid = ["15min", "30min"]
    bar_cache = {tf: intraday.resample_signal_bars(df, tf) for tf in timeframe_grid}
    regime_cache = {tf: completed_regime(bar_cache[tf].index, regime_trades) for tf in timeframe_grid}
    rows = []
    best = None
    for timeframe in timeframe_grid:
        for ema_length in [10, 20, 40]:
            for mode in ["reclaim", "rejection", "engulf", "aligned"]:
                for session_mode in ["all", "no_us", "asia"]:
                    entries = make_entries(
                        df, bar_cache[timeframe], regime_cache[timeframe], timeframe,
                        ema_length, mode, session_mode, SELECTION_START, END,
                    )
                    for risk_mult in [1.0, 1.5, 2.0]:
                        for hold in [72, 144]:
                            trades = intraday.simulate(df, entries, risk_mult, hold)
                            row = {
                                "timeframe": timeframe, "ema_length": ema_length,
                                "signal_mode": mode, "session_mode": session_mode,
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
            "# Daily King Regime Intraday Candle RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8",
        )
        print(sweep.head(30).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    tf = str(best["timeframe"])
    entries = make_entries(
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
        "# Daily King Regime Intraday Candle RR2", "",
        "- Regime: gap-aware daily HLC3 SMA60 / simple TR40 King Keltner position",
        "- Regime timing: active only after the daily entry bar has fully completed",
        "- Trigger: completed intraday candle pattern relative to its EMA",
        "- Entry: next 5m open; exit: ATR risk with 2-point floor and exact 2R",
        "- Controls: adverse-stop first, KST 08:00-23:59, one position, cap 3/day, cost 0.5", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "Intraday parameters were selected on 2026 and frozen historically.",
        "Research caveat: the SMA60 daily regime was discovered during full-history exploration.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
