# -*- coding: utf-8 -*-
"""Test 5m three-candle wickless momentum entry signals on Gold.

Entry logic only:
    long: 3 long bullish candles with short/no lower wicks.
    short: 3 long bearish candles with short/no upper wicks.

Because no stop/target was specified, this script evaluates forward returns
after fixed horizons instead of changing the existing grid strategy.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gold_data_prep as prep  # noqa: E402


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "result" / "three_candle_momentum_5m"

TIMEFRAME = "5m"
HORIZONS = [3, 6, 12, 24]

# Parameterized interpretation of "long candle" and "short/no wick".
BODY_RATIO_MIN = 0.70
SHORT_WICK_RATIO_MAX = 0.15
RANGE_LOOKBACK = 20
RANGE_MULTIPLIER = 1.20
ALLOW_OVERLAP = False


def _round_report(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(3)
    return out


def add_candle_shape_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    candle_range = out["high"] - out["low"]
    body = (out["close"] - out["open"]).abs()
    upper_wick = out["high"] - out[["open", "close"]].max(axis=1)
    lower_wick = out[["open", "close"]].min(axis=1) - out["low"]

    out["candle_range"] = candle_range
    out["body"] = body
    out["upper_wick"] = upper_wick
    out["lower_wick"] = lower_wick
    out["body_ratio"] = body / candle_range.replace(0, pd.NA)
    out["upper_wick_ratio"] = upper_wick / candle_range.replace(0, pd.NA)
    out["lower_wick_ratio"] = lower_wick / candle_range.replace(0, pd.NA)
    out["prior_avg_range_20"] = candle_range.shift(1).rolling(RANGE_LOOKBACK, min_periods=RANGE_LOOKBACK).mean()
    out["is_long_range_candle"] = candle_range >= out["prior_avg_range_20"] * RANGE_MULTIPLIER

    out["bullish_short_lower_wick_long_candle"] = (
        (out["close"] > out["open"])
        & out["is_long_range_candle"]
        & (out["body_ratio"] >= BODY_RATIO_MIN)
        & (out["lower_wick_ratio"] <= SHORT_WICK_RATIO_MAX)
    ).fillna(False)
    out["bearish_short_upper_wick_long_candle"] = (
        (out["close"] < out["open"])
        & out["is_long_range_candle"]
        & (out["body_ratio"] >= BODY_RATIO_MIN)
        & (out["upper_wick_ratio"] <= SHORT_WICK_RATIO_MAX)
    ).fillna(False)
    return out


def detect_three_candle_signals(df: pd.DataFrame, allow_overlap=ALLOW_OVERLAP) -> pd.DataFrame:
    out = add_candle_shape_columns(df)
    bull = out["bullish_short_lower_wick_long_candle"]
    bear = out["bearish_short_upper_wick_long_candle"]

    long_signal = bull & bull.shift(1).fillna(False) & bull.shift(2).fillna(False)
    short_signal = bear & bear.shift(1).fillna(False) & bear.shift(2).fillna(False)
    if not allow_overlap:
        long_signal = long_signal & ~bull.shift(3).fillna(False)
        short_signal = short_signal & ~bear.shift(3).fillna(False)

    out["three_bullish_momentum_signal"] = long_signal
    out["three_bearish_momentum_signal"] = short_signal
    return out


def build_signal_events(df: pd.DataFrame) -> pd.DataFrame:
    idx = df.index
    rows = []
    for direction, signal_col in [
        ("long", "three_bullish_momentum_signal"),
        ("short", "three_bearish_momentum_signal"),
    ]:
        signal_positions = [i for i, flag in enumerate(df[signal_col].to_numpy()) if bool(flag)]
        for signal_pos in signal_positions:
            entry_pos = signal_pos + 1
            if entry_pos >= len(df):
                continue
            row = {
                "direction": direction,
                "signal_time": idx[signal_pos],
                "entry_time": idx[entry_pos],
                "entry_price": float(df["open"].iloc[entry_pos]),
                "session": df["session"].iloc[entry_pos] if "session" in df.columns else "unknown",
                "timeframe": TIMEFRAME,
                "signal_candle_close": float(df["close"].iloc[signal_pos]),
                "signal_candle_range": float(df["candle_range"].iloc[signal_pos]),
                "signal_body_ratio": float(df["body_ratio"].iloc[signal_pos]),
                "signal_upper_wick_ratio": float(df["upper_wick_ratio"].iloc[signal_pos]),
                "signal_lower_wick_ratio": float(df["lower_wick_ratio"].iloc[signal_pos]),
            }
            rows.append(row)
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def add_forward_outcomes(df: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    idx = df.index
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    out = events.copy()

    for horizon in HORIZONS:
        pnl_values = []
        mfe_values = []
        mae_values = []
        exit_times = []
        for _, event in out.iterrows():
            entry_pos = idx.searchsorted(event["entry_time"])
            exit_pos = entry_pos + horizon - 1
            if entry_pos >= len(df) or exit_pos >= len(df):
                pnl_values.append(math.nan)
                mfe_values.append(math.nan)
                mae_values.append(math.nan)
                exit_times.append(pd.NaT)
                continue
            entry_price = float(event["entry_price"])
            hi = float(highs[entry_pos:exit_pos + 1].max())
            lo = float(lows[entry_pos:exit_pos + 1].min())
            exit_close = float(closes[exit_pos])
            if event["direction"] == "long":
                pnl = exit_close - entry_price
                mfe = hi - entry_price
                mae = entry_price - lo
            else:
                pnl = entry_price - exit_close
                mfe = entry_price - lo
                mae = hi - entry_price
            pnl_values.append(pnl)
            mfe_values.append(max(0.0, mfe))
            mae_values.append(max(0.0, mae))
            exit_times.append(idx[exit_pos])

        out["exit_time_%sb" % horizon] = exit_times
        out["pnl_points_%sb" % horizon] = pnl_values
        out["mfe_points_%sb" % horizon] = mfe_values
        out["mae_points_%sb" % horizon] = mae_values
        out["win_%sb" % horizon] = pd.Series(pnl_values) > 0
    return out


def _profit_factor(pnl: pd.Series) -> float:
    pnl = pd.to_numeric(pnl, errors="coerce").dropna()
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    if gross_loss == 0:
        return math.inf
    return float(gross_profit / gross_loss)


def summarize_forward_outcomes(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    by_session_rows = []
    by_year_rows = []

    def summarize_group(group: pd.DataFrame, horizon: int) -> dict:
        pnl = pd.to_numeric(group["pnl_points_%sb" % horizon], errors="coerce").dropna()
        if pnl.empty:
            return {
                "signals": 0,
                "win_rate": math.nan,
                "expectancy_points": math.nan,
                "median_pnl_points": math.nan,
                "profit_factor": math.nan,
                "avg_mfe_points": math.nan,
                "avg_mae_points": math.nan,
            }
        return {
            "signals": int(len(pnl)),
            "win_rate": float((pnl > 0).mean()),
            "expectancy_points": float(pnl.mean()),
            "median_pnl_points": float(pnl.median()),
            "profit_factor": _profit_factor(pnl),
            "avg_mfe_points": float(pd.to_numeric(group["mfe_points_%sb" % horizon], errors="coerce").mean()),
            "avg_mae_points": float(pd.to_numeric(group["mae_points_%sb" % horizon], errors="coerce").mean()),
        }

    events = events.copy()
    events["year"] = pd.DatetimeIndex(events["entry_time"]).tz_convert(prep.KST).year

    for horizon in HORIZONS:
        for direction, group in events.groupby("direction", sort=True):
            row = {"direction": direction, "horizon_bars": horizon}
            row.update(summarize_group(group, horizon))
            summary_rows.append(row)
        combined = {"direction": "combined", "horizon_bars": horizon}
        combined.update(summarize_group(events, horizon))
        summary_rows.append(combined)

        for (direction, session), group in events.groupby(["direction", "session"], sort=True):
            row = {"direction": direction, "session": session, "horizon_bars": horizon}
            row.update(summarize_group(group, horizon))
            by_session_rows.append(row)

        for (direction, year), group in events.groupby(["direction", "year"], sort=True):
            row = {"direction": direction, "year": int(year), "horizon_bars": horizon}
            row.update(summarize_group(group, horizon))
            by_year_rows.append(row)

    return (
        _round_report(pd.DataFrame(summary_rows)),
        _round_report(pd.DataFrame(by_session_rows)),
        _round_report(pd.DataFrame(by_year_rows)),
    )


def run() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / "xauusd_5m_2010-01-01_2026-06-16.csv"
    df = prep.load_gold_data(filepath, timeframe=TIMEFRAME)
    df = prep.assign_session(df)
    df = detect_three_candle_signals(df, allow_overlap=ALLOW_OVERLAP)
    events = build_signal_events(df)
    events = add_forward_outcomes(df, events)
    summary, by_session, by_year = summarize_forward_outcomes(events)

    events.to_csv(OUTPUT_DIR / "three_candle_momentum_events.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "three_candle_momentum_summary.csv", index=False, encoding="utf-8-sig")
    by_session.to_csv(OUTPUT_DIR / "three_candle_momentum_by_session.csv", index=False, encoding="utf-8-sig")
    by_year.to_csv(OUTPUT_DIR / "three_candle_momentum_by_year.csv", index=False, encoding="utf-8-sig")

    print("")
    print("=== THREE CANDLE MOMENTUM 5M: PARAMETERS ===")
    print("body_ratio_min=%s short_wick_ratio_max=%s range_lookback=%s range_multiplier=%s allow_overlap=%s" % (
        BODY_RATIO_MIN,
        SHORT_WICK_RATIO_MAX,
        RANGE_LOOKBACK,
        RANGE_MULTIPLIER,
        ALLOW_OVERLAP,
    ))
    print("")
    print("=== SUMMARY ===")
    print(summary.to_string(index=False))
    print("")
    print("=== BY SESSION, 12 BARS ===")
    print(by_session[by_session["horizon_bars"] == 12].to_string(index=False))
    print("")
    print("WROTE:", OUTPUT_DIR)
    return {"events": events, "summary": summary, "by_session": by_session, "by_year": by_year}


if __name__ == "__main__":
    run()
