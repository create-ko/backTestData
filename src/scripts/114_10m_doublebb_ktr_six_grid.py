# -*- coding: utf-8 -*-
"""10-minute Double-BB breakout with session-KTR six-entry grid.

The three entry variants are deliberately isolated:
1) immediate: first fill at the next 10-minute open after a Double-BB close.
2) first_onebee: first opposing BB4/4 touch after the breakout, then next open.
3) breakout_onebee_limit: a limit at the breakout candle's opposing BB4/4 band,
   replaced by the newest breakout while it remains unfilled.

Grid and exits:
- Six equal units at E1 plus/minus 0..5 session KTR.
- The hard stop becomes active only after all six units are filled, at 5.5 KTR.
- Until an opposite Double-BB breakout closes, exit all units at average entry +/- 2 KTR.
- Once the opposite breakout is confirmed, exit at the first strictly positive
  net PnL price. New entry signals are ignored while a position is open.
- A 10-minute bar is resolved from its 1-minute bars. A remaining same-minute
  stop/exit conflict is conservative: stop first.

The first-onebee pending signal is replaced by a newer breakout before entry.
This matches the breakout-onebee pending-order behavior and prevents competing
signals from opening multiple positions. No time exit is used.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
DATA_DIR = ROOT / "data"
sys.path.insert(0, str(SCRIPT_DIR))

import gold_data_prep as prep  # noqa: E402


TEST_START = os.getenv("TEST_START", "2026-01-01")
TEST_END = os.getenv("TEST_END", "2026-06-30 23:59:59")
ROUND_TRIP_COST_POINTS_PER_UNIT = 0.50
MAX_ENTRIES = int(os.getenv("MAX_ENTRIES", "6"))
KTR_STOP_OFFSET = 0.50
TARGET_KTR = 2.0
PRICE_TICK = 0.01
GRID_UNIT_MODE = os.getenv("GRID_UNIT_MODE", "session_ktr")
SESSION_KTR_SWITCH_POINTS = float(os.getenv("SESSION_KTR_SWITCH_POINTS", "15.0"))
THIRD_FILL_RECOVERY = os.getenv("THIRD_FILL_RECOVERY", "0") == "1"
ENTRY_TYPES = ("immediate", "first_onebee", "breakout_onebee_limit")


def _quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _load_ktr_module():
    path = SCRIPT_DIR / "89_strategy1_h1_breakout_120sma_3scale_stop_trail_close.py"
    spec = importlib.util.spec_from_file_location("strategy1_ktr", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the existing session KTR module: %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_market_data():
    """Load 10m signal data, attach the existing session KTR, and load 1m paths."""
    # The shared prep module was originally capped at 2026-06-17. Keep that
    # historical default untouched for other scripts, but allow this new
    # strategy to use the locally available June 30 source files.
    prep.END_DATE_EXCLUSIVE = pd.Timestamp("2026-07-01", tz="Asia/Seoul")
    ten_path = DATA_DIR / "xauusd_10m_2010-01-01_2026-06-30.csv"
    one_path = DATA_DIR / "xauusd_1m_2010-01-01_2026-06-30.csv"
    df10_all = _quiet(prep.load_gold_data, ten_path, timeframe="10m")
    df10_all = prep.assign_session(df10_all)
    df10_all = prep.add_bollinger_bands(df10_all, ddof=0)

    ktr_module = _load_ktr_module()
    ktr_table = ktr_module.build_session_ktr_table(df10_all)
    df10_all = ktr_module.attach_session_ktr(df10_all, ktr_table)

    start = pd.Timestamp(TEST_START, tz="Asia/Seoul")
    end = pd.Timestamp(TEST_END, tz="Asia/Seoul")
    df10 = df10_all.loc[(df10_all.index >= start) & (df10_all.index <= end)].copy()
    df10["long_breakout"] = (
        (df10["close"] > df10["bb20_2_upper_close"])
        & (df10["close"] > df10["bb4_4_upper_open"])
    ).fillna(False)
    df10["short_breakout"] = (
        (df10["close"] < df10["bb20_2_lower_close"])
        & (df10["close"] < df10["bb4_4_lower_open"])
    ).fillna(False)

    # A one-minute buffer on both sides protects the first/last 10m path.
    df1_all = _quiet(prep.load_gold_data, one_path, timeframe="1m")
    df1 = df1_all.loc[
        (df1_all.index >= start - pd.Timedelta(minutes=1))
        & (df1_all.index < end + pd.Timedelta(minutes=11))
    ][["open", "high", "low", "close"]].copy()
    return df10, df1, ktr_table


def _direction_from_bar(row: pd.Series) -> str | None:
    if bool(row["long_breakout"]):
        return "long"
    if bool(row["short_breakout"]):
        return "short"
    return None


def _is_opposite(direction: str, candidate: str | None) -> bool:
    return candidate is not None and candidate != direction


def _onebee_touched(row: pd.Series, direction: str) -> bool:
    if direction == "long":
        return bool(row["low"] <= row["bb4_4_lower_open"])
    return bool(row["high"] >= row["bb4_4_upper_open"])


def _limit_price(row: pd.Series, direction: str) -> float:
    return float(row["bb4_4_lower_open"] if direction == "long" else row["bb4_4_upper_open"])


def _entry_levels(entry_1: float, ktr: float, direction: str) -> list[float]:
    multiplier = -1.0 if direction == "long" else 1.0
    return [entry_1 + multiplier * level * ktr for level in range(MAX_ENTRIES)]


@dataclass
class Position:
    entry_type: str
    direction: str
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_1: float
    ktr: float
    session_ktr: float
    grid_unit_source: str
    session: str
    ktr_session: str
    levels: list[float]
    filled: list[bool] = field(default_factory=lambda: [False] * MAX_ENTRIES)
    active: list[bool] = field(default_factory=lambda: [False] * MAX_ENTRIES)
    fill_times: list[pd.Timestamp | None] = field(default_factory=lambda: [None] * MAX_ENTRIES)
    opposite_breakout_seen: bool = False
    opposite_breakout_time: pd.Timestamp | None = None
    max_favorable_points: float = 0.0
    max_adverse_points: float = 0.0
    recovery_reduced: bool = False
    recovery_armed: bool = False
    recovery_extreme: float | None = None

    def fill(self, level_index: int, when: pd.Timestamp):
        self.filled[level_index] = True
        self.active[level_index] = True
        self.fill_times[level_index] = when

    @property
    def fill_count(self) -> int:
        return int(sum(self.filled))

    @property
    def fill_prices(self) -> list[float]:
        return [price for price, filled in zip(self.levels, self.filled) if filled]

    @property
    def open_prices(self) -> list[float]:
        return [price for price, active in zip(self.levels, self.active) if active]

    @property
    def avg_entry(self) -> float:
        return float(np.mean(self.open_prices))

    @property
    def hard_stop(self) -> float:
        return self.levels[-1] - KTR_STOP_OFFSET * self.ktr if self.direction == "long" else self.levels[-1] + KTR_STOP_OFFSET * self.ktr

    @property
    def target(self) -> float:
        return self.avg_entry + TARGET_KTR * self.ktr if self.direction == "long" else self.avg_entry - TARGET_KTR * self.ktr

    @property
    def positive_net_exit(self) -> float:
        # Every filled unit has 0.5P round-trip cost. Add one minimum tick so
        # that the fallback exit is strictly positive, not merely break-even.
        cost_per_unit = ROUND_TRIP_COST_POINTS_PER_UNIT + PRICE_TICK
        return self.avg_entry + cost_per_unit if self.direction == "long" else self.avg_entry - cost_per_unit


def _make_position(entry_type: str, setup: dict, entry_time: pd.Timestamp, entry_price: float) -> Position:
    ktr = float(setup["ktr"])
    return Position(
        entry_type=entry_type,
        direction=setup["direction"],
        signal_time=setup["signal_time"],
        entry_time=entry_time,
        entry_1=float(entry_price),
        ktr=ktr,
        session_ktr=float(setup["session_ktr"]),
        grid_unit_source=setup["grid_unit_source"],
        session=setup["session"],
        ktr_session=setup["ktr_session"],
        levels=_entry_levels(float(entry_price), ktr, setup["direction"]),
    )


def _minute_path(df1: pd.DataFrame, ten_time: pd.Timestamp) -> pd.DataFrame:
    # Index search avoids scanning the full 1m data set for every 10m bar.
    # It is behaviorally identical to the former boolean time filter.
    start = df1.index.searchsorted(ten_time, side="left")
    end = df1.index.searchsorted(ten_time + pd.Timedelta(minutes=10), side="left")
    return df1.iloc[start:end]


def _close_record(position: Position, exit_time: pd.Timestamp, exit_price: float, reason: str, is_closed=True) -> dict:
    fills = position.fill_count
    open_units = len(position.open_prices)
    avg = position.avg_entry
    gross_per_unit = exit_price - avg if position.direction == "long" else avg - exit_price
    gross_points = gross_per_unit * open_units
    cost_points = ROUND_TRIP_COST_POINTS_PER_UNIT * open_units
    net_points = gross_points - cost_points
    return {
        "entry_type": position.entry_type,
        "direction": position.direction,
        "signal_time": position.signal_time,
        "entry_time": position.entry_time,
        "session": position.session,
        "ktr_session": position.ktr_session,
        "ktr": position.ktr,
        "session_ktr": position.session_ktr,
        "grid_unit_source": position.grid_unit_source,
        "max_entries": MAX_ENTRIES,
        "entry_1_price": position.entry_1,
        **{"entry_%s_price" % (i + 1): position.levels[i] for i in range(MAX_ENTRIES)},
        **{"entry_%s_time" % (i + 1): position.fill_times[i] for i in range(MAX_ENTRIES)},
        "filled_entries": fills,
        "remaining_entries": open_units,
        "third_fill_recovery_reduced": position.recovery_reduced,
        "avg_entry_price": avg,
        "hard_stop_price": position.hard_stop,
        "target_price_at_exit": position.target,
        "opposite_breakout_seen": position.opposite_breakout_seen,
        "opposite_breakout_time": position.opposite_breakout_time,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": reason,
        "is_closed": is_closed,
        "gross_points": gross_points,
        "cost_points": cost_points,
        "net_points": net_points if is_closed else np.nan,
        "net_ktr": net_points / position.ktr if is_closed else np.nan,
        "mfe_points": position.max_favorable_points,
        "mae_points": position.max_adverse_points,
        "mfe_ktr": position.max_favorable_points / position.ktr,
        "mae_ktr": position.max_adverse_points / position.ktr,
    }


def _process_minute(position: Position, bar: pd.Series) -> tuple[bool, dict | None]:
    """Advance one minute. A same-minute unresolved conflict is stop-first."""
    when = bar.name
    high, low = float(bar["high"]), float(bar["low"])

    # Adverse grid fills are intentionally processed before exits. If the same
    # minute also reaches the stop/target, minute OHLC cannot give a sequence;
    # stop-first below supplies the conservative fallback.
    for level_i, level in enumerate(position.levels):
        if position.recovery_reduced or position.filled[level_i]:
            continue
        hit = low <= level if position.direction == "long" else high >= level
        if hit:
            position.fill(level_i, when)

    # After an opposite breakout, an exact 3-fill recovery neutralizes the
    # outer pair (E1/E3) at the cost-neutral E2 +/- 0.5P level.
    if (
        THIRD_FILL_RECOVERY
        and position.opposite_breakout_seen
        and not position.recovery_reduced
        and position.fill_count == 3
    ):
        neutral = position.levels[1] + ROUND_TRIP_COST_POINTS_PER_UNIT if position.direction == "long" else position.levels[1] - ROUND_TRIP_COST_POINTS_PER_UNIT
        hit = high >= neutral if position.direction == "long" else low <= neutral
        if hit:
            position.active[0] = False
            position.active[2] = False
            position.recovery_reduced = True
            position.recovery_extreme = neutral

    avg = position.avg_entry
    if position.recovery_reduced:
        if position.direction == "long":
            position.recovery_extreme = max(float(position.recovery_extreme), high)
            if high >= position.levels[1] + 0.5 * position.ktr:
                position.recovery_armed = True
            stop = (max(position.levels[1], float(position.recovery_extreme) - 0.5 * position.ktr) if position.recovery_armed else position.levels[1] - 0.5 * position.ktr)
            if low <= stop:
                return True, _close_record(position, when, stop, "third_fill_recovery_trail")
        else:
            position.recovery_extreme = min(float(position.recovery_extreme), low)
            if low <= position.levels[1] - 0.5 * position.ktr:
                position.recovery_armed = True
            stop = (min(position.levels[1], float(position.recovery_extreme) + 0.5 * position.ktr) if position.recovery_armed else position.levels[1] + 0.5 * position.ktr)
            if high >= stop:
                return True, _close_record(position, when, stop, "third_fill_recovery_trail")
        return False, None
    if position.direction == "long":
        position.max_favorable_points = max(position.max_favorable_points, high - avg)
        position.max_adverse_points = max(position.max_adverse_points, avg - low)
        stop_hit = position.fill_count == MAX_ENTRIES and low <= position.hard_stop
        exit_level = position.positive_net_exit if position.opposite_breakout_seen else position.target
        exit_hit = high >= exit_level
    else:
        position.max_favorable_points = max(position.max_favorable_points, avg - low)
        position.max_adverse_points = max(position.max_adverse_points, high - avg)
        stop_hit = position.fill_count == MAX_ENTRIES and high >= position.hard_stop
        exit_level = position.positive_net_exit if position.opposite_breakout_seen else position.target
        exit_hit = low <= exit_level

    if stop_hit:
        return True, _close_record(position, when, position.hard_stop, "hard_stop_after_max_fills")
    if exit_hit:
        reason = "positive_after_opposite_breakout" if position.opposite_breakout_seen else "target_2ktr"
        return True, _close_record(position, when, exit_level, reason)
    return False, None


def _start_at_open(entry_type: str, setup: dict, ten_time: pd.Timestamp, minute_bars: pd.DataFrame) -> tuple[Position, dict | None]:
    position = _make_position(entry_type, setup, ten_time, float(minute_bars["open"].iloc[0]))
    position.fill(0, minute_bars.index[0])
    for _, minute in minute_bars.iterrows():
        closed, record = _process_minute(position, minute)
        if closed:
            return position, record
    return position, None


def _try_limit_entry(setup: dict, ten_time: pd.Timestamp, minute_bars: pd.DataFrame) -> tuple[Position | None, dict | None]:
    limit = float(setup["limit_price"])
    for minute_time, minute in minute_bars.iterrows():
        touched = float(minute["low"]) <= limit if setup["direction"] == "long" else float(minute["high"]) >= limit
        if not touched:
            continue
        position = _make_position("breakout_onebee_limit", setup, ten_time, limit)
        position.fill(0, minute_time)
        # The fill minute can also contain deeper grid fills or a stop/target.
        closed, record = _process_minute(position, minute)
        if closed:
            return position, record
        remaining = minute_bars.loc[minute_bars.index > minute_time]
        for _, later_minute in remaining.iterrows():
            closed, record = _process_minute(position, later_minute)
            if closed:
                return position, record
        return position, None
    return None, None


def _setup_from_signal(row: pd.Series, time: pd.Timestamp, direction: str) -> dict | None:
    session_ktr = row.get("session_ktr")
    if pd.isna(session_ktr) or float(session_ktr) <= 0:
        return None
    breakout_range = float(row["high"] - row["low"])
    if pd.isna(breakout_range) or breakout_range <= 0:
        return None
    if GRID_UNIT_MODE == "breakout_range_if_session_ktr_gt_threshold":
        if float(session_ktr) > SESSION_KTR_SWITCH_POINTS:
            ktr = breakout_range
            grid_unit_source = "breakout_range"
        else:
            ktr = float(session_ktr)
            grid_unit_source = "session_ktr"
    elif GRID_UNIT_MODE == "session_ktr":
        ktr = float(session_ktr)
        grid_unit_source = "session_ktr"
    else:
        raise ValueError("Unknown GRID_UNIT_MODE: %s" % GRID_UNIT_MODE)
    return {
        "direction": direction,
        "signal_time": time + pd.Timedelta(minutes=10),
        "session": str(row.get("session", "other")),
        "ktr_session": str(row.get("ktr_session", "unknown")),
        "ktr": float(ktr),
        "session_ktr": float(session_ktr),
        "breakout_range": breakout_range,
        "grid_unit_source": grid_unit_source,
        "limit_price": _limit_price(row, direction),
    }


def simulate_entry_type(df10: pd.DataFrame, df1: pd.DataFrame, entry_type: str) -> pd.DataFrame:
    """Run one entry variant chronologically, with no overlapping positions."""
    records: list[dict] = []
    position: Position | None = None
    pending_setup: dict | None = None
    scheduled_setup: dict | None = None
    times = df10.index

    for pos, (ten_time, row) in enumerate(df10.iterrows()):
        minute_bars = _minute_path(df1, ten_time)
        if minute_bars.empty:
            continue

        # First, process the price path during this completed 10m bar.
        if position is not None:
            for _, minute in minute_bars.iterrows():
                closed, record = _process_minute(position, minute)
                if closed:
                    records.append(record)
                    position = None
                    break
        elif scheduled_setup is not None:
            position, record = _start_at_open(entry_type, scheduled_setup, ten_time, minute_bars)
            scheduled_setup = None
            if record is not None:
                records.append(record)
                position = None
        elif entry_type == "first_onebee" and pending_setup is not None:
            if _onebee_touched(row, pending_setup["direction"]) and pos + 1 < len(times):
                scheduled_setup = pending_setup
                pending_setup = None
        elif entry_type == "breakout_onebee_limit" and pending_setup is not None:
            position, record = _try_limit_entry(pending_setup, ten_time, minute_bars)
            if position is not None:
                pending_setup = None
                if record is not None:
                    records.append(record)
                    position = None

        # A breakout becomes known only after this 10m bar closes.
        signal_direction = _direction_from_bar(row)
        if position is not None:
            if _is_opposite(position.direction, signal_direction):
                position.opposite_breakout_seen = True
                position.opposite_breakout_time = ten_time + pd.Timedelta(minutes=10)
            continue

        if scheduled_setup is not None:
            continue
        if signal_direction is None:
            continue
        setup = _setup_from_signal(row, ten_time, signal_direction)
        if setup is None:
            continue
        if entry_type == "immediate":
            if pos + 1 < len(times):
                scheduled_setup = setup
        else:
            # For both pending entry variants, a confirmed newer breakout
            # replaces the previous unfilled setup.
            pending_setup = setup

    if position is not None:
        last_bar = df1.iloc[-1]
        records.append(_close_record(position, last_bar.name, float(last_bar["close"]), "open_at_data_end", is_closed=False))
    return pd.DataFrame(records)


def summarize(trades: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "max_entries", "entry_type", "direction", "total_positions", "closed_trades", "open_positions",
        "win_rate", "expectancy_ktr", "profit_factor", "cumulative_points",
        "max_drawdown_points", "avg_fills", "avg_cost_points", "target_2ktr_rate",
        "opposite_positive_exit_rate", "hard_stop_rate",
    ]
    rows = []
    for (entry_type, direction), group in trades.groupby(["entry_type", "direction"], dropna=False):
        closed = group[group["is_closed"]].copy()
        pnl = pd.to_numeric(closed.get("net_points"), errors="coerce").dropna()
        pnl_ktr = pd.to_numeric(closed.get("net_ktr"), errors="coerce").dropna()
        wins = pnl[pnl > 0]
        losses = pnl[pnl < 0]
        curve = pnl.cumsum()
        dd = curve.cummax() - curve
        rows.append({
            "max_entries": MAX_ENTRIES,
            "entry_type": entry_type,
            "direction": direction,
            "total_positions": len(group),
            "closed_trades": len(closed),
            "open_positions": int((~group["is_closed"]).sum()),
            "win_rate": float((pnl > 0).mean()) if len(pnl) else np.nan,
            "expectancy_ktr": float(pnl_ktr.mean()) if len(pnl_ktr) else np.nan,
            "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and abs(losses.sum()) > 0 else np.nan,
            "cumulative_points": float(pnl.sum()) if len(pnl) else 0.0,
            "max_drawdown_points": float(dd.max()) if len(dd) else 0.0,
            "avg_fills": float(closed["filled_entries"].mean()) if len(closed) else np.nan,
            "avg_cost_points": float(closed["cost_points"].mean()) if len(closed) else np.nan,
            "target_2ktr_rate": float((closed["exit_reason"] == "target_2ktr").mean()) if len(closed) else np.nan,
            "opposite_positive_exit_rate": float((closed["exit_reason"] == "positive_after_opposite_breakout").mean()) if len(closed) else np.nan,
            "hard_stop_rate": float((closed["exit_reason"] == "hard_stop_after_max_fills").mean()) if len(closed) else np.nan,
        })
    out = pd.DataFrame(rows)
    return out.reindex(columns=cols).sort_values(["entry_type", "direction"]).reset_index(drop=True)


def write_report(output_dir: Path, summary: pd.DataFrame, trades: pd.DataFrame):
    output_dir.mkdir(parents=True, exist_ok=True)
    summary.round(3).to_csv(output_dir / "summary.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(output_dir / "trades.csv", index=False, encoding="utf-8-sig")
    html = """<!doctype html><html><head><meta charset=\"utf-8\"><title>10m DoubleBB KTR Grid</title>
