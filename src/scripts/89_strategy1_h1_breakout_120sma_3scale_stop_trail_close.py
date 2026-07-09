# -*- coding: utf-8 -*-
"""Strategy 1 variant: H1 double-BB breakout + lower-TF 120SMA retest.

Rules:
- H1 double-BB breakout is the setup trigger.
- Entry timeframes: 1m, 2m, 5m, 10m.
- First entry is the first lower-TF 120SMA touch after the H1 breakout closes.
- Two additional entries are placed every 10 points adverse, for 3 total entries.
    long:  E1=120SMA, E2=E1-10P, E3=E1-20P, stop=E3-5P
    short: E1=120SMA, E2=E1+10P, E3=E1+20P, stop=E3+5P
- Profit exit: after bar close recovers 5P beyond the average entry, a 5P
  trailing stop is updated at each bar close. The first armed trailing stop is
  effectively breakeven. The newly updated trailing stop is active from the
  next bar, avoiding same-bar look-ahead.

TODO: The user did not specify how long the post-breakout 120SMA retest remains
valid. This test keeps the prior first-pass default: wait up to 6 hours for the
first 120SMA touch. Once entered, there is no time-based exit; trades hold until
hard stop or trailing stop.
"""
from __future__ import annotations

import contextlib
import io
import math
import sys
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gold_data_prep as prep  # noqa: E402


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OUTPUT_DIR = (
    Path(__file__).resolve().parents[2]
    / "result"
    / "strategy1_h1_breakout_120sma_ktr_grid_cost05_entry0830_2330_no_time_exit"
)

ENTRY_TFS = ["1m", "2m", "5m", "10m"]
GRID_METHODS = ["fixed_10p", "session_ktr"]
SMA_LEN = 120
ENTRY_SPACING_POINTS = 10.0
MAX_ENTRIES = 3
STOP_BEYOND_THIRD_POINTS = 5.0
TRAIL_POINTS = 5.0
MAX_WAIT_HOURS = 6
ROUND_TRIP_COST_POINTS_PER_UNIT = 0.50
KST = ZoneInfo("Asia/Seoul")
ENTRY_START_MINUTE = 8 * 60 + 30
ENTRY_END_MINUTE = 23 * 60 + 30


def _quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _round_report(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(3)
    return out


def _entry_time_allowed(ts: pd.Timestamp) -> bool:
    kst_ts = ts.tz_convert("Asia/Seoul") if ts.tzinfo is not None else ts.tz_localize("Asia/Seoul")
    minutes = kst_ts.hour * 60 + kst_ts.minute
    return ENTRY_START_MINUTE <= minutes < ENTRY_END_MINUTE


def _daterange(start_day: date, end_day: date):
    cur = start_day
    while cur <= end_day:
        yield cur
        cur += timedelta(days=1)


def _kst_fixed_timestamp(day: date, hour: int, minute: int) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, dtime(hour, minute), tzinfo=KST))


def _local_reset_to_kst_timestamp(day: date, tz_name: str, hour: int, minute: int) -> pd.Timestamp:
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(tz_name))
    return pd.Timestamp(local.astimezone(KST))


