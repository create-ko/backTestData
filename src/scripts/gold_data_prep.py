# -*- coding: utf-8 -*-
"""Gold data loading, validation, session tagging, and Bollinger prep.

This module intentionally stops before strategy logic.

Example:
    df = load_gold_data("../../data/xauusd_5m_2010-01-01_2026-06-16.csv", "5m")
    validate_ohlcv(df)
    df = assign_session(df)
    df = add_bollinger_bands(df)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

import math
import pandas as pd


KST = ZoneInfo("Asia/Seoul")
LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")
START_DATE = pd.Timestamp("2010-01-01", tz=KST)
END_DATE_EXCLUSIVE = pd.Timestamp("2026-06-17", tz=KST)


@dataclass(frozen=True)
class ValidationReport:
    rows: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    missing_values: int
    duplicate_datetimes: int
    invalid_ohlc_rows: int
    non_positive_price_rows: int


def _normalize_col(name: str) -> str:
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    for cand in candidates:
        if cand in columns:
            return cand
    for col in columns:
        for cand in candidates:
            if cand in col:
                return col
    return None


def _parse_time_arg(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _in_time_range(ts: pd.Timestamp, start: time, end: time) -> bool:
    t = ts.timetz().replace(tzinfo=None)
    return start <= t < end


def _is_dst(ts: pd.Timestamp) -> bool:
    return bool(ts.dst() and ts.dst().total_seconds() != 0)


def load_gold_data(filepath, timeframe, timezone="Asia/Seoul") -> pd.DataFrame:
    """Load and normalize OHLCV CSV data.

    Parameters:
        filepath: CSV path.
        timeframe: Label such as "5m" or "10m". Stored in df.attrs.
        timezone: Source timezone if datetime strings are timezone-naive.
            Epoch columns are treated as UTC and converted to KST.

    Returns:
        DataFrame indexed by timezone-aware Asia/Seoul datetimes with columns:
        open, high, low, close, volume.
    """
    path = Path(filepath)
    df = pd.read_csv(path)
    df.columns = [_normalize_col(c) for c in df.columns]
    cols = list(df.columns)

    datetime_col = _find_column(
        cols,
        ["datetime", "date_time", "timestamp", "time", "date", "dt"],
    )
    colmap = {
        "open": _find_column(cols, ["open", "o"]),
        "high": _find_column(cols, ["high", "h"]),
        "low": _find_column(cols, ["low", "l"]),
        "close": _find_column(cols, ["close", "c"]),
        "volume": _find_column(cols, ["volume", "vol", "v"]),
    }

    missing = [name for name, col in colmap.items() if col is None]
    if datetime_col is None:
        missing.append("datetime")
    if missing:
        raise ValueError("Missing required column(s): %s" % ", ".join(missing))

    raw_dt = df[datetime_col]
    if pd.api.types.is_numeric_dtype(raw_dt):
        unit = "ms" if raw_dt.dropna().astype("int64").median() > 10**11 else "s"
        dt = pd.to_datetime(raw_dt, unit=unit, utc=True).dt.tz_convert(KST)
    else:
        parsed = pd.to_datetime(raw_dt, errors="coerce")
        if parsed.dt.tz is None:
            source_tz = ZoneInfo(timezone)
            dt = parsed.dt.tz_localize(source_tz, nonexistent="shift_forward", ambiguous="NaT").dt.tz_convert(KST)
        else:
            dt = parsed.dt.tz_convert(KST)

    out = pd.DataFrame(index=dt)
    for target, source in colmap.items():
        out[target] = pd.to_numeric(df[source], errors="coerce").to_numpy()

    out = out[~out.index.isna()].copy()
    out.index.name = "datetime"
    out = out.sort_index()
    out = out[(out.index >= START_DATE) & (out.index < END_DATE_EXCLUSIVE)]
    out.attrs["timeframe"] = timeframe
    out.attrs["source_file"] = str(path)

    report = validate_ohlcv(out)
    print(
        "Loaded %s | timeframe=%s | start=%s | end=%s | rows=%s | missing=%s | duplicates=%s"
        % (
            path,
            timeframe,
            report.start,
            report.end,
            report.rows,
            report.missing_values,
            report.duplicate_datetimes,
        )
    )
    return out


def validate_ohlcv(df: pd.DataFrame) -> ValidationReport:
    """Validate OHLCV data and print a compact report."""
    required = ["open", "high", "low", "close", "volume"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError("DataFrame missing column(s): %s" % ", ".join(missing_cols))
    if df.index.tz is None:
        raise ValueError("DataFrame index must be timezone-aware")

    missing_values = int(df[required].isna().sum().sum())
    duplicate_datetimes = int(df.index.duplicated().sum())
    non_positive = int(((df[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
    invalid_ohlc = int(
        (
            (df["high"] < df[["open", "close", "low"]].max(axis=1))
            | (df["low"] > df[["open", "close", "high"]].min(axis=1))
            | (df["high"] < df["low"])
        ).sum()
    )

    report = ValidationReport(
        rows=int(len(df)),
        start=df.index.min() if len(df) else None,
        end=df.index.max() if len(df) else None,
        missing_values=missing_values,
        duplicate_datetimes=duplicate_datetimes,
        invalid_ohlc_rows=invalid_ohlc,
        non_positive_price_rows=non_positive,
    )
    print(
        "Validation | rows=%s | start=%s | end=%s | missing=%s | duplicates=%s | invalid_ohlc=%s | non_positive=%s"
        % (
            report.rows,
            report.start,
            report.end,
            report.missing_values,
            report.duplicate_datetimes,
            report.invalid_ohlc_rows,
            report.non_positive_price_rows,
        )
    )
    return report


def assign_session(
    df: pd.DataFrame,
    us_open_start="09:30",
    us_open_end="11:00",
    europe_start="08:00",
    europe_end="10:30",
    us_extended_hours=2,
) -> pd.DataFrame:
    """Add DST-aware market session labels.

    Input index must be timezone-aware and is converted to Asia/Seoul.
    London and New York session decisions are made in local market time.
    """
    if df.index.tz is None:
        raise ValueError("DataFrame index must be timezone-aware")

    out = df.copy()
    out.index = out.index.tz_convert(KST)
    out["datetime_kst"] = out.index
    out["datetime_london"] = out.index.tz_convert(LONDON)
    out["datetime_newyork"] = out.index.tz_convert(NEW_YORK)
    out["is_london_dst"] = out["datetime_london"].map(_is_dst)
    out["is_newyork_dst"] = out["datetime_newyork"].map(_is_dst)

    asia_start = time(8, 30)
    asia_end = time(15, 30)
    eu_start = _parse_time_arg(europe_start)
    eu_end = _parse_time_arg(europe_end)
    us_start = _parse_time_arg(us_open_start)
    us_end = _parse_time_arg(us_open_end)

    us_end_minutes = us_end.hour * 60 + us_end.minute
    ext_end_minutes = min(24 * 60, us_end_minutes + int(us_extended_hours * 60))
    ext_end = time(ext_end_minutes // 60, ext_end_minutes % 60) if ext_end_minutes < 24 * 60 else time(23, 59, 59)

    sessions = []
    for ts_kst, ts_lon, ts_ny in zip(out["datetime_kst"], out["datetime_london"], out["datetime_newyork"]):
        if _in_time_range(ts_kst, asia_start, asia_end):
            sessions.append("asia")
        elif _in_time_range(ts_lon, eu_start, eu_end):
            sessions.append("europe")
        elif _in_time_range(ts_ny, us_start, us_end):
            sessions.append("us_open")
        elif _in_time_range(ts_ny, us_end, ext_end):
            sessions.append("us_extended")
        else:
            sessions.append("other")
    out["session"] = sessions
    return out


def summarize_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """Return date/session row counts."""
    if "session" not in df.columns:
        raise ValueError("assign_session() must be called first")
    summary = (
        df.assign(date_kst=df.index.tz_convert(KST).date)
        .groupby(["date_kst", "session"])
        .size()
        .rename("rows")
        .reset_index()
    )
    print(summary.groupby("session")["rows"].sum().sort_index())
    return summary


def get_first_session_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Return the first completed candle per KST date and session."""
    if "session" not in df.columns:
        raise ValueError("assign_session() must be called first")
    work = df[df["session"] != "other"].copy()
    work["date_kst"] = work.index.tz_convert(KST).date
    first_idx = work.groupby(["date_kst", "session"], sort=True).head(1).index
    return work.loc[first_idx].copy()


