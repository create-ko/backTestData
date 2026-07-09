# -*- coding: utf-8 -*-
"""2m SMA20/120 cross + breakout-box onebee strategy.

Confirmed rules:
- Base TF: 2m.
- MA: SMA20 / SMA120 on 2m.
- Cross cycle starts on SMA20/120 cross.
- Breakout target: prior 60-bar high/low.
- Breakout candle wick ratio: max 10% on the breakout side.
- Breakout box: breakout candle high-low.
- Onebee:
  long = low touches bb4_4_lower_open, short = high touches bb4_4_upper_open.
- Entry: next 2m candle open after onebee touch candle.
- KTR: existing session_ktr convention from strategy1 script.
- Grid: 6 entries at 0,1,2,3,4,5 KTR, stop at 5.5 KTR.
- If filled entries < 50% (1-2 fills): fixed target 2KTR from avg entry, with
  0.5KTR close-based trailing when possible before target.
- If filled entries >= 50% (3+ fills): exit on Entry1 recovery.
- Cost: 0.5P round turn per filled unit.

Compared:
- box_break_policy: end_cycle vs keep_cycle.
- cycle_entry_policy: once_per_cycle vs repeat_in_cycle.
- h1_filter: none vs h1_sma20_120_align.

Same-bar conflict:
- If a 2m bar hits both stop and target/trail, use available 1m candles inside
  the 2m bar to infer path. If still ambiguous/missing, stop first.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STRATEGY1_SCRIPT = SCRIPT_DIR / "89_strategy1_h1_breakout_120sma_3scale_stop_trail_close.py"

sys.path.insert(0, str(SCRIPT_DIR))
import gold_data_prep as prep  # noqa: E402

spec = importlib.util.spec_from_file_location("strategy1_ktr", STRATEGY1_SCRIPT)
strategy1_ktr = importlib.util.module_from_spec(spec)
sys.modules["strategy1_ktr"] = strategy1_ktr
assert spec.loader is not None
spec.loader.exec_module(strategy1_ktr)


WICK_LIMIT = 0.10
RECENT_BREAK_LEN = 60
SMA_FAST = 20
SMA_SLOW = 120
BB_DDOF = 0
MAX_ENTRIES = 6
STOP_KTR = 5.5
HALF_FILL_COUNT = 3
TARGET_KTR_LIGHT_FILL = 2.0
TRAIL_KTR_LIGHT_FILL = 0.5
COST_PER_FILLED_UNIT = 0.50
ENTRY_START_MINUTE = 8 * 60 + 30
ENTRY_END_MINUTE = 23 * 60 + 30
BOX_BREAK_POLICIES = ["end_cycle", "keep_cycle"]
CYCLE_ENTRY_POLICIES = ["once_per_cycle", "repeat_in_cycle"]
H1_FILTERS = ["none", "h1_sma20_120_align"]
TEST_START = os.environ.get("TEST_START", "2026-01-01")
TEST_END = os.environ.get("TEST_END", "2026-06-16 23:59:59")
WARMUP_DAYS = int(os.environ.get("WARMUP_DAYS", "20"))
PERIOD_LABEL = (
    TEST_START[:10].replace("-", "")
    + "_"
    + TEST_END[:10].replace("-", "")
)
OUTPUT_DIR = ROOT / "result" / ("strategy_2m_sma_cross_box_onebee_ktr_" + PERIOD_LABEL)


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def load_tf(tf: str) -> pd.DataFrame:
    path = DATA_DIR / ("xauusd_%s_2010-01-01_2026-06-16.csv" % tf)
    df = quiet_call(prep.load_gold_data, path, timeframe=tf)
    df = prep.assign_session(df)
    df.attrs["timeframe"] = tf
    return df


def entry_time_allowed(ts: pd.Timestamp) -> bool:
    kst = ts.tz_convert("Asia/Seoul") if ts.tzinfo is not None else ts.tz_localize("Asia/Seoul")
    minutes = kst.hour * 60 + kst.minute
    return ENTRY_START_MINUTE <= minutes < ENTRY_END_MINUTE


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = prep.add_bollinger_bands(df.copy(), ddof=BB_DDOF)
    out["sma20"] = out["close"].rolling(SMA_FAST, min_periods=SMA_FAST).mean()
    out["sma120"] = out["close"].rolling(SMA_SLOW, min_periods=SMA_SLOW).mean()
    out["cross_long"] = ((out["sma20"] > out["sma120"]) & (out["sma20"].shift(1) <= out["sma120"].shift(1))).fillna(False)
    out["cross_short"] = ((out["sma20"] < out["sma120"]) & (out["sma20"].shift(1) >= out["sma120"].shift(1))).fillna(False)
    out["prior_60_high"] = out["high"].shift(1).rolling(RECENT_BREAK_LEN, min_periods=RECENT_BREAK_LEN).max()
    out["prior_60_low"] = out["low"].shift(1).rolling(RECENT_BREAK_LEN, min_periods=RECENT_BREAK_LEN).min()

    rng = out["high"] - out["low"]
    body = (out["close"] - out["open"]).abs()
    upper_wick = out["high"] - out[["open", "close"]].max(axis=1)
    lower_wick = out[["open", "close"]].min(axis=1) - out["low"]
    out["candle_range"] = rng
    out["body_ratio"] = np.where(rng > 0, body / rng, np.nan)
    out["upper_wick_ratio"] = np.where(rng > 0, upper_wick / rng, np.nan)
    out["lower_wick_ratio"] = np.where(rng > 0, lower_wick / rng, np.nan)
    out["long_breakout_box"] = (
        (out["close"] > out["prior_60_high"])
        & (out["close"] > out["open"])
        & (out["upper_wick_ratio"] <= WICK_LIMIT)
    ).fillna(False)
    out["short_breakout_box"] = (
        (out["close"] < out["prior_60_low"])
        & (out["close"] < out["open"])
        & (out["lower_wick_ratio"] <= WICK_LIMIT)
    ).fillna(False)
    return out


def build_h1_filter(df2: pd.DataFrame) -> pd.DataFrame:
    h1 = (
        df2[["open", "high", "low", "close", "volume"]]
        .resample("1h", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
    )
    h1["h1_sma20"] = h1["close"].rolling(20, min_periods=20).mean()
    h1["h1_sma120"] = h1["close"].rolling(120, min_periods=120).mean()
    h1["h1_bar_time_used"] = h1.index
    h1["h1_available_time"] = h1.index + pd.Timedelta(hours=1)
    h1["h1_long_ok"] = (h1["close"] > h1["h1_sma20"]) & (h1["h1_sma20"] > h1["h1_sma120"])
    h1["h1_short_ok"] = (h1["close"] < h1["h1_sma20"]) & (h1["h1_sma20"] < h1["h1_sma120"])
    return h1[["h1_available_time", "h1_bar_time_used", "h1_long_ok", "h1_short_ok", "close", "h1_sma20", "h1_sma120"]].rename(columns={"close": "h1_close"})


def attach_h1(df2: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    left = df2.reset_index().rename(columns={df2.index.name or "index": "datetime"})
    right = h1.reset_index(drop=True).sort_values("h1_available_time")
    left["_ts_ns"] = pd.to_datetime(left["datetime"], utc=True).astype("int64")
    right["_h1_ns"] = pd.to_datetime(right["h1_available_time"], utc=True).astype("int64")
    merged = pd.merge_asof(
        left.sort_values("_ts_ns"),
        right.sort_values("_h1_ns"),
        left_on="_ts_ns",
        right_on="_h1_ns",
        direction="backward",
    )
    merged = merged.drop(columns=["_ts_ns", "_h1_ns"], errors="ignore")
    merged = merged.set_index("datetime")
    merged.index.name = df2.index.name
    return merged


def load_prepared_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    df2 = add_indicators(load_tf("2m"))
    df10 = strategy1_ktr.load_entry_tf("10m")
    ktr_table = strategy1_ktr.build_session_ktr_table(df10)
    df2 = strategy1_ktr.attach_session_ktr(df2, ktr_table)
    h1 = build_h1_filter(df2)
    df2 = attach_h1(df2, h1)
    df1 = load_tf("1m")
    start = pd.Timestamp(TEST_START, tz="Asia/Seoul")
    warmup_start = start - pd.Timedelta(days=WARMUP_DAYS)
    end = pd.Timestamp(TEST_END, tz="Asia/Seoul")
    df2 = df2.loc[(df2.index >= warmup_start) & (df2.index <= end)].copy()
    df1 = df1.loc[(df1.index >= warmup_start) & (df1.index <= end)].copy()
    return df2, df1


def body_inside_box(bar: pd.Series, box_low: float, box_high: float, direction: str) -> bool:
    body_low = min(float(bar["open"]), float(bar["close"]))
    body_high = max(float(bar["open"]), float(bar["close"]))
    if body_low < box_low or body_high > box_high:
        return False
    return float(bar["close"]) > float(bar["open"]) if direction == "long" else float(bar["close"]) < float(bar["open"])


def h1_allows(row: pd.Series, direction: str, h1_filter: str) -> bool:
    if h1_filter == "none":
        return True
    if direction == "long":
        return bool(row.get("h1_long_ok", False))
    return bool(row.get("h1_short_ok", False))


def find_entry_candidates(df: pd.DataFrame, box_break_policy: str, cycle_entry_policy: str, h1_filter: str) -> pd.DataFrame:
    rows = []
    test_start_ts = pd.Timestamp(TEST_START, tz="Asia/Seoul")
    idx = df.index
    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    bb44_lower = df["bb4_4_lower_open"].to_numpy(dtype=float)
    bb44_upper = df["bb4_4_upper_open"].to_numpy(dtype=float)
    cross_long = df["cross_long"].to_numpy(dtype=bool)
    cross_short = df["cross_short"].to_numpy(dtype=bool)
    long_breakout = df["long_breakout_box"].to_numpy(dtype=bool)
    short_breakout = df["short_breakout_box"].to_numpy(dtype=bool)
    sessions = df["session"].astype(str).to_numpy()
    ktr_sessions = df["ktr_session"].astype(str).to_numpy()
    session_ktr = df["session_ktr"].to_numpy(dtype=float)
    h1_long_ok = df["h1_long_ok"].fillna(False).to_numpy(dtype=bool)
    h1_short_ok = df["h1_short_ok"].fillna(False).to_numpy(dtype=bool)
    h1_bar_time_used = df["h1_bar_time_used"].to_numpy()
    cycle_direction = None
    cycle_id = -1
    cycle_has_entry = False
    active_box = None
    pos = 0
    last_entry_exit_guard = -1

    while pos < len(df) - 1:
        if bool(cross_long[pos]):
            cycle_direction = "long"
            cycle_id += 1
            cycle_has_entry = False
            active_box = None
        elif bool(cross_short[pos]):
            cycle_direction = "short"
            cycle_id += 1
            cycle_has_entry = False
            active_box = None

        if cycle_direction is None:
            pos += 1
            continue
        if cycle_entry_policy == "once_per_cycle" and cycle_has_entry:
            pos += 1
            continue

        if active_box is None:
            breakout_ok = bool(long_breakout[pos]) if cycle_direction == "long" else bool(short_breakout[pos])
            if breakout_ok:
                active_box = {
                    "breakout_pos": pos,
                    "breakout_time": idx[pos],
                    "box_high": float(high[pos]),
                    "box_low": float(low[pos]),
                    "breakout_close": float(close[pos]),
                    "breakout_range": float(high[pos] - low[pos]),
                    "broken_before_entry": False,
                }
            pos += 1
            continue

        box_high = active_box["box_high"]
        box_low = active_box["box_low"]
        box_broken = float(close[pos]) < box_low if cycle_direction == "long" else float(close[pos]) > box_high
        if box_broken:
            active_box["broken_before_entry"] = True
            if box_break_policy == "end_cycle":
                cycle_direction = None
                active_box = None
                pos += 1
                continue

        onebee = (
            float(low[pos]) <= float(bb44_lower[pos])
            if cycle_direction == "long"
            else float(high[pos]) >= float(bb44_upper[pos])
        )
        body_low = min(float(open_[pos]), float(close[pos]))
        body_high = max(float(open_[pos]), float(close[pos]))
        body_direction_ok = close[pos] > open_[pos] if cycle_direction == "long" else close[pos] < open_[pos]
        body_box_ok = body_low >= box_low and body_high <= box_high and body_direction_ok
        h1_ok = True
        if h1_filter != "none":
            h1_ok = bool(h1_long_ok[pos]) if cycle_direction == "long" else bool(h1_short_ok[pos])
        if (
            onebee
            and body_box_ok
            and pos + 1 < len(df)
            and entry_time_allowed(idx[pos + 1])
            and h1_ok
            and pos > last_entry_exit_guard
            and idx[pos + 1] >= test_start_ts
        ):
            ktr = float(session_ktr[pos + 1])
            if not pd.isna(ktr) and ktr > 0:
                rows.append({
                    "tf": "2m",
                    "direction": cycle_direction,
                    "cycle_id": cycle_id,
                    "box_break_policy": box_break_policy,
                    "cycle_entry_policy": cycle_entry_policy,
                    "h1_filter": h1_filter,
                    "breakout_pos": active_box["breakout_pos"],
                    "breakout_time": active_box["breakout_time"],
                    "box_high": box_high,
                    "box_low": box_low,
                    "breakout_close": active_box["breakout_close"],
                    "breakout_range": active_box["breakout_range"],
                    "box_broken_before_entry": active_box["broken_before_entry"],
                    "onebee_touch_pos": pos,
                    "onebee_touch_time": idx[pos],
                    "entry_pos": pos + 1,
                    "entry_time": idx[pos + 1],
                    "entry_price": float(open_[pos + 1]),
                    "session": str(sessions[pos + 1]),
                    "ktr_session": str(ktr_sessions[pos + 1]),
                    "session_ktr": ktr,
                    "year": idx[pos + 1].year,
                    "bars_cross_to_breakout": active_box["breakout_pos"],
                    "bars_breakout_to_entry": pos + 1 - active_box["breakout_pos"],
                    "h1_bar_time_used": h1_bar_time_used[pos],
                })
                cycle_has_entry = True
                active_box = None
        pos += 1
    return pd.DataFrame(rows)


def levels_for(entry_price: float, direction: str, ktr: float) -> list[float]:
    if direction == "long":
        return [entry_price - i * ktr for i in range(MAX_ENTRIES)]
    return [entry_price + i * ktr for i in range(MAX_ENTRIES)]


def favorable_hit(direction: str, high: float, low: float, price: float) -> bool:
    return high >= price if direction == "long" else low <= price


def stop_hit(direction: str, high: float, low: float, price: float) -> bool:
    return low <= price if direction == "long" else high >= price


def infer_same_bar_exit(
    df1: pd.DataFrame,
    bar_start: pd.Timestamp,
    direction: str,
    stop_price: float,
    favorable_price: float,
) -> str:
    end = bar_start + pd.Timedelta(minutes=2)
    rows = df1.loc[(df1.index >= bar_start) & (df1.index < end)]
    if rows.empty:
        return "stop"
    for _, r in rows.iterrows():
        hi = float(r["high"])
        lo = float(r["low"])
        s_hit = stop_hit(direction, hi, lo, stop_price)
        f_hit = favorable_hit(direction, hi, lo, favorable_price)
        if s_hit and not f_hit:
            return "stop"
        if f_hit and not s_hit:
            return "favorable"
        if s_hit and f_hit:
            return "stop"
    return "stop"


def first_true_pos(mask: np.ndarray, start_pos: int) -> int | None:
    hits = np.where(mask)[0]
    if len(hits) == 0:
        return None
    return start_pos + int(hits[0])


def pnl(direction: str, avg_entry: float, exit_price: float, qty: float) -> float:
    return (exit_price - avg_entry) * qty if direction == "long" else (avg_entry - exit_price) * qty


def simulate_trade(data2: dict, df1: pd.DataFrame, cand: pd.Series) -> dict | None:
    direction = cand["direction"]
    start_pos = int(cand["entry_pos"])
    entry1 = float(cand["entry_price"])
    ktr = float(cand["session_ktr"])
    idx = data2["idx"]
    high = data2["high"]
    low = data2["low"]
    close = data2["close"]
    if start_pos >= len(idx) or pd.isna(ktr) or ktr <= 0:
        return None

    levels = levels_for(entry1, direction, ktr)
    hard_stop = entry1 - STOP_KTR * ktr if direction == "long" else entry1 + STOP_KTR * ktr
    filled = [False] * MAX_ENTRIES
    fill_times = [pd.NaT] * MAX_ENTRIES
    fill_prices: list[float] = []
    open_qty = 0
    avg_entry = math.nan
    target_price = math.nan
    trail_stop = math.nan
    trailing_armed = False
    max_favorable = 0.0
    max_adverse = 0.0
    exit_price = float(close[-1])
    exit_time = idx[-1]
    exit_reason = "open_at_data_end"

    pos = start_pos
    last_pos = len(idx) - 1
    while pos <= last_pos:
        if open_qty > 0:
            target_price = entry1 if open_qty >= HALF_FILL_COUNT else (
                avg_entry + TARGET_KTR_LIGHT_FILL * ktr if direction == "long" else avg_entry - TARGET_KTR_LIGHT_FILL * ktr
            )
            candidates = []
            if direction == "long":
                if open_qty < MAX_ENTRIES:
                    p = first_true_pos(low[pos:] <= levels[open_qty], pos)
                    if p is not None:
                        candidates.append(p)
                p = first_true_pos(low[pos:] <= hard_stop, pos)
                if p is not None:
                    candidates.append(p)
                p = first_true_pos(high[pos:] >= target_price, pos)
                if p is not None:
                    candidates.append(p)
                if trailing_armed:
                    p = first_true_pos(low[pos:] <= trail_stop, pos)
                    if p is not None:
                        candidates.append(p)
                elif open_qty < HALF_FILL_COUNT:
                    p = first_true_pos(close[pos:] >= avg_entry + TRAIL_KTR_LIGHT_FILL * ktr, pos)
                    if p is not None:
                        candidates.append(p)
            else:
                if open_qty < MAX_ENTRIES:
                    p = first_true_pos(high[pos:] >= levels[open_qty], pos)
                    if p is not None:
                        candidates.append(p)
                p = first_true_pos(high[pos:] >= hard_stop, pos)
                if p is not None:
                    candidates.append(p)
                p = first_true_pos(low[pos:] <= target_price, pos)
                if p is not None:
                    candidates.append(p)
                if trailing_armed:
                    p = first_true_pos(high[pos:] >= trail_stop, pos)
                    if p is not None:
                        candidates.append(p)
                elif open_qty < HALF_FILL_COUNT:
                    p = first_true_pos(close[pos:] <= avg_entry - TRAIL_KTR_LIGHT_FILL * ktr, pos)
                    if p is not None:
                        candidates.append(p)
            if candidates:
                next_pos = min(candidates)
                if next_pos > pos and not pd.isna(avg_entry):
                    if direction == "long":
                        max_favorable = max(max_favorable, float(np.nanmax(high[pos:next_pos + 1]) - avg_entry))
                        max_adverse = max(max_adverse, float(avg_entry - np.nanmin(low[pos:next_pos + 1])))
                    else:
                        max_favorable = max(max_favorable, float(avg_entry - np.nanmin(low[pos:next_pos + 1])))
                        max_adverse = max(max_adverse, float(np.nanmax(high[pos:next_pos + 1]) - avg_entry))
                    pos = next_pos
            elif pos < last_pos:
                if not pd.isna(avg_entry):
                    if direction == "long":
                        max_favorable = max(max_favorable, float(np.nanmax(high[pos:]) - avg_entry))
                        max_adverse = max(max_adverse, float(avg_entry - np.nanmin(low[pos:])))
                    else:
                        max_favorable = max(max_favorable, float(avg_entry - np.nanmin(low[pos:])))
                        max_adverse = max(max_adverse, float(np.nanmax(high[pos:]) - avg_entry))
                pos = last_pos

        t = idx[pos]
        hi = float(high[pos])
        lo = float(low[pos])
        cl = float(close[pos])

        for i, level in enumerate(levels):
            if filled[i]:
                continue
            hit = lo <= level if direction == "long" else hi >= level
            if hit:
                filled[i] = True
                fill_times[i] = t
                fill_prices.append(level)
                open_qty += 1
                avg_entry = sum(fill_prices) / len(fill_prices)
                trailing_armed = False
                trail_stop = math.nan

        if open_qty == 0 or pd.isna(avg_entry):
            pos += 1
            continue

        if direction == "long":
            max_favorable = max(max_favorable, hi - avg_entry)
            max_adverse = max(max_adverse, avg_entry - lo)
        else:
            max_favorable = max(max_favorable, avg_entry - lo)
            max_adverse = max(max_adverse, hi - avg_entry)

        if open_qty >= HALF_FILL_COUNT:
            target_price = entry1
        else:
            target_price = avg_entry + TARGET_KTR_LIGHT_FILL * ktr if direction == "long" else avg_entry - TARGET_KTR_LIGHT_FILL * ktr

        stop_now = stop_hit(direction, hi, lo, hard_stop)
        target_now = favorable_hit(direction, hi, lo, target_price)
        trail_now = trailing_armed and stop_hit(direction, hi, lo, trail_stop)
        favorable_price = target_price if target_now else trail_stop

        if stop_now and (target_now or trail_now):
            side = infer_same_bar_exit(df1, t, direction, hard_stop, favorable_price)
            if side == "stop":
                exit_price = hard_stop
                exit_reason = "hard_stop_5_5ktr"
            else:
                exit_price = favorable_price
                exit_reason = "entry1_recovery" if open_qty >= HALF_FILL_COUNT and target_now else "target_2ktr" if target_now else "trail_0_5ktr"
            exit_time = t
            break
        if stop_now:
            exit_price = hard_stop
            exit_reason = "hard_stop_5_5ktr"
            exit_time = t
            break
        if target_now:
            exit_price = target_price
            exit_reason = "entry1_recovery" if open_qty >= HALF_FILL_COUNT else "target_2ktr"
            exit_time = t
            break
        if trail_now:
            exit_price = trail_stop
            exit_reason = "trail_0_5ktr"
            exit_time = t
            break

        if open_qty < HALF_FILL_COUNT:
            arm_close = cl >= avg_entry + TRAIL_KTR_LIGHT_FILL * ktr if direction == "long" else cl <= avg_entry - TRAIL_KTR_LIGHT_FILL * ktr
            if arm_close:
                if direction == "long":
                    next_trail = cl - TRAIL_KTR_LIGHT_FILL * ktr
                    trail_stop = max(avg_entry, next_trail) if not trailing_armed else max(trail_stop, avg_entry, next_trail)
                else:
                    next_trail = cl + TRAIL_KTR_LIGHT_FILL * ktr
                    trail_stop = min(avg_entry, next_trail) if not trailing_armed else min(trail_stop, avg_entry, next_trail)
                trailing_armed = True

        pos += 1

    if open_qty == 0 or pd.isna(avg_entry):
        return None

    gross = pnl(direction, avg_entry, exit_price, open_qty)
    cost = COST_PER_FILLED_UNIT * open_qty
    net = gross - cost
    return {
        "entry_1_price": levels[0],
        "entry_2_price": levels[1],
        "entry_3_price": levels[2],
        "entry_4_price": levels[3],
        "entry_5_price": levels[4],
        "entry_6_price": levels[5],
        "entry_1_time": fill_times[0],
        "entry_2_time": fill_times[1],
        "entry_3_time": fill_times[2],
        "entry_4_time": fill_times[3],
        "entry_5_time": fill_times[4],
        "entry_6_time": fill_times[5],
        "filled_entries": int(open_qty),
        "fill_ratio": open_qty / MAX_ENTRIES,
        "avg_entry": avg_entry,
        "hard_stop_price": hard_stop,
        "target_price": target_price,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_points_total": gross,
        "cost_points_total": cost,
        "net_points_total": net,
        "net_ktr_r": net / ktr,
        "mfe_points": max_favorable,
        "mae_points": max_adverse,
        "mfe_ktr_r": max_favorable / ktr,
        "mae_ktr_r": max_adverse / ktr,
        "hold_bars": int(idx.searchsorted(exit_time) - start_pos + 1),
        "trailing_armed": bool(trailing_armed),
    }


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
    pnl = pd.to_numeric(group["net_points_total"], errors="coerce")
    exits = group["exit_reason"].astype(str)
    return {
        "trades": int(len(group)),
        "win_rate": float((pnl > 0).mean()),
        "expectancy_points": float(pnl.mean()),
        "expectancy_ktr_r": float(group["net_ktr_r"].mean()),
        "profit_factor": profit_factor(pnl),
        "max_drawdown_points": max_drawdown(pnl),
        "cumulative_points": float(pnl.sum()),
        "avg_filled_entries": float(group["filled_entries"].mean()),
        "avg_session_ktr": float(group["session_ktr"].mean()),
        "stop_rate": float((exits == "hard_stop_5_5ktr").mean()),
        "target_2ktr_rate": float((exits == "target_2ktr").mean()),
        "trail_rate": float((exits == "trail_0_5ktr").mean()),
        "entry1_recovery_rate": float((exits == "entry1_recovery").mean()),
        "avg_mfe_ktr_r": float(group["mfe_ktr_r"].mean()),
        "avg_mae_ktr_r": float(group["mae_ktr_r"].mean()),
    }


def round_report(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(3)
    return out


def grouped_summary(trades: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    rows = []
    for key, group in trades.groupby(cols, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        row = dict(zip(cols, key))
        row.update(summarize_group(group))
        rows.append(row)
    return round_report(pd.DataFrame(rows))


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join(f"<th>{c}</th>" for c in show.columns)
    rows = []
    for _, row in show.iterrows():
        cells = []
        for col, value in row.items():
            klass = ""
            if col in {"expectancy_ktr_r", "expectancy_points", "cumulative_points", "profit_factor"}:
                try:
                    num = float(value)
                    klass = "pos" if (num >= 1 if col == "profit_factor" else num > 0) else "neg"
                except Exception:
                    pass
            if pd.isna(value):
                text = ""
            elif isinstance(value, float):
                text = f"{value*100:.1f}%" if col == "win_rate" or col.endswith("_rate") else f"{value:,.3f}"
            else:
                text = str(value)
            cells.append(f"<td class='{klass}'>{text}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<section><h2>{title}</h2><div class='table-wrap'><table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"


def write_html(summary, sessions, fills, exits, yearly):
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f6f7f9;color:#17202a}
    header{padding:30px 42px;background:#101820;color:white}h1{margin:0 0 8px;font-size:26px}header p{margin:0;color:#c9d3df}
    main{padding:24px 42px 48px;max-width:1900px;margin:0 auto}section{background:white;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{margin:0 0 10px;font-size:18px}.table-wrap{overflow-x:auto;border:1px solid #d9dee7;border-radius:8px}
    table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}
    th{background:#eef2f7}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2),td:nth-child(3),th:nth-child(3),td:nth-child(4),th:nth-child(4){text-align:left}
    """
    html = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m SMA Cross Box Onebee KTR</title><style>{css}</style></head>