def build_session_ktr_table(df10: pd.DataFrame) -> pd.DataFrame:
    """Build session KTR from first completed hour after session reset.

    This follows the existing session KTR convention in this repo:
    Asia = 08:00 KST, Europe = 08:00 London, NewYork = 09:30 New York.
    Non-Asia KTR is the first-hour high-low. Asia is capped by 25% of the
    recent 10 weekday daily ranges, matching the older session KTR script.
    """
    if df10.empty:
        return pd.DataFrame(columns=["reset_time", "next_reset_time", "ktr_session", "session_ktr"])

    first_day = df10.index[0].date() - timedelta(days=2)
    last_day = df10.index[-1].date() + timedelta(days=2)
    resets = []
    for day in _daterange(first_day, last_day):
        resets.append((_kst_fixed_timestamp(day, 8, 0), "Asia"))
        resets.append((_local_reset_to_kst_timestamp(day, "Europe/London", 8, 0), "Europe"))
        resets.append((_local_reset_to_kst_timestamp(day, "America/New_York", 9, 30), "NewYork"))
    resets = sorted(set(resets), key=lambda x: x[0])

    daily = df10[["high", "low", "close"]].copy()
    daily["_day"] = daily.index.date
    daily_ranges = daily.groupby("_day").agg({"high": "max", "low": "min", "close": "last"})
    daily_ranges["range"] = daily_ranges["high"] - daily_ranges["low"]
    daily_ranges["prev_close"] = daily_ranges["close"].shift(1)
    weekday_days = [d for d in daily_ranges.index if pd.Timestamp(d).weekday() < 5]

    rows = []
    for i in range(len(resets) - 1):
        reset_time, name = resets[i]
        next_reset_time = resets[i + 1][0]
        if reset_time < df10.index[0] or reset_time + pd.Timedelta(hours=1) >= df10.index[-1]:
            continue
        obs = df10.loc[(df10.index >= reset_time) & (df10.index < reset_time + pd.Timedelta(hours=1))]
        if len(obs) != 6:
            continue
        raw = float(obs["high"].max() - obs["low"].min())
        session_ktr = raw
        asia_avg10 = math.nan
        asia_capped = False
        if name == "Asia":
            day = reset_time.date()
            prev_close = daily_ranges["prev_close"].get(day, math.nan)
            prior_days = [d for d in weekday_days if d < day]
            selected = prior_days[-10:]
            if len(selected) < 10 or pd.isna(prev_close):
                continue
            recent_ranges = daily_ranges.loc[selected, "range"]
            asia_avg10 = float(recent_ranges.mean())
            raw = max(float(obs["high"].iloc[0]), float(prev_close)) - min(float(obs["low"].iloc[0]), float(prev_close))
            session_ktr = min(raw, 0.25 * asia_avg10)
            asia_capped = session_ktr < raw
        if session_ktr <= 0 or pd.isna(session_ktr):
            continue
        rows.append({
            "reset_time": reset_time,
            "next_reset_time": next_reset_time,
            "ktr_session": name,
            "raw_session_ktr": raw,
            "session_ktr": float(session_ktr),
            "asia_avg10_range": asia_avg10,
            "asia_ktr_capped": asia_capped,
        })

    return pd.DataFrame(rows).sort_values("reset_time").reset_index(drop=True)


def attach_session_ktr(df: pd.DataFrame, ktr_table: pd.DataFrame) -> pd.DataFrame:
    if ktr_table.empty:
        out = df.copy()
        out["ktr_session"] = pd.NA
        out["session_ktr"] = np.nan
        return out
    def _to_ns(values) -> np.ndarray:
        raw = pd.to_datetime(values, utc=True).astype("int64").to_numpy()
        finite = raw[~pd.isna(raw)]
        if len(finite) == 0:
            return raw
        scale_probe = np.nanmax(np.abs(finite))
        if scale_probe < 10**12:
            return raw * 1_000_000_000
        if scale_probe < 10**15:
            return raw * 1_000_000
        if scale_probe < 10**18:
            return raw * 1_000
        return raw

    left = df.reset_index().rename(columns={df.index.name or "index": "datetime"})
    left["_ts_ns"] = _to_ns(left["datetime"])
    right = ktr_table.sort_values("reset_time").copy()
    right["_reset_ns"] = _to_ns(right["reset_time"])
    right["_next_reset_ns"] = _to_ns(right["next_reset_time"])
    merged = pd.merge_asof(
        left.sort_values("_ts_ns"),
        right,
        left_on="_ts_ns",
        right_on="_reset_ns",
        direction="backward",
    )
    valid = merged["_ts_ns"] < merged["_next_reset_ns"]
    merged.loc[~valid, ["ktr_session", "raw_session_ktr", "session_ktr", "asia_avg10_range", "asia_ktr_capped"]] = pd.NA
    merged = merged.drop(columns=["_ts_ns", "_reset_ns", "_next_reset_ns"], errors="ignore")
    merged = merged.set_index("datetime")
    merged.index.name = df.index.name
    return merged