def debug_session_times(df: pd.DataFrame, dates) -> pd.DataFrame:
    """Print session rows around KST dates to verify DST shifts."""
    if "session" not in df.columns:
        raise ValueError("assign_session() must be called first")
    wanted = {pd.Timestamp(d).date() if not isinstance(d, date) else d for d in dates}
    date_index = pd.Series(df.index.tz_convert(KST).date, index=df.index)
    sample = df.loc[date_index.isin(wanted)]
    cols = [
        "datetime_kst",
        "datetime_london",
        "datetime_newyork",
        "session",
        "is_london_dst",
        "is_newyork_dst",
    ]
    sample = sample[cols]
    print(sample[sample["session"] != "other"].head(80).to_string())
    return sample


def add_bollinger_bands(df: pd.DataFrame, ddof=0) -> pd.DataFrame:
    """Add BB20/2 close bands and BB4/4 open bands."""
    out = df.copy()

    close_mid = out["close"].rolling(20, min_periods=20).mean()
    close_std = out["close"].rolling(20, min_periods=20).std(ddof=ddof)
    out["bb20_2_mid_close"] = close_mid
    out["bb20_2_upper_close"] = close_mid + 2 * close_std
    out["bb20_2_lower_close"] = close_mid - 2 * close_std

    open_mid = out["open"].rolling(4, min_periods=4).mean()
    open_std = out["open"].rolling(4, min_periods=4).std(ddof=ddof)
    out["bb4_4_mid_open"] = open_mid
    out["bb4_4_upper_open"] = open_mid + 4 * open_std
    out["bb4_4_lower_open"] = open_mid - 4 * open_std
    return out


def debug_bollinger_values(df: pd.DataFrame, start, end) -> pd.DataFrame:
    """Print open/close and Bollinger values for a date range."""
    start_ts = pd.Timestamp(start, tz=KST)
    end_ts = pd.Timestamp(end, tz=KST)
    cols = [
        "open",
        "close",
        "bb20_2_mid_close",
        "bb20_2_upper_close",
        "bb20_2_lower_close",
        "bb4_4_mid_open",
        "bb4_4_upper_open",
        "bb4_4_lower_open",
    ]
    sample = df.loc[(df.index >= start_ts) & (df.index <= end_ts), cols]
    print(sample.to_string())
    return sample


def _normalize_direction(direction: str) -> str:
    direction = str(direction).lower().strip()
    if direction not in {"long", "short"}:
        raise ValueError("direction must be 'long' or 'short'")
    return direction


def _breakout_col(direction: str) -> str:
    direction = _normalize_direction(direction)
    return "buy_breakout_double_bb" if direction == "long" else "sell_breakout_double_bb"