<body><header><h1>2m SMA20/120 Cross Box Onebee KTR</h1><p>Session KTR grid 0~5, stop 5.5KTR, 1~2 fills target 2KTR with 0.5KTR trail, 3+ fills Entry1 recovery.</p></header><main>
{table_html(summary.sort_values("expectancy_ktr_r", ascending=False), "Config Ranking")}
{table_html(sessions.sort_values("expectancy_ktr_r", ascending=False), "Session Breakdown", 100)}
{table_html(fills.sort_values(["box_break_policy", "cycle_entry_policy", "h1_filter", "direction", "filled_entries"]), "Filled Entries Breakdown")}
{table_html(exits.sort_values(["box_break_policy", "cycle_entry_policy", "h1_filter", "direction", "exit_reason"]), "Exit Breakdown")}
{table_html(yearly.sort_values(["box_break_policy", "cycle_entry_policy", "h1_filter", "direction", "year"]), "Yearly Breakdown")}
</main></body></html>"""
    (OUTPUT_DIR / "strategy_2m_sma_cross_box_onebee_ktr_report.html").write_text(html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("LOAD/PREP data")
    print("TEST_PERIOD:", TEST_START, "~", TEST_END, "warmup_days=", WARMUP_DAYS)
    df2, df1 = load_prepared_data()
    data2 = {
        "idx": df2.index,
        "high": df2["high"].to_numpy(dtype=float),
        "low": df2["low"].to_numpy(dtype=float),
        "close": df2["close"].to_numpy(dtype=float),
    }
    all_rows = []
    all_candidates = []

    for box_policy in BOX_BREAK_POLICIES:
        for cycle_policy in CYCLE_ENTRY_POLICIES:
            for h1_filter in H1_FILTERS:
                print("candidates", box_policy, cycle_policy, h1_filter)
                cands = find_entry_candidates(df2, box_policy, cycle_policy, h1_filter)
                print(" ->", len(cands))
                if not cands.empty:
                    all_candidates.append(cands)
                for _, cand in cands.iterrows():
                    sim = simulate_trade(data2, df1, cand)
                    if sim is None:
                        continue
                    row = cand.to_dict()
                    row.update(sim)
                    all_rows.append(row)

    trades = pd.DataFrame(all_rows).sort_values("entry_time").reset_index(drop=True) if all_rows else pd.DataFrame()
    candidates = pd.concat(all_candidates, ignore_index=True) if all_candidates else pd.DataFrame()

    summary = grouped_summary(trades, ["box_break_policy", "cycle_entry_policy", "h1_filter", "direction"])
    sessions = grouped_summary(trades, ["box_break_policy", "cycle_entry_policy", "h1_filter", "direction", "session"])
    fills = grouped_summary(trades, ["box_break_policy", "cycle_entry_policy", "h1_filter", "direction", "filled_entries"])
    exits = grouped_summary(trades, ["box_break_policy", "cycle_entry_policy", "h1_filter", "direction", "exit_reason"])
    yearly = grouped_summary(trades, ["box_break_policy", "cycle_entry_policy", "h1_filter", "direction", "year"])

    candidates.to_csv(OUTPUT_DIR / "strategy_2m_sma_cross_box_onebee_candidates.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(OUTPUT_DIR / "strategy_2m_sma_cross_box_onebee_trades.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "strategy_2m_sma_cross_box_onebee_summary.csv", index=False, encoding="utf-8-sig")
    sessions.to_csv(OUTPUT_DIR / "strategy_2m_sma_cross_box_onebee_by_session.csv", index=False, encoding="utf-8-sig")
    fills.to_csv(OUTPUT_DIR / "strategy_2m_sma_cross_box_onebee_by_fills.csv", index=False, encoding="utf-8-sig")
    exits.to_csv(OUTPUT_DIR / "strategy_2m_sma_cross_box_onebee_by_exit.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "strategy_2m_sma_cross_box_onebee_by_year.csv", index=False, encoding="utf-8-sig")
    write_html(summary, sessions, fills, exits, yearly)

    print("")
    print("=== 2M SMA CROSS BOX ONEBEE KTR ===")
    print("Candidates:", len(candidates), "Trades:", len(trades))
    cols = [
        "box_break_policy", "cycle_entry_policy", "h1_filter", "direction",
        "trades", "win_rate", "expectancy_ktr_r", "profit_factor",
        "max_drawdown_points", "cumulative_points", "avg_filled_entries",
        "avg_session_ktr", "stop_rate", "target_2ktr_rate", "trail_rate", "entry1_recovery_rate",
    ]
    print(summary.sort_values("expectancy_ktr_r", ascending=False)[cols].to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