def make_h1_breakout_signals(df10: pd.DataFrame) -> pd.DataFrame:
    h1 = (
        df10[["open", "high", "low", "close", "volume"]]
        .resample("1h", label="left", closed="left")
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        .dropna(subset=["open", "high", "low", "close"])
    )
    h1.attrs["timeframe"] = "1h"
    h1 = prep.add_bollinger_bands(h1)
    h1["h1_bar_time"] = h1.index
    h1["h1_signal_time"] = h1.index + pd.Timedelta(hours=1)
    h1["h1_breakout_long"] = (
        (h1["close"] > h1["bb20_2_upper_close"])
        & (h1["close"] > h1["bb4_4_upper_open"])
    ).fillna(False)
    h1["h1_breakout_short"] = (
        (h1["close"] < h1["bb20_2_lower_close"])
        & (h1["close"] < h1["bb4_4_lower_open"])
    ).fillna(False)

    rows = []
    signals = h1[h1["h1_breakout_long"] | h1["h1_breakout_short"]]
    for _, row in signals.iterrows():
        if bool(row["h1_breakout_long"]):
            direction = "long"
        elif bool(row["h1_breakout_short"]):
            direction = "short"
        else:
            continue
        rows.append({
            "direction": direction,
            "h1_bar_time": row["h1_bar_time"],
            "h1_signal_time": row["h1_signal_time"],
            "h1_open": float(row["open"]),
            "h1_high": float(row["high"]),
            "h1_low": float(row["low"]),
            "h1_close": float(row["close"]),
        })
    return pd.DataFrame(rows).sort_values("h1_signal_time").reset_index(drop=True)


def load_entry_tf(timeframe: str) -> pd.DataFrame:
    path = DATA_DIR / ("xauusd_%s_2010-01-01_2026-06-16.csv" % timeframe)
    df = _quiet_call(prep.load_gold_data, path, timeframe=timeframe)
    df = prep.assign_session(df)
    df["sma120"] = df["close"].rolling(SMA_LEN, min_periods=SMA_LEN).mean()
    return df


def find_first_sma_touch(df: pd.DataFrame, signal: pd.Series) -> dict | None:
    direction = signal["direction"]
    start_time = signal["h1_signal_time"]
    end_time = start_time + pd.Timedelta(hours=MAX_WAIT_HOURS)
    window = df.loc[(df.index >= start_time) & (df.index < end_time)]
    if window.empty:
        return None

    for entry_time, bar in window.iterrows():
        sma = bar["sma120"]
        if pd.isna(sma):
            continue
        touched = bar["low"] <= sma if direction == "long" else bar["high"] >= sma
        if touched:
            if not _entry_time_allowed(entry_time):
                return None
            return {
                "entry_time": entry_time,
                "entry_1_price": float(sma),
                "session": bar["session"] if "session" in window.columns else "unknown",
            }
    return None


def find_first_sma_touch_fast(data: dict, signal: pd.Series) -> dict | None:
    direction = signal["direction"]
    idx = data["idx"]
    start_time = signal["h1_signal_time"]
    end_time = start_time + pd.Timedelta(hours=MAX_WAIT_HOURS)
    start_pos = idx.searchsorted(start_time)
    end_pos = idx.searchsorted(end_time)
    if start_pos >= end_pos:
        return None

    sma = data["sma"]
    if direction == "long":
        hits = np.where(data["low"][start_pos:end_pos] <= sma[start_pos:end_pos])[0]
    else:
        hits = np.where(data["high"][start_pos:end_pos] >= sma[start_pos:end_pos])[0]
    if len(hits) == 0:
        return None

    for offset in hits:
        pos = start_pos + int(offset)
        if not np.isnan(sma[pos]):
            if not _entry_time_allowed(idx[pos]):
                return None
            return {
                "entry_time": idx[pos],
                "entry_1_price": float(sma[pos]),
                "entry_pos": pos,
                "session": data["session"][pos],
                "ktr_session": data["ktr_session"][pos],
                "session_ktr": data["session_ktr"][pos],
            }
    return None


def _entry_levels(entry_1: float, direction: str, grid_step: float) -> list[float]:
    if direction == "long":
        return [entry_1 - i * grid_step for i in range(MAX_ENTRIES)]
    return [entry_1 + i * grid_step for i in range(MAX_ENTRIES)]