<style>body{font-family:Arial,sans-serif;margin:32px;color:#18212f}table{border-collapse:collapse;margin:16px 0}th,td{border:1px solid #ccd3dc;padding:7px 9px;text-align:right}th{background:#eef3f7}td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.note{max-width:1000px;line-height:1.55}</style>
</head><body><h1>10m Double-BB / Session KTR Grid</h1><p class=\"note\">Period: %s to %s. Max entries: %s. Cost: 0.5P per filled unit round trip. Intrabar conflicts use 1m bars; unresolved 1m conflicts use stop first.</p><h2>Closed-trade summary</h2>%s</body></html>""" % (
        TEST_START, TEST_END, MAX_ENTRIES, summary.round(3).to_html(index=False),
    )
    (output_dir / "report.html").write_text(html, encoding="utf-8")


def main():
    df10, df1, _ = load_market_data()
    print("10m bars: %s | 1m bars: %s | period: %s ~ %s" % (len(df10), len(df1), TEST_START, TEST_END))
    parts = []
    for entry_type in ENTRY_TYPES:
        result = simulate_entry_type(df10, df1, entry_type)
        print("%s: positions=%s" % (entry_type, len(result)))
        parts.append(result)
    trades = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    summary = summarize(trades) if not trades.empty else pd.DataFrame()
    output_dir = ROOT / "result" / ("strategy_10m_doublebb_ktr_grid%s_%s_%s" % (MAX_ENTRIES, TEST_START[:10].replace("-", ""), TEST_END[:10].replace("-", "")))
    write_report(output_dir, summary, trades)
    print("\n" + summary.round(3).to_string(index=False))
    print("\nSaved: %s" % output_dir)


if __name__ == "__main__":
    main()