def detect_buy_breakout_double_bb(df: pd.DataFrame, direction="long") -> pd.DataFrame:
    """Mark buy breakout double-BB events.

    Definition:
        long:
            close[t] > bb20_2_upper_close[t]
            AND close[t] > bb4_4_upper_open[t]
        short:
            close[t] < bb20_2_lower_close[t]
            AND close[t] < bb4_4_lower_open[t]

    This function only adds a boolean event column. It does not create entries.
    """
    direction = _normalize_direction(direction)
    if direction == "long":
        required = ["close", "bb20_2_upper_close", "bb4_4_upper_open"]
    else:
        required = ["close", "bb20_2_lower_close", "bb4_4_lower_open"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Missing column(s): %s. Run add_bollinger_bands() first." % ", ".join(missing))

    out = df.copy()
    event_col = _breakout_col(direction)
    if direction == "long":
        out[event_col] = (
            (out["close"] > out["bb20_2_upper_close"])
            & (out["close"] > out["bb4_4_upper_open"])
        ).fillna(False)
    else:
        out[event_col] = (
            (out["close"] < out["bb20_2_lower_close"])
            & (out["close"] < out["bb4_4_lower_open"])
        ).fillna(False)
    print("%s breakout double-BB events: %s" % (direction.capitalize(), int(out[event_col].sum())))
    return out


def get_breakout_events(df: pd.DataFrame, direction="long") -> pd.DataFrame:
    """Extract buy breakout double-BB event rows with diagnostic columns."""
    direction = _normalize_direction(direction)
    event_col = _breakout_col(direction)
    if event_col not in df.columns:
        raise ValueError("detect_buy_breakout_double_bb(direction=%s) must be called first" % direction)

    required = ["open", "high", "low", "close"]
    if direction == "long":
        required += ["bb20_2_upper_close", "bb4_4_upper_open"]
    else:
        required += ["bb20_2_lower_close", "bb4_4_lower_open"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Missing column(s): %s" % ", ".join(missing))

    events = df[df[event_col]].copy()
    events["datetime"] = events.index
    events["direction"] = direction
    if "session" not in events.columns:
        # TODO: If session is required by downstream code, call assign_session() before this function.
        events["session"] = "unknown"
    events["timeframe"] = df.attrs.get("timeframe", "unknown")
    events["candle_range"] = events["high"] - events["low"]
    if direction == "long":
        events["close_position"] = (events["close"] - events["low"]) / events["candle_range"]
        band_cols = ["bb20_2_upper_close", "bb4_4_upper_open"]
    else:
        events["close_position"] = (events["high"] - events["close"]) / events["candle_range"]
        band_cols = ["bb20_2_lower_close", "bb4_4_lower_open"]
    events.loc[events["candle_range"] == 0, "close_position"] = pd.NA

    cols = [
        "datetime",
        "direction",
        "session",
        "timeframe",
        "open",
        "high",
        "low",
        "close",
        *band_cols,
        "candle_range",
        "close_position",
    ]
    events = events[cols]
    print("Breakout events sample:")
    print(events.head(10).to_string())
    return events


def summarize_breakout_events(events: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Summarize breakout event counts by year and session."""
    if "datetime" in events.columns:
        dt = pd.DatetimeIndex(events["datetime"])
    else:
        dt = events.index
    by_year = events.assign(year=dt.tz_convert(KST).year).groupby("year").size().rename("events").reset_index()
    if "session" in events.columns:
        by_session = events.groupby("session").size().rename("events").reset_index()
    else:
        by_session = pd.DataFrame(columns=["session", "events"])
    if "direction" in events.columns:
        by_direction = events.groupby("direction").size().rename("events").reset_index()
    else:
        by_direction = pd.DataFrame(columns=["direction", "events"])

    print("Breakout events by year:")
    print(by_year.to_string(index=False))
    print("Breakout events by session:")
    print(by_session.to_string(index=False))
    print("Breakout events by direction:")
    print(by_direction.to_string(index=False))
    return {"by_year": by_year, "by_session": by_session, "by_direction": by_direction}


def find_buy_pullback_entries(df: pd.DataFrame, max_bars=None, direction="long") -> pd.DataFrame:
    """Find first buy pullback entry candidate after each breakout event.

    Pullback definition:
        long: low[k] < bb4_4_lower_open[k]
        short: high[k] > bb4_4_upper_open[k]

    Entry assumption:
        entry_time = datetime[k + 1]
        entry_price = open[k + 1]

    max_bars:
        None for no limit, 6 for 1~6 bars, 10 for 1~10 bars, etc.
    """
    direction = _normalize_direction(direction)
    event_col = _breakout_col(direction)
    required = [
        event_col,
        "open",
        "high",
        "low",
        "close",
        "bb4_4_lower_open",
        "bb4_4_upper_open",
        "bb20_2_mid_close",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Missing column(s): %s" % ", ".join(missing))

    if "session" not in df.columns:
        # TODO: Decide whether session should be mandatory. For now keep candidates usable without assign_session().
        session_values = pd.Series("unknown", index=df.index)
    else:
        session_values = df["session"]

    breakout_positions = [i for i, flag in enumerate(df[event_col].to_numpy()) if bool(flag)]
    rows = []
    idx = df.index
    lows = df["low"].to_numpy()
    highs = df["high"].to_numpy()
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    lower4 = df["bb4_4_lower_open"].to_numpy()
    upper4 = df["bb4_4_upper_open"].to_numpy()
    mid20 = df["bb20_2_mid_close"].to_numpy()
    timeframe = df.attrs.get("timeframe", "unknown")

    for breakout_pos in breakout_positions:
        search_end = len(df) - 2
        if max_bars is not None:
            search_end = min(search_end, breakout_pos + int(max_bars))
        if breakout_pos + 1 > search_end:
            continue

        pullback_pos = None
        for k in range(breakout_pos + 1, search_end + 1):
            if direction == "long":
                if pd.isna(lower4[k]):
                    continue
                touched = lows[k] < lower4[k]
            else:
                if pd.isna(upper4[k]):
                    continue
                touched = highs[k] > upper4[k]
            if touched:
                pullback_pos = k
                break
        if pullback_pos is None:
            continue

        entry_pos = pullback_pos + 1
        if entry_pos >= len(df):
            continue

        midline_broken = False
        for x in range(breakout_pos + 1, entry_pos):
            if direction == "long":
                broken = not pd.isna(mid20[x]) and closes[x] < mid20[x]
            else:
                broken = not pd.isna(mid20[x]) and closes[x] > mid20[x]
            if broken:
                midline_broken = True
                break

        candle_range = highs[breakout_pos] - lows[breakout_pos]
        if candle_range == 0:
            breakout_close_position = pd.NA
        elif direction == "long":
            breakout_close_position = (closes[breakout_pos] - lows[breakout_pos]) / candle_range
        else:
            breakout_close_position = (highs[breakout_pos] - closes[breakout_pos]) / candle_range

        rows.append({
            "direction": direction,
            "breakout_time": idx[breakout_pos],
            "pullback_touch_time": idx[pullback_pos],
            "entry_time": idx[entry_pos],
            "entry_price": opens[entry_pos],
            "session": session_values.iloc[entry_pos],
            "timeframe": timeframe,
            "bars_to_pullback": pullback_pos - breakout_pos,
            "midline_broken_before_entry": midline_broken,
            "breakout_close_position": breakout_close_position,
        })

    candidates = pd.DataFrame(rows)
    window_name = "no_limit" if max_bars is None else "within_%s_bars" % max_bars
    if not candidates.empty:
        candidates["candidate_window"] = window_name
    print("%s pullback candidates %s: %s" % (direction.capitalize(), window_name, len(candidates)))
    print(candidates.head(10).to_string(index=False) if len(candidates) else "(none)")
    return candidates


def create_pullback_entry_candidates(df: pd.DataFrame, direction="long") -> pd.DataFrame:
    """Create no-limit, 1~6 bar, and 1~10 bar pullback candidate sets."""
    direction = _normalize_direction(direction)
    parts = [
        find_buy_pullback_entries(df, max_bars=None, direction=direction),
        find_buy_pullback_entries(df, max_bars=6, direction=direction),
        find_buy_pullback_entries(df, max_bars=10, direction=direction),
    ]
    candidates = pd.concat([p for p in parts if not p.empty], ignore_index=True) if any(not p.empty for p in parts) else pd.DataFrame()
    print("All pullback candidate rows: %s" % len(candidates))
    return candidates


def summarize_pullback_candidates(candidates: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Summarize pullback candidates by window, session, midline group, and bars_to_pullback."""
    if candidates.empty:
        print("No pullback candidates to summarize")
        return {}

    by_window = candidates.groupby("candidate_window").size().rename("candidates").reset_index()
    by_session = candidates.groupby(["candidate_window", "session"]).size().rename("candidates").reset_index()
    by_midline = (
        candidates.groupby(["candidate_window", "midline_broken_before_entry"])
        .size()
        .rename("candidates")
        .reset_index()
    )
    by_bars = candidates.groupby(["candidate_window", "bars_to_pullback"]).size().rename("candidates").reset_index()

    print("Pullback candidates by window:")
    print(by_window.to_string(index=False))
    print("Pullback candidates by session:")
    print(by_session.to_string(index=False))
    print("Pullback candidates by midline_broken_before_entry:")
    print(by_midline.to_string(index=False))
    print("Pullback candidates by bars_to_pullback:")
    print(by_bars.head(50).to_string(index=False))

    return {
        "by_window": by_window,
        "by_session": by_session,
        "by_midline": by_midline,
        "by_bars_to_pullback": by_bars,
    }


def _year_bucket(ts) -> str:
    year = pd.Timestamp(ts).year
    if 2010 <= year <= 2014:
        return "2010_2014"
    if 2015 <= year <= 2019:
        return "2015_2019"
    if 2020 <= year <= 2026:
        return "2020_2026"
    return "outside"


def _bool_ratio_summary(df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    group_cols = group_cols or []
    cols = [
        "invalid_any",
        "invalid_breakout",
        "invalid_pullback",
        "invalid_entry",
        "missing_band_values",
        "invalid_v",
    ]

    def _agg(group):
        row = {"candidates": int(len(group))}
        for col in cols:
            if col in group.columns:
                row[col] = int(group[col].fillna(False).astype(bool).sum())
                row[col + "_rate"] = float(group[col].fillna(False).astype(bool).mean())
        return pd.Series(row)

    if not group_cols:
        return _agg(df).to_frame().T
    return df.groupby(group_cols, dropna=False).apply(_agg).reset_index()


def audit_pullback_candidates(df: pd.DataFrame, candidates: pd.DataFrame, output_dir) -> dict[str, pd.DataFrame]:
    """Validate generated long/short pullback candidates without changing strategy logic.

    The function writes invalid cases and summary CSV files to output_dir.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    if candidates.empty:
        empty = candidates.copy()
        empty.to_csv(output_path / "audit_invalid_candidates.csv", index=False, encoding="utf-8-sig")
        return {"audited": empty, "invalid": empty}

    required_df_cols = [
        "open",
        "high",
        "low",
        "close",
        "bb20_2_upper_close",
        "bb20_2_lower_close",
        "bb4_4_upper_open",
        "bb4_4_lower_open",
    ]
    missing_df = [c for c in required_df_cols if c not in df.columns]
    if missing_df:
        raise ValueError("Missing df column(s): %s" % ", ".join(missing_df))

    required_candidate_cols = [
        "breakout_time",
        "pullback_touch_time",
        "entry_time",
        "entry_price",
    ]
    missing_candidates = [c for c in required_candidate_cols if c not in candidates.columns]
    if missing_candidates:
        raise ValueError("Missing candidate column(s): %s" % ", ".join(missing_candidates))

    audited_rows = []
    idx = df.index
    for _, cand in candidates.iterrows():
        row = cand.to_dict()
        direction = _normalize_direction(cand.get("direction", "long"))
        row["direction"] = direction

        breakout_time = cand["breakout_time"]
        pullback_time = cand["pullback_touch_time"]
        entry_time = cand["entry_time"]

        breakout_exists = breakout_time in df.index
        pullback_exists = pullback_time in df.index
        entry_exists = entry_time in df.index
        row["breakout_row_exists"] = breakout_exists
        row["pullback_row_exists"] = pullback_exists
        row["entry_row_exists"] = entry_exists

        if breakout_exists:
            b = df.loc[breakout_time]
            row["breakout_close"] = b["close"]
            row["breakout_bb20_upper"] = b["bb20_2_upper_close"]
            row["breakout_bb20_lower"] = b["bb20_2_lower_close"]
            row["breakout_bb44_upper"] = b["bb4_4_upper_open"]
            row["breakout_bb44_lower"] = b["bb4_4_lower_open"]
        else:
            b = pd.Series(dtype=float)
            row["breakout_close"] = pd.NA
            row["breakout_bb20_upper"] = pd.NA
            row["breakout_bb20_lower"] = pd.NA
            row["breakout_bb44_upper"] = pd.NA
            row["breakout_bb44_lower"] = pd.NA

        if pullback_exists:
            p = df.loc[pullback_time]
            row["pullback_low"] = p["low"]
            row["pullback_high"] = p["high"]
            row["pullback_bb44_lower"] = p["bb4_4_lower_open"]
            row["pullback_bb44_upper"] = p["bb4_4_upper_open"]
        else:
            p = pd.Series(dtype=float)
            row["pullback_low"] = pd.NA
            row["pullback_high"] = pd.NA
            row["pullback_bb44_lower"] = pd.NA
            row["pullback_bb44_upper"] = pd.NA

        if direction == "long":
            row["breakout_valid_long"] = bool(
                breakout_exists
                and pd.notna(b["close"])
                and pd.notna(b["bb20_2_upper_close"])
                and pd.notna(b["bb4_4_upper_open"])
                and b["close"] > b["bb20_2_upper_close"]
                and b["close"] > b["bb4_4_upper_open"]
            )
            row["breakout_valid_short"] = pd.NA
            row["pullback_valid_long"] = bool(
                pullback_exists
                and pd.notna(p["low"])
                and pd.notna(p["bb4_4_lower_open"])
                and p["low"] < p["bb4_4_lower_open"]
            )
            row["pullback_valid_short"] = pd.NA
            row["breakout_close_minus_bb20_upper"] = row["breakout_close"] - row["breakout_bb20_upper"] if breakout_exists else pd.NA
            row["breakout_close_minus_bb44_upper"] = row["breakout_close"] - row["breakout_bb44_upper"] if breakout_exists else pd.NA
            row["bb44_lower_minus_pullback_low"] = row["pullback_bb44_lower"] - row["pullback_low"] if pullback_exists else pd.NA
            row["bb20_lower_minus_breakout_close"] = pd.NA
            row["bb44_lower_minus_breakout_close"] = pd.NA
            row["pullback_high_minus_bb44_upper"] = pd.NA
            breakout_valid = row["breakout_valid_long"]
            pullback_valid = row["pullback_valid_long"]
        else:
            row["breakout_valid_long"] = pd.NA
            row["breakout_valid_short"] = bool(
                breakout_exists
                and pd.notna(b["close"])
                and pd.notna(b["bb20_2_lower_close"])
                and pd.notna(b["bb4_4_lower_open"])
                and b["close"] < b["bb20_2_lower_close"]
                and b["close"] < b["bb4_4_lower_open"]
            )
            row["pullback_valid_long"] = pd.NA
            row["pullback_valid_short"] = bool(
                pullback_exists
                and pd.notna(p["high"])
                and pd.notna(p["bb4_4_upper_open"])
                and p["high"] > p["bb4_4_upper_open"]
            )
            row["breakout_close_minus_bb20_upper"] = pd.NA
            row["breakout_close_minus_bb44_upper"] = pd.NA
            row["bb44_lower_minus_pullback_low"] = pd.NA
            row["bb20_lower_minus_breakout_close"] = row["breakout_bb20_lower"] - row["breakout_close"] if breakout_exists else pd.NA
            row["bb44_lower_minus_breakout_close"] = row["breakout_bb44_lower"] - row["breakout_close"] if breakout_exists else pd.NA
            row["pullback_high_minus_bb44_upper"] = row["pullback_high"] - row["pullback_bb44_upper"] if pullback_exists else pd.NA
            breakout_valid = row["breakout_valid_short"]
            pullback_valid = row["pullback_valid_short"]

        expected_entry_time = pd.NaT
        if pullback_exists:
            pullback_pos = idx.searchsorted(pullback_time)
            if pullback_pos + 1 < len(idx):
                expected_entry_time = idx[pullback_pos + 1]
        row["expected_entry_time"] = expected_entry_time
        if entry_exists:
            row["entry_open_at_time"] = df.loc[entry_time, "open"]
        else:
            row["entry_open_at_time"] = pd.NA
        row["entry_time_is_next_candle"] = bool(pd.notna(expected_entry_time) and entry_time == expected_entry_time)
        row["entry_price_matches_open"] = bool(entry_exists and pd.notna(cand["entry_price"]) and cand["entry_price"] == df.loc[entry_time, "open"])
        row["entry_valid"] = row["entry_time_is_next_candle"] and row["entry_price_matches_open"]

        band_values = [
            row["breakout_bb20_upper"],
            row["breakout_bb20_lower"],
            row["breakout_bb44_upper"],
            row["breakout_bb44_lower"],
            row["pullback_bb44_upper"],
            row["pullback_bb44_lower"],
        ]
        row["missing_band_values"] = any(pd.isna(v) for v in band_values)
        row["invalid_breakout"] = (not bool(breakout_valid)) or row["missing_band_values"]
        row["invalid_pullback"] = (not bool(pullback_valid)) or row["missing_band_values"]
        row["invalid_entry"] = not row["entry_valid"]
        if "invalid_v" in cand.index:
            row["invalid_v"] = bool(cand["invalid_v"])
        else:
            v_flags = []
            for col in ["v_session_opening_range", "v_avg_range_20"]:
                if col in cand.index:
                    v_flags.append(pd.isna(cand[col]) or cand[col] <= 0)
            row["invalid_v"] = any(v_flags) if v_flags else False
        row["invalid_any"] = bool(
            row["invalid_breakout"]
            or row["invalid_pullback"]
            or row["invalid_entry"]
            or row["missing_band_values"]
            or row["invalid_v"]
        )
        row["year_bucket"] = _year_bucket(entry_time)
        audited_rows.append(row)

    audited = pd.DataFrame(audited_rows)
    invalid = audited[audited["invalid_any"]].copy()

    summaries = {
        "summary_overall": _bool_ratio_summary(audited),
        "summary_by_direction": _bool_ratio_summary(audited, ["direction"]),
        "summary_by_timeframe": _bool_ratio_summary(audited, ["timeframe"]) if "timeframe" in audited.columns else pd.DataFrame(),
        "summary_by_session": _bool_ratio_summary(audited, ["session"]) if "session" in audited.columns else pd.DataFrame(),
        "summary_by_year_bucket": _bool_ratio_summary(audited, ["year_bucket"]),
    }

    audited.to_csv(output_path / "audit_all_candidates.csv", index=False, encoding="utf-8-sig")
    invalid.to_csv(output_path / "audit_invalid_candidates.csv", index=False, encoding="utf-8-sig")
    for name, table in summaries.items():
        table.to_csv(output_path / ("%s.csv" % name), index=False, encoding="utf-8-sig")

    print("Audit candidates: %s | invalid: %s" % (len(audited), len(invalid)))
    print("Audit invalid ratios overall:")
    print(summaries["summary_overall"].to_string(index=False))
    if len(invalid):
        sample_cols = [
            "direction",
            "timeframe",
            "session",
            "breakout_time",
            "pullback_touch_time",
            "entry_time",
            "invalid_breakout",
            "invalid_pullback",
            "invalid_entry",
            "missing_band_values",
            "invalid_v",
        ]
        print("Top invalid samples:")
        print(invalid[[c for c in sample_cols if c in invalid.columns]].head(20).to_string(index=False))

    result = {"audited": audited, "invalid": invalid}
    result.update(summaries)
    return result


def export_audit_samples_by_year_bucket(df: pd.DataFrame, candidates: pd.DataFrame, output_dir, n_per_direction=5) -> pd.DataFrame:
    """Export OHLCV/band rows around sampled candidates for manual CSV audit.

    For each year bucket and direction, saves up to n_per_direction samples.
    Window: breakout_time - 5 bars through entry_time + 10 bars.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    if candidates.empty:
        empty = pd.DataFrame()
        empty.to_csv(output_path / "audit_sample_windows.csv", index=False, encoding="utf-8-sig")
        return empty

    work = candidates.copy()
    if "direction" not in work.columns:
        work["direction"] = "long"
    work["year_bucket"] = work["entry_time"].map(_year_bucket)
    work = work.sort_values("breakout_time")

    base_cols = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "bb20_2_mid_close",
        "bb20_2_upper_close",
        "bb20_2_lower_close",
        "bb4_4_mid_open",
        "bb4_4_upper_open",
        "bb4_4_lower_open",
        "session",
    ]
    cols = [c for c in base_cols if c in df.columns]
    rows = []
    idx = df.index

    for bucket in ["2010_2014", "2015_2019", "2020_2026"]:
        for direction in ["long", "short"]:
            sample = work[(work["year_bucket"] == bucket) & (work["direction"] == direction)].head(int(n_per_direction))
            for sample_no, (_, cand) in enumerate(sample.iterrows(), start=1):
                breakout_time = cand["breakout_time"]
                entry_time = cand["entry_time"]
                if breakout_time not in idx or entry_time not in idx:
                    continue
                start_pos = max(0, idx.searchsorted(breakout_time) - 5)
                end_pos = min(len(idx) - 1, idx.searchsorted(entry_time) + 10)
                window = df.iloc[start_pos:end_pos + 1][cols].copy()
                for ts, row in window.iterrows():
                    out = {
                        "year_bucket": bucket,
                        "direction": direction,
                        "sample_no": sample_no,
                        "datetime": ts,
                        "relative_event": "",
                        "breakout_time": breakout_time,
                        "pullback_touch_time": cand["pullback_touch_time"],
                        "entry_time": entry_time,
                        "entry_price": cand["entry_price"],
                        "bars_to_pullback": cand.get("bars_to_pullback", pd.NA),
                        "midline_broken_before_entry": cand.get("midline_broken_before_entry", pd.NA),
                    }
                    if ts == breakout_time:
                        out["relative_event"] = "breakout"
                    elif ts == cand["pullback_touch_time"]:
                        out["relative_event"] = "pullback_touch"
                    elif ts == entry_time:
                        out["relative_event"] = "entry"
                    for col in cols:
                        out[col] = row[col]
                    rows.append(out)

    samples = pd.DataFrame(rows)
    samples.to_csv(output_path / "audit_sample_windows.csv", index=False, encoding="utf-8-sig")
    print("Audit sample rows exported: %s" % len(samples))
    return samples


def add_v_metrics_to_candidates(df: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    """Attach 1V volatility metrics to entry candidates.

    v_session_opening_range:
        high - low of the first completed candle in the current contiguous
        session block.

    v_avg_range_20:
        rolling mean of high-low over the 20 candles before entry.

    This function does not simulate grid fills.
    """
    if candidates.empty:
        print("No candidates for V metrics")
        return candidates.copy()
    required = ["high", "low"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Missing column(s): %s" % ", ".join(missing))
    if "session" not in df.columns:
        # TODO: Decide whether V session mode should be allowed without explicit session labels.
        raise ValueError("assign_session() must be called before session opening range V")
    if "entry_time" not in candidates.columns:
        raise ValueError("candidates must include entry_time")

    work = df.copy()
    work["range"] = work["high"] - work["low"]
    session_changed = work["session"].ne(work["session"].shift(1))
    work["_session_block"] = session_changed.cumsum()
    first_range_by_block = work.groupby("_session_block")["range"].transform("first")
    work["v_session_opening_range"] = first_range_by_block
    work["v_avg_range_20"] = work["range"].rolling(20, min_periods=20).mean().shift(1)

    cols = ["session", "v_session_opening_range", "v_avg_range_20"]
    lookup = work[cols]
    out = candidates.copy()
    out = out.join(lookup, on="entry_time", rsuffix="_at_entry")
    if "session_at_entry" in out.columns:
        # Keep the candidate session as the canonical label. The joined copy is only diagnostic.
        out = out.drop(columns=["session_at_entry"])

    out["invalid_v_session_opening_range"] = out["v_session_opening_range"].isna() | (out["v_session_opening_range"] <= 0)
    out["invalid_v_avg_range_20"] = out["v_avg_range_20"].isna() | (out["v_avg_range_20"] <= 0)
    out["invalid_v"] = out["invalid_v_session_opening_range"] | out["invalid_v_avg_range_20"]

    print("Candidates with V metrics:")
    print(out.head(10).to_string(index=False))
    print(
        "invalid_v any=%s | session=%s | avg20=%s"
        % (
            int(out["invalid_v"].sum()),
            int(out["invalid_v_session_opening_range"].sum()),
            int(out["invalid_v_avg_range_20"].sum()),
        )
    )
    return out


def summarize_v_metrics(candidates: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Summarize 1V values by session."""
    required = ["session", "v_session_opening_range", "v_avg_range_20"]
    missing = [c for c in required if c not in candidates.columns]
    if missing:
        raise ValueError("Missing column(s): %s. Run add_v_metrics_to_candidates() first." % ", ".join(missing))

    def _summary(col: str) -> pd.DataFrame:
        return (
            candidates.groupby("session")[col]
            .agg(["count", "mean", "median", "min", "max"])
            .reset_index()
            .rename(columns={
                "count": "%s_count" % col,
                "mean": "%s_mean" % col,
                "median": "%s_median" % col,
                "min": "%s_min" % col,
                "max": "%s_max" % col,
            })
        )

    session_v = _summary("v_session_opening_range")
    avg20_v = _summary("v_avg_range_20")
    print("V session_opening_range summary:")
    print(session_v.to_string(index=False))
    print("V avg_range_20 summary:")
    print(avg20_v.to_string(index=False))
    return {
        "session_opening_range": session_v,
        "avg_range_20": avg20_v,
    }


def simulate_grid_path(
    df: pd.DataFrame,
    candidates: pd.DataFrame,
    v_method,
    max_entries=3,
    max_holding_bars=48,
) -> pd.DataFrame:
    """Observe long/short grid fills and path behavior after each entry candidate.

    This function intentionally does not calculate PnL, take-profit, or stop-loss.

    v_method:
        "session_opening_range" or "avg_range_20"

    max_entries:
        Maximum entries allowed to affect avg_entry_price. Entry_4/Entry_5 are
        still observed via reached_4th_entry and level columns.

    TODO: Quantity weighting is assumed equal-unit because this step only asks
    for path/fill behavior. Add size schedules in a later step if needed.
    """
    method_to_col = {
        "session_opening_range": "v_session_opening_range",
        "avg_range_20": "v_avg_range_20",
    }
    if v_method not in method_to_col:
        raise ValueError("v_method must be one of: %s" % ", ".join(method_to_col))
    v_col = method_to_col[v_method]
    required_candidate_cols = ["entry_time", "entry_price", v_col]
    missing = [c for c in required_candidate_cols if c not in candidates.columns]
    if missing:
        raise ValueError("Missing candidate column(s): %s" % ", ".join(missing))
    required_df_cols = ["high", "low"]
    missing_df = [c for c in required_df_cols if c not in df.columns]
    if missing_df:
        raise ValueError("Missing df column(s): %s" % ", ".join(missing_df))

    max_entries = int(max_entries)
    if max_entries < 1 or max_entries > 5:
        raise ValueError("max_entries must be between 1 and 5")

    idx = df.index
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    rows = []

    for _, cand in candidates.iterrows():
        v = cand[v_col]
        entry_time = cand["entry_time"]
        entry_price = cand["entry_price"]
        direction = _normalize_direction(cand.get("direction", "long"))
        if pd.isna(v) or v <= 0 or pd.isna(entry_price):
            row = cand.to_dict()
            row.update({
                "direction": direction,
                "v_method": v_method,
                "filled_entries_count": 0,
                "entry_1_price": entry_price,
                "entry_2_price": pd.NA,
                "entry_3_price": pd.NA,
                "entry_4_price": pd.NA,
                "entry_5_price": pd.NA,
                "avg_entry_price": pd.NA,
                "max_adverse_excursion_v": pd.NA,
                "max_favorable_excursion_v": pd.NA,
                "returned_to_entry_1_after_3_fills": False,
                "reached_4th_entry": False,
            })
            rows.append(row)
            continue

        entry_pos = idx.searchsorted(entry_time)
        if entry_pos >= len(df):
            continue

        if direction == "long":
            levels = [entry_price - n * v for n in range(5)]
        else:
            levels = [entry_price + n * v for n in range(5)]
        fill_flags = [False] * 5
        fill_flags[0] = True
        observed_fills = 1
        max_allowed_fill = min(max_entries, 5)
        filled_prices = [levels[0]]
        reached_4th = False
        returned_to_entry1_after_3 = False
        lowest = entry_price
        highest = entry_price

        end_pos = min(len(df) - 1, entry_pos + int(max_holding_bars) - 1)
        for pos in range(entry_pos, end_pos + 1):
            lo = lows[pos]
            hi = highs[pos]
            if lo < lowest:
                lowest = lo
            if hi > highest:
                highest = hi

            for level_idx, level in enumerate(levels):
                if direction == "long":
                    touched = lo <= level
                else:
                    touched = hi >= level
                if touched:
                    observed_fills = max(observed_fills, level_idx + 1)
                    if level_idx == 3:
                        reached_4th = True
                    if level_idx < max_allowed_fill and not fill_flags[level_idx]:
                        fill_flags[level_idx] = True
                        filled_prices.append(level)

            if direction == "long":
                returned = hi >= entry_price
            else:
                returned = lo <= entry_price
            if len(filled_prices) >= 3 and returned:
                returned_to_entry1_after_3 = True

        avg_entry = sum(filled_prices) / len(filled_prices)
        if direction == "long":
            mae_v = max(0.0, (avg_entry - lowest) / v)
            mfe_v = max(0.0, (highest - avg_entry) / v)
        else:
            mae_v = max(0.0, (highest - avg_entry) / v)
            mfe_v = max(0.0, (avg_entry - lowest) / v)

        row = cand.to_dict()
        row.update({
            "direction": direction,
            "v_method": v_method,
            "filled_entries_count": min(observed_fills, max_allowed_fill),
            "entry_1_price": levels[0],
            "entry_2_price": levels[1],
            "entry_3_price": levels[2],
            "entry_4_price": levels[3],
            "entry_5_price": levels[4],
            "avg_entry_price": avg_entry,
            "max_adverse_excursion_v": mae_v,
            "max_favorable_excursion_v": mfe_v,
            "returned_to_entry_1_after_3_fills": returned_to_entry1_after_3,
            "reached_4th_entry": reached_4th,
        })
        rows.append(row)

    results = pd.DataFrame(rows)
    print("Grid path results v_method=%s max_entries=%s max_holding_bars=%s rows=%s" % (
        v_method,
        max_entries,
        max_holding_bars,
        len(results),
    ))
    print(results.head(10).to_string(index=False) if len(results) else "(none)")
    return results


def summarize_grid_behavior(results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Summarize grid fill/path behavior by session, midline group, and pullback bars."""
    if results.empty:
        print("No grid path results to summarize")
        return {}
    required = [
        "filled_entries_count",
        "max_adverse_excursion_v",
        "max_favorable_excursion_v",
        "returned_to_entry_1_after_3_fills",
        "reached_4th_entry",
    ]
    missing = [c for c in required if c not in results.columns]
    if missing:
        raise ValueError("Missing result column(s): %s" % ", ".join(missing))

    def _agg(group_cols):
        return (
            results.groupby(group_cols)
            .agg(
                candidates=("entry_time", "count"),
                avg_filled_entries=("filled_entries_count", "mean"),
                fill1=("filled_entries_count", lambda s: int((s == 1).sum())),
                fill2=("filled_entries_count", lambda s: int((s == 2).sum())),
                fill3plus=("filled_entries_count", lambda s: int((s >= 3).sum())),
                mae_v_avg=("max_adverse_excursion_v", "mean"),
                mfe_v_avg=("max_favorable_excursion_v", "mean"),
                returned_to_entry1_after_3_rate=("returned_to_entry_1_after_3_fills", "mean"),
                reached_4th_entry_rate=("reached_4th_entry", "mean"),
            )
            .reset_index()
        )

    by_session = _agg(["session"]) if "session" in results.columns else pd.DataFrame()
    by_direction = _agg(["direction"]) if "direction" in results.columns else pd.DataFrame()
    by_midline = _agg(["midline_broken_before_entry"]) if "midline_broken_before_entry" in results.columns else pd.DataFrame()
    by_bars = _agg(["bars_to_pullback"]) if "bars_to_pullback" in results.columns else pd.DataFrame()

    for table in (by_session, by_direction, by_midline, by_bars):
        if not table.empty:
            for col in ["returned_to_entry1_after_3_rate", "reached_4th_entry_rate"]:
                table[col] = (table[col] * 100).round(2)
            for col in ["avg_filled_entries", "mae_v_avg", "mfe_v_avg"]:
                table[col] = table[col].round(4)

    print("Grid behavior by session:")
    print(by_session.to_string(index=False) if not by_session.empty else "(not available)")
    print("Grid behavior by direction:")
    print(by_direction.to_string(index=False) if not by_direction.empty else "(not available)")
    print("Grid behavior by midline_broken_before_entry:")
    print(by_midline.to_string(index=False) if not by_midline.empty else "(not available)")
    print("Grid behavior by bars_to_pullback:")
    print(by_bars.head(50).to_string(index=False) if not by_bars.empty else "(not available)")

    return {
        "by_session": by_session,
        "by_direction": by_direction,
        "by_midline": by_midline,
        "by_bars_to_pullback": by_bars,
    }


def _v_column_for_method(v_method: str) -> str:
    method_to_col = {
        "session_opening_range": "v_session_opening_range",
        "avg_range_20": "v_avg_range_20",
    }
    if v_method not in method_to_col:
        raise ValueError("v_method must be one of: %s" % ", ".join(method_to_col))
    return method_to_col[v_method]


def _exit_targets_for_model(model_name: str, avg_entry: float, v: float, direction="long"):
    direction = _normalize_direction(direction)
    sign = 1.0 if direction == "long" else -1.0
    if model_name == "split_v_targets":
        return [
            {"price": avg_entry + sign * 0.5 * v, "fraction": 0.40, "label": "target_0_5v"},
            {"price": avg_entry + sign * 1.0 * v, "fraction": 0.40, "label": "target_1_0v"},
            {"price": avg_entry + sign * 2.0 * v, "fraction": 1.00, "label": "target_2_0v"},
        ]
    if model_name == "conservative_psychology_model":
        return [
            {"price": avg_entry + sign * 0.3 * v, "fraction": 0.50, "label": "target_0_3v"},
            {"price": avg_entry + sign * 0.8 * v, "fraction": 0.30, "label": "target_0_8v"},
            {"price": avg_entry + sign * 1.5 * v, "fraction": 1.00, "label": "target_1_5v"},
        ]
    if model_name == "single_target_1v":
        return [
            {"price": avg_entry + sign * 1.0 * v, "fraction": 1.00, "label": "target_1_0v_full"},
        ]
    if model_name == "single_target_1_5v":
        return [
            {"price": avg_entry + sign * 1.5 * v, "fraction": 1.00, "label": "target_1_5v_full"},
        ]
    if model_name == "two_step_50_50":
        return [
            {"price": avg_entry + sign * 0.7 * v, "fraction": 0.50, "label": "target_0_7v_50pct"},
            {"price": avg_entry + sign * 1.5 * v, "fraction": 1.00, "label": "target_1_5v_50pct"},
        ]
    raise ValueError("Unsupported target model: %s" % model_name)


def _close_units(
    units_to_close: float,
    exit_price: float,
    open_units: float,
    cost_basis_points: float,
    realized_points: float,
    trade_cost_points_per_unit: float,
    direction="long",
):
    direction = _normalize_direction(direction)
    units_to_close = min(units_to_close, open_units)
    if units_to_close <= 0:
        return open_units, cost_basis_points, realized_points
    avg_cost = cost_basis_points / open_units
    if direction == "long":
        realized_points += (exit_price - avg_cost) * units_to_close
    else:
        realized_points += (avg_cost - exit_price) * units_to_close
    realized_points -= trade_cost_points_per_unit * units_to_close
    open_units -= units_to_close
    cost_basis_points -= avg_cost * units_to_close
    if open_units <= 1e-12:
        open_units = 0.0
        cost_basis_points = 0.0
    return open_units, cost_basis_points, realized_points


def backtest_exit_model(
    df: pd.DataFrame,
    grid_results: pd.DataFrame,
    model_name,
    conservative_same_bar=True,
    fee_points=0.0,
    slippage_points=0.0,
    max_entries=3,
    max_holding_bars=48,
) -> pd.DataFrame:
    """Backtest long/short stop/take-profit exit models on grid path results.

    model_name:
        "defensive_return_to_entry1", "split_v_targets",
        "conservative_psychology_model", "single_target_1v",
        "single_target_1_5v", "two_step_50_50", or
        "defensive_entry1_full_exit".

    Costs:
        fee_points and slippage_points are charged per unit per execution.
        For example, one entry and one exit both subtract cost.

    TODO: Partial exits followed by additional grid fills can be defined many
    ways. This implementation recalculates the remaining-position target ladder
    after a new fill, preserving already realized PnL.
    """
    supported = {
        "defensive_return_to_entry1",
        "defensive_entry1_full_exit",
        "split_v_targets",
        "conservative_psychology_model",
        "single_target_1v",
        "single_target_1_5v",
        "two_step_50_50",
    }
    if model_name not in supported:
        raise ValueError("model_name must be one of: %s" % ", ".join(sorted(supported)))
    if grid_results.empty:
        print("No grid results to backtest")
        return pd.DataFrame()

    required_grid_cols = ["entry_time", "entry_1_price", "v_method"]
    missing = [c for c in required_grid_cols if c not in grid_results.columns]
    if missing:
        raise ValueError("Missing grid result column(s): %s" % ", ".join(missing))
    required_df_cols = ["open", "high", "low", "close"]
    missing_df = [c for c in required_df_cols if c not in df.columns]
    if missing_df:
        raise ValueError("Missing df column(s): %s" % ", ".join(missing_df))

    idx = df.index
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    trade_cost = float(fee_points) + float(slippage_points)
    max_entries = int(max_entries)
    if max_entries < 1 or max_entries > 5:
        raise ValueError("max_entries must be between 1 and 5")

    rows = []
    for _, grid in grid_results.iterrows():
        v_method = grid["v_method"]
        v_col = _v_column_for_method(v_method)
        if v_col not in grid.index:
            raise ValueError("Missing V column for v_method %s: %s" % (v_method, v_col))
        v = grid[v_col]
        entry_1 = grid["entry_1_price"]
        entry_time = grid["entry_time"]
        direction = _normalize_direction(grid.get("direction", "long"))
        if pd.isna(v) or v <= 0 or pd.isna(entry_1):
            continue

        entry_pos = idx.searchsorted(entry_time)
        if entry_pos >= len(df):
            continue
        end_pos = min(len(df) - 1, entry_pos + int(max_holding_bars) - 1)
        if direction == "long":
            stop_price = entry_1 - 3.0 * v
            grid_levels = [entry_1 - n * v for n in range(max_entries)]
        else:
            stop_price = entry_1 + 3.0 * v
            grid_levels = [entry_1 + n * v for n in range(max_entries)]

        filled_flags = [False] * max_entries
        filled_flags[0] = True
        max_filled_count = 1
        entry_executions_count = 1
        exit_executions_count = 0
        open_units = 1.0
        cost_basis_points = float(entry_1) + trade_cost if direction == "long" else float(entry_1) - trade_cost
        realized_points = 0.0
        exit_reason = "time_exit"
        target_index = 0
        defensive_first_exit_done = False
        lowest = float(entry_1)
        highest = float(entry_1)
        exit_time = idx[end_pos]

        def avg_entry_now():
            return cost_basis_points / open_units if open_units > 0 else math.nan

        def reset_targets():
            if model_name == "defensive_return_to_entry1":
                base_model = "split_v_targets"
            elif model_name == "defensive_entry1_full_exit":
                base_model = "single_target_1v"
            else:
                base_model = model_name
            return _exit_targets_for_model(
                base_model,
                avg_entry_now(),
                float(v),
                direction=direction,
            )

        targets = reset_targets()

        for pos in range(entry_pos, end_pos + 1):
            hi = float(highs[pos])
            lo = float(lows[pos])
            lowest = min(lowest, lo)
            highest = max(highest, hi)

            def process_stop():
                nonlocal open_units, cost_basis_points, realized_points, exit_reason, exit_time, exit_executions_count
                if direction == "long":
                    stop_hit = lo <= stop_price
                else:
                    stop_hit = hi >= stop_price
                if open_units > 0 and stop_hit:
                    open_units, cost_basis_points, realized_points = _close_units(
                        open_units,
                        stop_price,
                        open_units,
                        cost_basis_points,
                        realized_points,
                        trade_cost,
                        direction=direction,
                    )
                    exit_executions_count += 1
                    exit_reason = "stop"
                    exit_time = idx[pos]
                    return True
                return False

            def process_targets():
                nonlocal open_units, cost_basis_points, realized_points, exit_reason, exit_time
                nonlocal target_index, defensive_first_exit_done, exit_executions_count
                if open_units <= 0:
                    return True

                if model_name == "defensive_return_to_entry1" and max_filled_count >= 3:
                    if direction == "long":
                        defensive_hit = hi >= entry_1
                    else:
                        defensive_hit = lo <= entry_1
                    if not defensive_first_exit_done and defensive_hit:
                        units = open_units * 0.70
                        open_units, cost_basis_points, realized_points = _close_units(
                            units,
                            entry_1,
                            open_units,
                            cost_basis_points,
                            realized_points,
                            trade_cost,
                            direction=direction,
                        )
                        exit_executions_count += 1
                        defensive_first_exit_done = True
                        exit_reason = "defensive_entry1_70pct"
                        exit_time = idx[pos]
                    if open_units > 0:
                        if direction == "long":
                            remaining_target = avg_entry_now() + 1.0 * float(v)
                            remaining_hit = hi >= remaining_target
                        else:
                            remaining_target = avg_entry_now() - 1.0 * float(v)
                            remaining_hit = lo <= remaining_target
                        if remaining_hit:
                            open_units, cost_basis_points, realized_points = _close_units(
                                open_units,
                                remaining_target,
                                open_units,
                                cost_basis_points,
                                realized_points,
                                trade_cost,
                                direction=direction,
                            )
                            exit_executions_count += 1
                            exit_reason = "defensive_remaining_1v"
                            exit_time = idx[pos]
                    return open_units <= 0

                if model_name == "defensive_entry1_full_exit" and max_filled_count >= 3:
                    if direction == "long":
                        defensive_hit = hi >= entry_1
                    else:
                        defensive_hit = lo <= entry_1
                    if defensive_hit:
                        open_units, cost_basis_points, realized_points = _close_units(
                            open_units,
                            entry_1,
                            open_units,
                            cost_basis_points,
                            realized_points,
                            trade_cost,
                            direction=direction,
                        )
                        exit_executions_count += 1
                        exit_reason = "defensive_entry1_full_exit"
                        exit_time = idx[pos]
                    return open_units <= 0

                def target_hit(price):
                    return hi >= price if direction == "long" else lo <= price

                while open_units > 0 and target_index < len(targets) and target_hit(targets[target_index]["price"]):
                    target = targets[target_index]
                    units = open_units * float(target["fraction"])
                    open_units, cost_basis_points, realized_points = _close_units(
                        units,
                        float(target["price"]),
                        open_units,
                        cost_basis_points,
                        realized_points,
                        trade_cost,
                        direction=direction,
                    )
                    exit_executions_count += 1
                    exit_reason = target["label"]
                    exit_time = idx[pos]
                    target_index += 1
                return open_units <= 0

            def process_grid_fills():
                nonlocal open_units, cost_basis_points, max_filled_count, targets, target_index, entry_executions_count
                filled_new = False
                for level_idx, level in enumerate(grid_levels):
                    if level_idx == 0:
                        continue
                    if direction == "long":
                        fill_hit = lo <= level
                    else:
                        fill_hit = hi >= level
                    if not filled_flags[level_idx] and fill_hit:
                        filled_flags[level_idx] = True
                        max_filled_count = max(max_filled_count, level_idx + 1)
                        open_units += 1.0
                        entry_executions_count += 1
                        cost_basis_points += float(level) + trade_cost if direction == "long" else float(level) - trade_cost
                        filled_new = True
                if filled_new:
                    target_index = 0
                    targets = reset_targets()

            if conservative_same_bar:
                process_grid_fills()
                if process_stop():
                    break
                if process_targets():
                    break
            else:
                if process_targets():
                    break
                process_grid_fills()
                if process_stop():
                    break

        if open_units > 0:
            final_price = float(closes[end_pos])
            open_units, cost_basis_points, realized_points = _close_units(
                open_units,
                final_price,
                open_units,
                cost_basis_points,
                realized_points,
                trade_cost,
                direction=direction,
            )
            exit_executions_count += 1
            if exit_reason == "time_exit":
                exit_time = idx[end_pos]

        realized_v = realized_points / float(v)
        row = grid.to_dict()
        row.update({
            "direction": direction,
            "exit_model": model_name,
            "conservative_same_bar": bool(conservative_same_bar),
            "fee_points": float(fee_points),
            "slippage_points": float(slippage_points),
            "stop_price": stop_price,
            "exit_time": exit_time,
            "exit_reason": exit_reason,
            "max_filled_entries": int(max_filled_count),
            "entry_executions_count": int(entry_executions_count),
            "exit_executions_count": int(exit_executions_count),
            "total_executions_count": int(entry_executions_count + exit_executions_count),
            "realized_pnl_points": realized_points,
            "realized_pnl_v": realized_v,
            "win": realized_points > 0,
            "loss": realized_points < 0,
            "max_adverse_excursion_v": grid.get("max_adverse_excursion_v", pd.NA),
            "max_favorable_excursion_v": grid.get("max_favorable_excursion_v", pd.NA),
        })
        rows.append(row)

    trades = pd.DataFrame(rows)
    print("Backtest exit model=%s trades=%s" % (model_name, len(trades)))
    print(trades[[
        "entry_time",
        "exit_time",
        "session",
        "max_filled_entries",
        "realized_pnl_v",
        "realized_pnl_points",
        "win",
        "exit_reason",
    ]].head(10).to_string(index=False) if len(trades) else "(none)")
    return trades


def summarize_backtest_results(trades: pd.DataFrame) -> pd.DataFrame:
    """Return a compact one-row performance summary for a trade set."""
    columns = [
        "total_trades",
        "win_rate",
        "avg_win_v",
        "avg_loss_v",
        "expectancy_v",
        "profit_factor",
        "max_drawdown_v",
        "cumulative_pnl_v",
        "average_mfe_v",
        "average_mae_v",
        "mfe_capture_ratio",
        "returned_to_entry1_after_3_rate",
        "reached_4th_entry_rate",
    ]
    if trades.empty:
        return pd.DataFrame([{c: 0 if c == "total_trades" else pd.NA for c in columns}])

    pnl = pd.to_numeric(trades["realized_pnl_v"], errors="coerce").fillna(0.0)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    cumulative = pnl.cumsum()
    drawdown = cumulative.cummax() - cumulative
    gross_profit = wins.sum()
    gross_loss = abs(losses.sum())
    mfe = pd.to_numeric(trades.get("max_favorable_excursion_v", pd.Series(dtype=float)), errors="coerce")
    mae = pd.to_numeric(trades.get("max_adverse_excursion_v", pd.Series(dtype=float)), errors="coerce")
    capture = pnl / mfe.replace(0, pd.NA)
    returned_to_entry1 = trades.get("returned_to_entry_1_after_3_fills", pd.Series(dtype=bool))
    reached_4th = trades.get("reached_4th_entry", pd.Series(dtype=bool))
    if "max_filled_entries" in trades.columns:
        three_fill_mask = pd.to_numeric(trades["max_filled_entries"], errors="coerce") >= 3
    elif "filled_entries_count" in trades.columns:
        three_fill_mask = pd.to_numeric(trades["filled_entries_count"], errors="coerce") >= 3
    else:
        three_fill_mask = pd.Series(False, index=trades.index)
    if len(returned_to_entry1) and three_fill_mask.any():
        returned_rate = float(returned_to_entry1.loc[three_fill_mask].astype(bool).mean())
    else:
        returned_rate = pd.NA

    summary = pd.DataFrame([{
        "total_trades": int(len(trades)),
        "win_rate": float((pnl > 0).mean()),
        "avg_win_v": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_v": float(losses.mean()) if len(losses) else 0.0,
        "expectancy_v": float(pnl.mean()),
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else math.inf,
        "max_drawdown_v": float(drawdown.max()) if len(drawdown) else 0.0,
        "cumulative_pnl_v": float(pnl.sum()),
        "average_mfe_v": float(mfe.mean()) if len(mfe.dropna()) else pd.NA,
        "average_mae_v": float(mae.mean()) if len(mae.dropna()) else pd.NA,
        "mfe_capture_ratio": float(capture.mean()) if len(capture.dropna()) else pd.NA,
        "returned_to_entry1_after_3_rate": returned_rate,
        "reached_4th_entry_rate": float(reached_4th.astype(bool).mean()) if len(reached_4th) else pd.NA,
    }])
    return summary[columns]


def _add_report_bins(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    if "entry_time" in out.columns:
        out["year"] = pd.DatetimeIndex(out["entry_time"]).tz_convert(KST).year
    if "bars_to_pullback" in out.columns:
        out["bars_to_pullback_bin"] = pd.cut(
            out["bars_to_pullback"],
            bins=[0, 3, 6, 10, math.inf],
            labels=["1~3", "4~6", "7~10", "11+"],
            right=True,
        )
    if "max_filled_entries" in out.columns:
        out["max_fill_bin"] = out["max_filled_entries"].map({
            1: "1 fill",
            2: "2 fills",
            3: "3 fills",
        }).fillna("4+ touched")
        if "reached_4th_entry" in out.columns:
            out.loc[out["reached_4th_entry"].astype(bool), "max_fill_bin"] = "4+ touched"
    return out


def _summarize_by(trades: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if group_col not in trades.columns:
        return pd.DataFrame()
    parts = []
    for key, group in trades.groupby(group_col, dropna=False):
        summary = summarize_backtest_results(group)
        summary.insert(0, group_col, key)
        parts.append(summary)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _summarize_direction_combined(trades: pd.DataFrame) -> pd.DataFrame:
    parts = []
    if "direction" in trades.columns:
        for direction, group in trades.groupby("direction", dropna=False):
            summary = summarize_backtest_results(group)
            summary.insert(0, "direction", direction)
            parts.append(summary)
    combined = summarize_backtest_results(trades)
    combined.insert(0, "direction", "combined")
    parts.append(combined)
    return pd.concat(parts, ignore_index=True)


def _save_report_tables(report: dict[str, pd.DataFrame], output_dir, prefix):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    saved = {}
    for name, table in report.items():
        if isinstance(table, pd.DataFrame):
            file_path = output_path / ("%s_%s.csv" % (prefix, name))
            table.to_csv(file_path, index=False, encoding="utf-8-sig")
            saved[name] = str(file_path)
    print("Saved report CSV files:")
    for name, file_path in saved.items():
        print("%s: %s" % (name, file_path))
    return saved


def generate_performance_report(trades: pd.DataFrame, output_dir=None, prefix="gold_backtest_report") -> dict[str, pd.DataFrame]:
    """Generate overall and breakdown performance report tables.

    If output_dir is provided, every report table is saved as CSV.
    """
    if trades.empty:
        report = {"overall": summarize_backtest_results(trades)}
        if output_dir is not None:
            _save_report_tables(report, output_dir, prefix)
        return report

    work = _add_report_bins(trades)
    report = {
        "overall": summarize_backtest_results(work),
        "by_direction": _summarize_direction_combined(work),
        "by_year": _summarize_by(work, "year"),
        "by_session": _summarize_by(work, "session"),
        "by_timeframe": _summarize_by(work, "timeframe"),
        "by_midline": _summarize_by(work, "midline_broken_before_entry"),
        "by_bars_to_pullback": _summarize_by(work, "bars_to_pullback_bin"),
        "by_max_fill": _summarize_by(work, "max_fill_bin"),
        "by_v_method": _summarize_by(work, "v_method"),
        "by_exit_model": _summarize_by(work, "exit_model"),
    }
    if output_dir is not None:
        report["saved_files"] = pd.DataFrame(
            [{"table": k, "path": v} for k, v in _save_report_tables(report, output_dir, prefix).items()]
        )
    return report


def print_report(report: dict[str, pd.DataFrame]) -> None:
    """Print generated performance report tables."""
    for name, table in report.items():
        if not isinstance(table, pd.DataFrame):
            continue
        print("")
        print("== %s ==" % name)
        if table.empty:
            print("(empty)")
        else:
            printable = table.copy()
            for col in printable.columns:
                if pd.api.types.is_float_dtype(printable[col]):
                    printable[col] = printable[col].round(4)
            print(printable.to_string(index=False))


if __name__ == "__main__":
    # Adjust path/timeframe as needed.
    filepath = Path(__file__).resolve().parents[2] / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"
    data = load_gold_data(filepath, timeframe="5m")
    validate_ohlcv(data)

    data = assign_session(
        data,
        us_open_start="09:30",
        us_open_end="11:00",
        europe_start="08:00",
        europe_end="10:30",
    )
    summarize_sessions(data)
    first = get_first_session_candles(data)
    print(first[["datetime_kst", "session", "open", "high", "low", "close"]].head(20).to_string())

    debug_session_times(data, ["2024-03-08", "2024-03-11", "2024-10-25", "2024-10-28", "2024-11-04"])

    data = add_bollinger_bands(data, ddof=0)
    debug_bollinger_values(data, "2024-01-02 08:30", "2024-01-02 10:00")

    data = detect_buy_breakout_double_bb(data)
    breakout_events = get_breakout_events(data)
    summarize_breakout_events(breakout_events)

    pullback_candidates = create_pullback_entry_candidates(data)
    summarize_pullback_candidates(pullback_candidates)

    pullback_candidates = add_v_metrics_to_candidates(data, pullback_candidates)
    summarize_v_metrics(pullback_candidates)

    grid_results = simulate_grid_path(
        data,
        pullback_candidates[pullback_candidates["candidate_window"] == "within_6_bars"],
        v_method="session_opening_range",
        max_entries=3,
        max_holding_bars=48,
    )
    summarize_grid_behavior(grid_results)

    sample_trades = backtest_exit_model(
        data,
        grid_results.head(200),
        model_name="split_v_targets",
        conservative_same_bar=True,
        fee_points=0.0,
        slippage_points=0.0,
        max_entries=3,
        max_holding_bars=48,
    )
    sample_report = generate_performance_report(sample_trades)
    print_report(sample_report)