def _stop_price_from_levels(levels: list[float], direction: str) -> float:
    if direction == "long":
        return levels[-1] - STOP_BEYOND_THIRD_POINTS
    return levels[-1] + STOP_BEYOND_THIRD_POINTS


def resolve_scaled_trade(df: pd.DataFrame, signal: pd.Series, entry: dict) -> dict | None:
    direction = signal["direction"]
    entry_time = entry["entry_time"]
    start_pos = df.index.searchsorted(entry_time)
    if start_pos >= len(df):
        return None

    end_pos = len(df) - 1

    levels = _entry_levels(float(entry["entry_1_price"]), direction, ENTRY_SPACING_POINTS)
    hard_stop = _stop_price_from_levels(levels, direction)
    filled = [False] * MAX_ENTRIES
    fill_times = [pd.NaT] * MAX_ENTRIES
    fill_prices = []
    open_units = 0
    avg_entry = math.nan
    trail_stop = math.nan
    trailing_armed = False
    max_favorable_points = 0.0
    max_adverse_points = 0.0
    exit_reason = "open_at_data_end"
    exit_price = float(df["close"].iloc[end_pos])
    exit_time = df.index[end_pos]

    for pos in range(start_pos, end_pos + 1):
        bar_time = df.index[pos]
        hi = float(df["high"].iloc[pos])
        lo = float(df["low"].iloc[pos])
        close = float(df["close"].iloc[pos])

        for level_i, level in enumerate(levels):
            if filled[level_i]:
                continue
            hit = lo <= level if direction == "long" else hi >= level
            if hit:
                filled[level_i] = True
                fill_times[level_i] = bar_time
                fill_prices.append(level)
                open_units += 1
                avg_entry = sum(fill_prices) / len(fill_prices)

        if open_units == 0:
            continue

        if direction == "long":
            max_favorable_points = max(max_favorable_points, hi - avg_entry)
            max_adverse_points = max(max_adverse_points, avg_entry - lo)

            if lo <= hard_stop:
                exit_reason = "hard_stop_3rd_minus_5p"
                exit_price = hard_stop
                exit_time = bar_time
                break

            if trailing_armed and lo <= trail_stop:
                exit_reason = "close_trail_5p"
                exit_price = trail_stop
                exit_time = bar_time
                break

            if close >= avg_entry + TRAIL_POINTS:
                next_trail = close - TRAIL_POINTS
                if not trailing_armed:
                    trailing_armed = True
                    trail_stop = max(avg_entry, next_trail)
                else:
                    trail_stop = max(trail_stop, avg_entry, next_trail)
        else:
            max_favorable_points = max(max_favorable_points, avg_entry - lo)
            max_adverse_points = max(max_adverse_points, hi - avg_entry)

            if hi >= hard_stop:
                exit_reason = "hard_stop_3rd_plus_5p"
                exit_price = hard_stop
                exit_time = bar_time
                break

            if trailing_armed and hi >= trail_stop:
                exit_reason = "close_trail_5p"
                exit_price = trail_stop
                exit_time = bar_time
                break

            if close <= avg_entry - TRAIL_POINTS:
                next_trail = close + TRAIL_POINTS
                if not trailing_armed:
                    trailing_armed = True
                    trail_stop = min(avg_entry, next_trail)
                else:
                    trail_stop = min(trail_stop, avg_entry, next_trail)

        if pos == end_pos:
            exit_price = close

    if open_units == 0 or pd.isna(avg_entry):
        return None

    gross_points_per_unit = (exit_price - avg_entry) if direction == "long" else (avg_entry - exit_price)
    gross_points_total = gross_points_per_unit * open_units
    cost_points_total = ROUND_TRIP_COST_POINTS_PER_UNIT * open_units
    net_points_total = gross_points_total - cost_points_total

    return {
        "entry_1_price": levels[0],
        "entry_2_price": levels[1],
        "entry_3_price": levels[2],
        "entry_1_time": fill_times[0],
        "entry_2_time": fill_times[1],
        "entry_3_time": fill_times[2],
        "hard_stop_price": hard_stop,
        "filled_entries": int(open_units),
        "avg_entry": avg_entry,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_points_per_unit": gross_points_per_unit,
        "gross_points_total": gross_points_total,
        "cost_points_total": cost_points_total,
        "net_points_total": net_points_total,
        "net_10p": net_points_total / ENTRY_SPACING_POINTS,
        "mfe_points": max_favorable_points,
        "mae_points": max_adverse_points,
        "mfe_10p": max_favorable_points / ENTRY_SPACING_POINTS,
        "mae_10p": max_adverse_points / ENTRY_SPACING_POINTS,
        "hold_bars": int(df.index.searchsorted(exit_time) - start_pos + 1),
        "trailing_armed": bool(trailing_armed),
    }


def _first_true_pos(mask: np.ndarray, start_pos: int) -> int | None:
    hits = np.where(mask)[0]
    if len(hits) == 0:
        return None
    return start_pos + int(hits[0])


def resolve_scaled_trade_fast(data: dict, signal: pd.Series, entry: dict, grid_method: str) -> dict | None:
    direction = signal["direction"]
    idx = data["idx"]
    start_pos = int(entry["entry_pos"])
    if start_pos >= len(idx):
        return None

    if grid_method == "fixed_10p":
        grid_step = ENTRY_SPACING_POINTS
    elif grid_method == "session_ktr":
        grid_step = float(entry["session_ktr"])
    else:
        raise ValueError("unknown grid_method: %s" % grid_method)
    if pd.isna(grid_step) or grid_step <= 0:
        return None

    levels = _entry_levels(float(entry["entry_1_price"]), direction, grid_step)
    hard_stop = _stop_price_from_levels(levels, direction)
    filled = [False] * MAX_ENTRIES
    fill_times = [pd.NaT] * MAX_ENTRIES
    fill_prices = []
    open_units = 0
    avg_entry = math.nan
    trail_stop = math.nan
    trailing_armed = False
    max_favorable_points = 0.0
    max_adverse_points = 0.0
    exit_reason = "open_at_data_end"
    exit_price = float(data["close"][-1])
    exit_time = idx[-1]

    pos = start_pos
    last_pos = len(idx) - 1
    while pos <= last_pos:
        if open_units > 0 and not trailing_armed:
            if direction == "long":
                candidates = []
                if open_units < MAX_ENTRIES:
                    next_level = levels[open_units]
                    p = _first_true_pos(data["low"][pos:] <= next_level, pos)
                    if p is not None:
                        candidates.append(p)
                p = _first_true_pos(data["low"][pos:] <= hard_stop, pos)
                if p is not None:
                    candidates.append(p)
                p = _first_true_pos(data["close"][pos:] >= avg_entry + TRAIL_POINTS, pos)
                if p is not None:
                    candidates.append(p)
                if candidates:
                    pos = min(candidates)
                else:
                    pos = last_pos
            else:
                candidates = []
                if open_units < MAX_ENTRIES:
                    next_level = levels[open_units]
                    p = _first_true_pos(data["high"][pos:] >= next_level, pos)
                    if p is not None:
                        candidates.append(p)
                p = _first_true_pos(data["high"][pos:] >= hard_stop, pos)
                if p is not None:
                    candidates.append(p)
                p = _first_true_pos(data["close"][pos:] <= avg_entry - TRAIL_POINTS, pos)
                if p is not None:
                    candidates.append(p)
                if candidates:
                    pos = min(candidates)
                else:
                    pos = last_pos

        bar_time = idx[pos]
        hi = float(data["high"][pos])
        lo = float(data["low"][pos])
        close = float(data["close"][pos])

        for level_i, level in enumerate(levels):
            if filled[level_i]:
                continue
            hit = lo <= level if direction == "long" else hi >= level
            if hit:
                filled[level_i] = True
                fill_times[level_i] = bar_time
                fill_prices.append(level)
                open_units += 1
                avg_entry = sum(fill_prices) / len(fill_prices)

        if open_units == 0:
            pos += 1
            continue

        if direction == "long":
            max_favorable_points = max(max_favorable_points, hi - avg_entry)
            max_adverse_points = max(max_adverse_points, avg_entry - lo)

            if lo <= hard_stop:
                exit_reason = "hard_stop_3rd_minus_5p"
                exit_price = hard_stop
                exit_time = bar_time
                break

            if trailing_armed and lo <= trail_stop:
                exit_reason = "close_trail_5p"
                exit_price = trail_stop
                exit_time = bar_time
                break

            if close >= avg_entry + TRAIL_POINTS:
                next_trail = close - TRAIL_POINTS
                if not trailing_armed:
                    trailing_armed = True
                    trail_stop = max(avg_entry, next_trail)
                else:
                    trail_stop = max(trail_stop, avg_entry, next_trail)
        else:
            max_favorable_points = max(max_favorable_points, avg_entry - lo)
            max_adverse_points = max(max_adverse_points, hi - avg_entry)

            if hi >= hard_stop:
                exit_reason = "hard_stop_3rd_plus_5p"
                exit_price = hard_stop
                exit_time = bar_time
                break

            if trailing_armed and hi >= trail_stop:
                exit_reason = "close_trail_5p"
                exit_price = trail_stop
                exit_time = bar_time
                break

            if close <= avg_entry - TRAIL_POINTS:
                next_trail = close + TRAIL_POINTS
                if not trailing_armed:
                    trailing_armed = True
                    trail_stop = min(avg_entry, next_trail)
                else:
                    trail_stop = min(trail_stop, avg_entry, next_trail)

        if pos == last_pos:
            exit_price = close
        pos += 1

    if open_units == 0 or pd.isna(avg_entry):
        return None

    gross_points_per_unit = (exit_price - avg_entry) if direction == "long" else (avg_entry - exit_price)
    gross_points_total = gross_points_per_unit * open_units
    cost_points_total = ROUND_TRIP_COST_POINTS_PER_UNIT * open_units
    net_points_total = gross_points_total - cost_points_total

    return {
        "entry_1_price": levels[0],
        "entry_2_price": levels[1],
        "entry_3_price": levels[2],
        "entry_1_time": fill_times[0],
        "entry_2_time": fill_times[1],
        "entry_3_time": fill_times[2],
        "hard_stop_price": hard_stop,
        "filled_entries": int(open_units),
        "avg_entry": avg_entry,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_points_per_unit": gross_points_per_unit,
        "gross_points_total": gross_points_total,
        "cost_points_total": cost_points_total,
        "net_points_total": net_points_total,
        "net_10p": net_points_total / ENTRY_SPACING_POINTS,
        "net_grid_r": net_points_total / grid_step,
        "grid_method": grid_method,
        "grid_step_points": grid_step,
        "mfe_points": max_favorable_points,
        "mae_points": max_adverse_points,
        "mfe_10p": max_favorable_points / ENTRY_SPACING_POINTS,
        "mae_10p": max_adverse_points / ENTRY_SPACING_POINTS,
        "mfe_grid_r": max_favorable_points / grid_step,
        "mae_grid_r": max_adverse_points / grid_step,
        "hold_bars": int(idx.searchsorted(exit_time) - start_pos + 1),
        "trailing_armed": bool(trailing_armed),
    }


def build_trades(signals: pd.DataFrame, df: pd.DataFrame, entry_tf: str, grid_method: str) -> pd.DataFrame:
    data = {
        "idx": df.index,
        "open": df["open"].to_numpy(dtype=float),
        "high": df["high"].to_numpy(dtype=float),
        "low": df["low"].to_numpy(dtype=float),
        "close": df["close"].to_numpy(dtype=float),
        "sma": df["sma120"].to_numpy(dtype=float),
        "session": df["session"].astype(str).to_numpy(),
        "ktr_session": df["ktr_session"].astype(str).to_numpy(),
        "session_ktr": df["session_ktr"].to_numpy(dtype=float),
    }
    rows = []
    for _, signal in signals.iterrows():
        entry = find_first_sma_touch_fast(data, signal)
        if entry is None:
            continue
        result = resolve_scaled_trade_fast(data, signal, entry, grid_method)
        if result is None:
            continue
        row = signal.to_dict()
        row.update(entry)
        row.update(result)
        row.update({
            "entry_tf": entry_tf,
            "grid_method": grid_method,
            "sma_len": SMA_LEN,
            "stop_beyond_third_points": STOP_BEYOND_THIRD_POINTS,
            "trail_points": TRAIL_POINTS,
            "entry_time_filter": "08:30-23:30",
            "year": pd.Timestamp(entry["entry_time"]).year,
        })
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def profit_factor(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    gp = vals[vals > 0].sum()
    gl = abs(vals[vals < 0].sum())
    if gl == 0:
        return math.inf if gp > 0 else 0.0
    return float(gp / gl)


def max_drawdown(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").fillna(0.0)
    eq = vals.cumsum()
    dd = eq.cummax() - eq
    return float(dd.max()) if len(dd) else 0.0


def summarize_group(group: pd.DataFrame) -> dict:
    if group.empty:
        return {
            "trades": 0,
            "win_rate": math.nan,
            "expectancy_points_total": math.nan,
            "expectancy_10p": math.nan,
            "expectancy_grid_r": math.nan,
            "profit_factor": math.nan,
            "max_drawdown_points": math.nan,
            "cumulative_points": 0.0,
            "avg_filled_entries": math.nan,
            "stop_rate": math.nan,
            "trail_rate": math.nan,
            "open_at_data_end_rate": math.nan,
            "avg_mfe_10p": math.nan,
            "avg_mae_10p": math.nan,
            "avg_grid_step_points": math.nan,
        }
    pnl = pd.to_numeric(group["net_points_total"], errors="coerce")
    exit_reason = group["exit_reason"].astype(str)
    return {
        "trades": int(len(group)),
        "win_rate": float((pnl > 0).mean()),
        "expectancy_points_total": float(pnl.mean()),
        "expectancy_10p": float(pd.to_numeric(group["net_10p"], errors="coerce").mean()),
        "expectancy_grid_r": float(pd.to_numeric(group["net_grid_r"], errors="coerce").mean()),
        "profit_factor": profit_factor(pnl),
        "max_drawdown_points": max_drawdown(pnl),
        "cumulative_points": float(pnl.sum()),
        "avg_filled_entries": float(pd.to_numeric(group["filled_entries"], errors="coerce").mean()),
        "stop_rate": float(exit_reason.str.contains("hard_stop").mean()),
        "trail_rate": float((exit_reason == "close_trail_5p").mean()),
        "open_at_data_end_rate": float((exit_reason == "open_at_data_end").mean()),
        "avg_mfe_10p": float(pd.to_numeric(group["mfe_10p"], errors="coerce").mean()),
        "avg_mae_10p": float(pd.to_numeric(group["mae_10p"], errors="coerce").mean()),
        "avg_grid_step_points": float(pd.to_numeric(group["grid_step_points"], errors="coerce").mean()),
    }


def summarize(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    by_year_rows = []
    by_session_rows = []
    by_exit_rows = []
    by_fills_rows = []

    for key, group in trades.groupby(["grid_method", "entry_tf", "direction"], sort=True):
        row = {"grid_method": key[0], "entry_tf": key[1], "direction": key[2]}
        row.update(summarize_group(group))
        summary_rows.append(row)
    for key, group in trades.groupby(["grid_method", "entry_tf"], sort=True):
        row = {"grid_method": key[0], "entry_tf": key[1], "direction": "combined"}
        row.update(summarize_group(group))
        summary_rows.append(row)

    for key, group in trades.groupby(["grid_method", "entry_tf", "direction", "year"], sort=True):
        row = {"grid_method": key[0], "entry_tf": key[1], "direction": key[2], "year": int(key[3])}
        row.update(summarize_group(group))
        by_year_rows.append(row)

    for key, group in trades.groupby(["grid_method", "entry_tf", "direction", "session"], sort=True):
        row = {"grid_method": key[0], "entry_tf": key[1], "direction": key[2], "session": key[3]}
        row.update(summarize_group(group))
        by_session_rows.append(row)

    for key, group in trades.groupby(["grid_method", "entry_tf", "direction", "exit_reason"], sort=True):
        row = {"grid_method": key[0], "entry_tf": key[1], "direction": key[2], "exit_reason": key[3]}
        row.update(summarize_group(group))
        by_exit_rows.append(row)

    for key, group in trades.groupby(["grid_method", "entry_tf", "direction", "filled_entries"], sort=True):
        row = {"grid_method": key[0], "entry_tf": key[1], "direction": key[2], "filled_entries": int(key[3])}
        row.update(summarize_group(group))
        by_fills_rows.append(row)

    return (
        _round_report(pd.DataFrame(summary_rows)),
        _round_report(pd.DataFrame(by_year_rows)),
        _round_report(pd.DataFrame(by_session_rows)),
        _round_report(pd.DataFrame(by_exit_rows)),
        _round_report(pd.DataFrame(by_fills_rows)),
    )


def run() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df10 = load_entry_tf("10m")
    ktr_table = build_session_ktr_table(df10)
    ktr_table.to_csv(OUTPUT_DIR / "strategy1_session_ktr_table.csv", index=False, encoding="utf-8-sig")
    df10 = attach_session_ktr(df10, ktr_table)
    signals = make_h1_breakout_signals(df10)

    all_trades = []
    cache = {"10m": df10}
    for entry_tf in ENTRY_TFS:
        df = cache.get(entry_tf)
        if df is None:
            df = load_entry_tf(entry_tf)
            df = attach_session_ktr(df, ktr_table)
            cache[entry_tf] = df
        for grid_method in GRID_METHODS:
            trades = build_trades(signals, df, entry_tf, grid_method)
            if not trades.empty:
                all_trades.append(trades)

    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    summary, by_year, by_session, by_exit, by_fills = summarize(trades)

    trades.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_stop5p_close_trail_trades.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_stop5p_close_trail_summary.csv", index=False, encoding="utf-8-sig")
    by_year.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_stop5p_close_trail_by_year.csv", index=False, encoding="utf-8-sig")
    by_session.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_stop5p_close_trail_by_session.csv", index=False, encoding="utf-8-sig")
    by_exit.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_stop5p_close_trail_by_exit.csv", index=False, encoding="utf-8-sig")
    by_fills.to_csv(OUTPUT_DIR / "strategy1_120sma_3scale_10p_stop5p_close_trail_by_fills.csv", index=False, encoding="utf-8-sig")

    top = summary.sort_values("expectancy_10p", ascending=False)
    print("")
    print("=== STRATEGY 1: 120SMA 3-SCALE 10P STOP + CLOSE TRAIL ===")
    print("H1 double-BB breakout -> 120SMA touch -> +2 entries every grid step adverse")
    print("grid_methods=%s hard stop: E3 +/- 5P, profit exit: avg +/- 5P close recovery then close-based 5P trailing" % ",".join(GRID_METHODS))
    print("entry_tfs=%s entry_time=08:30-23:30 wait_h=%s hold_until_exit=yes cost_per_unit=%s" % (
        ",".join(ENTRY_TFS),
        MAX_WAIT_HOURS,
        ROUND_TRIP_COST_POINTS_PER_UNIT,
    ))
    print("H1 signals:", len(signals))
    print("KTR sessions:", len(ktr_table))
    print("Trades:", len(all_trades) and len(pd.concat(all_trades, ignore_index=True)))
    print("")
    cols = [
        "grid_method",
        "entry_tf",
        "direction",
        "trades",
        "win_rate",
        "expectancy_points_total",
        "expectancy_10p",
        "expectancy_grid_r",
        "profit_factor",
        "max_drawdown_points",
        "cumulative_points",
        "avg_filled_entries",
        "avg_grid_step_points",
        "stop_rate",
        "trail_rate",
        "open_at_data_end_rate",
        "avg_mfe_10p",
        "avg_mae_10p",
    ]
    print(top[cols].to_string(index=False))
    print("")
    print("WROTE:", OUTPUT_DIR)
    return {
        "trades": trades,
        "summary": summary,
        "by_year": by_year,
        "by_session": by_session,
        "by_exit": by_exit,
        "by_fills": by_fills,
    }


if __name__ == "__main__":
    run()
