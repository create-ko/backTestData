# -*- coding: utf-8 -*-
"""2-minute XAUUSD 1:2 RR micro breakout-retest sweep.

Goal:
- Find a 2m strategy candidate with fixed 1:2 risk/reward.
- Target a high trade frequency, roughly 10-20 trades per trading day.
- Avoid same-bar optimism: if stop and target are touched in one candle, stop wins.

Candidate idea:
- Build a rolling micro range from prior 2m candles.
- Trade a breakout, then a quick retest of the broken level.
- Enter next candle open after retest confirmation.
- Stop behind the retest candle, target exactly 2R.
"""
from __future__ import annotations

import contextlib
import io
import math
import os
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gold_data_prep as prep  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "xauusd_2m_2010-01-01_2026-06-16.csv"
OUTPUT_DIR = ROOT / "result" / "rr2_2m_micro_retest_sweep"

ROUND_TURN_COST_POINTS = 0.50
ENTRY_START_MIN = 8 * 60 + 30
ENTRY_END_MIN = 24 * 60

LOOKBACKS = [6, 12, 18, 24]
RETEST_WINDOWS = [2, 3, 5]
MAX_RISKS = [4.0, 6.0, 8.0]
TREND_MODES = ["none", "sma120", "bb20_slope"]
BREAK_BUFFERS = [0.0, 0.05]
ENTRY_MODES = ["retest"]
MIN_RISK = 1.2
STOP_BUFFER = 0.2
MAX_HOLD_BARS = 60


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def parse_date_env(name: str, default: str) -> pd.Timestamp:
    return pd.Timestamp(os.environ.get(name, default), tz="Asia/Seoul")


def env_int_list(name: str, default: list[int]) -> list[int]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def env_float_list(name: str, default: list[float]) -> list[float]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def env_str_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [x.strip() for x in raw.split(",") if x.strip()]


def load_data() -> pd.DataFrame:
    df = quiet_call(prep.load_gold_data, DATA_PATH, timeframe="2m")
    start = parse_date_env("START_DATE", "2010-01-01")
    end = parse_date_env("END_DATE", "2026-06-17")
    df = df[(df.index >= start) & (df.index < end)].copy()
    df = prep.assign_session(df)
    df = prep.add_bollinger_bands(df, ddof=0)
    return add_indicators(df)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["sma20"] = out["close"].rolling(20, min_periods=20).mean()
    out["sma120"] = out["close"].rolling(120, min_periods=120).mean()
    out["sma120_slope"] = out["sma120"] - out["sma120"].shift(30)
    out["bb20_mid_slope"] = out["bb20_2_mid_close"] - out["bb20_2_mid_close"].shift(20)

    prev_close = out["close"].shift(1)
    tr = pd.concat([
        out["high"] - out["low"],
        (out["high"] - prev_close).abs(),
        (out["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14, min_periods=14).mean()
    return out


def entry_time_allowed(ts: pd.Timestamp) -> bool:
    kst = ts.tz_convert("Asia/Seoul")
    minute = kst.hour * 60 + kst.minute
    return ENTRY_START_MIN <= minute < ENTRY_END_MIN


def trend_ok(row: pd.Series, direction: str, trend_mode: str) -> bool:
    if trend_mode == "none":
        return True
    if trend_mode == "sma120":
        if direction == "long":
            return bool(row["sma20"] > row["sma120"] and row["sma120_slope"] > 0)
        return bool(row["sma20"] < row["sma120"] and row["sma120_slope"] < 0)
    if trend_mode == "bb20_slope":
        if direction == "long":
            return bool(row["close"] > row["bb20_2_mid_close"] and row["bb20_mid_slope"] > 0)
        return bool(row["close"] < row["bb20_2_mid_close"] and row["bb20_mid_slope"] < 0)
    raise ValueError("unknown trend_mode: %s" % trend_mode)


def make_trade(df: pd.DataFrame, entry_pos: int, retest_pos: int, direction: str, level: float, max_risk: float) -> dict | None:
    if entry_pos >= len(df):
        return None
    idx = df.index
    if not entry_time_allowed(idx[entry_pos]):
        return None

    entry = float(df["open"].iloc[entry_pos])
    if direction == "long":
        stop = min(float(df["low"].iloc[retest_pos]) - STOP_BUFFER, level - STOP_BUFFER)
        risk = entry - stop
        target = entry + 2.0 * risk
    else:
        stop = max(float(df["high"].iloc[retest_pos]) + STOP_BUFFER, level + STOP_BUFFER)
        risk = stop - entry
        target = entry - 2.0 * risk

    if not math.isfinite(risk) or risk < MIN_RISK or risk > max_risk:
        return None

    end_pos = min(len(df) - 1, entry_pos + MAX_HOLD_BARS)
    exit_price = float(df["close"].iloc[end_pos])
    exit_time = idx[end_pos]
    exit_reason = "time_exit"
    mfe = 0.0
    mae = 0.0

    for pos in range(entry_pos, end_pos + 1):
        hi = float(df["high"].iloc[pos])
        lo = float(df["low"].iloc[pos])
        if direction == "long":
            mfe = max(mfe, hi - entry)
            mae = max(mae, entry - lo)
            if lo <= stop:
                exit_price = stop
                exit_time = idx[pos]
                exit_reason = "stop"
                break
            if hi >= target:
                exit_price = target
                exit_time = idx[pos]
                exit_reason = "target_2r"
                break
        else:
            mfe = max(mfe, entry - lo)
            mae = max(mae, hi - entry)
            if hi >= stop:
                exit_price = stop
                exit_time = idx[pos]
                exit_reason = "stop"
                break
            if lo <= target:
                exit_price = target
                exit_time = idx[pos]
                exit_reason = "target_2r"
                break

    gross = exit_price - entry if direction == "long" else entry - exit_price
    net = gross - ROUND_TURN_COST_POINTS
    return {
        "entry_time": idx[entry_pos],
        "exit_time": exit_time,
        "direction": direction,
        "level": level,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "risk_points": risk,
        "gross_points": gross,
        "net_points": net,
        "r_net": net / risk,
        "exit_reason": exit_reason,
        "mfe_points": mfe,
        "mae_points": mae,
        "hold_bars": int(idx.searchsorted(exit_time) - entry_pos + 1),
        "year": int(idx[entry_pos].year),
        "month": idx[entry_pos].strftime("%Y-%m"),
        "day": idx[entry_pos].date().isoformat(),
        "session": str(df["session"].iloc[entry_pos]),
    }


def make_trade_arrays(data: dict, entry_pos: int, retest_pos: int, direction: str, level: float, max_risk: float) -> dict | None:
    idx = data["idx"]
    if entry_pos >= len(idx):
        return None
    if not data["entry_allowed"][entry_pos]:
        return None

    entry = float(data["open"][entry_pos])
    if direction == "long":
        stop = min(float(data["low"][retest_pos]) - STOP_BUFFER, level - STOP_BUFFER)
        risk = entry - stop
        target = entry + 2.0 * risk
    else:
        stop = max(float(data["high"][retest_pos]) + STOP_BUFFER, level + STOP_BUFFER)
        risk = stop - entry
        target = entry - 2.0 * risk

    if not math.isfinite(risk) or risk < MIN_RISK or risk > max_risk:
        return None

    end_pos = min(len(idx) - 1, entry_pos + MAX_HOLD_BARS)
    exit_price = float(data["close"][end_pos])
    exit_pos = end_pos
    exit_reason = "time_exit"
    mfe = 0.0
    mae = 0.0

    high = data["high"]
    low = data["low"]
    close = data["close"]
    for pos in range(entry_pos, end_pos + 1):
        hi = float(high[pos])
        lo = float(low[pos])
        if direction == "long":
            mfe = max(mfe, hi - entry)
            mae = max(mae, entry - lo)
            if lo <= stop:
                exit_price = stop
                exit_pos = pos
                exit_reason = "stop"
                break
            if hi >= target:
                exit_price = target
                exit_pos = pos
                exit_reason = "target_2r"
                break
        else:
            mfe = max(mfe, entry - lo)
            mae = max(mae, hi - entry)
            if hi >= stop:
                exit_price = stop
                exit_pos = pos
                exit_reason = "stop"
                break
            if lo <= target:
                exit_price = target
                exit_pos = pos
                exit_reason = "target_2r"
                break

    gross = exit_price - entry if direction == "long" else entry - exit_price
    net = gross - ROUND_TURN_COST_POINTS
    ts = idx[entry_pos]
    return {
        "entry_time": ts,
        "exit_time": idx[exit_pos],
        "direction": direction,
        "level": level,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "risk_points": risk,
        "gross_points": gross,
        "net_points": net,
        "r_net": net / risk,
        "exit_reason": exit_reason,
        "mfe_points": mfe,
        "mae_points": mae,
        "hold_bars": int(exit_pos - entry_pos + 1),
        "year": int(ts.year),
        "month": ts.strftime("%Y-%m"),
        "day": ts.date().isoformat(),
        "session": str(data["session"][entry_pos]),
    }


def build_array_cache(df: pd.DataFrame) -> dict:
    minutes = df.index.hour * 60 + df.index.minute
    entry_allowed = (minutes >= ENTRY_START_MIN) & (minutes < ENTRY_END_MIN)
    return {
        "idx": df.index,
        "open": df["open"].to_numpy(float),
        "high": df["high"].to_numpy(float),
        "low": df["low"].to_numpy(float),
        "close": df["close"].to_numpy(float),
        "session": df["session"].astype(str).to_numpy(),
        "entry_allowed": entry_allowed.to_numpy() if hasattr(entry_allowed, "to_numpy") else entry_allowed,
        "sma20": df["sma20"].to_numpy(float),
        "sma120": df["sma120"].to_numpy(float),
        "sma120_slope": df["sma120_slope"].to_numpy(float),
        "bb20_mid": df["bb20_2_mid_close"].to_numpy(float),
        "bb20_mid_slope": df["bb20_mid_slope"].to_numpy(float),
        "atr14": df["atr14"].to_numpy(float),
    }


def trend_ok_arrays(data: dict, pos: int, direction: str, trend_mode: str) -> bool:
    if trend_mode == "none":
        return True
    if trend_mode == "sma120":
        if direction == "long":
            return bool(data["sma20"][pos] > data["sma120"][pos] and data["sma120_slope"][pos] > 0)
        return bool(data["sma20"][pos] < data["sma120"][pos] and data["sma120_slope"][pos] < 0)
    if trend_mode == "bb20_slope":
        if direction == "long":
            return bool(data["close"][pos] > data["bb20_mid"][pos] and data["bb20_mid_slope"][pos] > 0)
        return bool(data["close"][pos] < data["bb20_mid"][pos] and data["bb20_mid_slope"][pos] < 0)
    raise ValueError("unknown trend_mode: %s" % trend_mode)


def make_direct_trade_arrays(data: dict, entry_pos: int, breakout_pos: int, direction: str, level: float, max_risk: float) -> dict | None:
    idx = data["idx"]
    if entry_pos >= len(idx):
        return None
    if not data["entry_allowed"][entry_pos]:
        return None

    entry = float(data["open"][entry_pos])
    if direction == "long":
        stop = min(float(data["low"][breakout_pos]) - STOP_BUFFER, level - STOP_BUFFER)
        risk = entry - stop
        target = entry + 2.0 * risk
    else:
        stop = max(float(data["high"][breakout_pos]) + STOP_BUFFER, level + STOP_BUFFER)
        risk = stop - entry
        target = entry - 2.0 * risk

    if not math.isfinite(risk) or risk < MIN_RISK or risk > max_risk:
        return None

    end_pos = min(len(idx) - 1, entry_pos + MAX_HOLD_BARS)
    exit_price = float(data["close"][end_pos])
    exit_pos = end_pos
    exit_reason = "time_exit"
    mfe = 0.0
    mae = 0.0

    high = data["high"]
    low = data["low"]
    close = data["close"]
    for pos in range(entry_pos, end_pos + 1):
        hi = float(high[pos])
        lo = float(low[pos])
        if direction == "long":
            mfe = max(mfe, hi - entry)
            mae = max(mae, entry - lo)
            if lo <= stop:
                exit_price = stop
                exit_pos = pos
                exit_reason = "stop"
                break
            if hi >= target:
                exit_price = target
                exit_pos = pos
                exit_reason = "target_2r"
                break
        else:
            mfe = max(mfe, entry - lo)
            mae = max(mae, hi - entry)
            if hi >= stop:
                exit_price = stop
                exit_pos = pos
                exit_reason = "stop"
                break
            if lo <= target:
                exit_price = target
                exit_pos = pos
                exit_reason = "target_2r"
                break

    gross = exit_price - entry if direction == "long" else entry - exit_price
    net = gross - ROUND_TURN_COST_POINTS
    ts = idx[entry_pos]
    return {
        "entry_time": ts,
        "exit_time": idx[exit_pos],
        "direction": direction,
        "level": level,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "risk_points": risk,
        "gross_points": gross,
        "net_points": net,
        "r_net": net / risk,
        "exit_reason": exit_reason,
        "mfe_points": mfe,
        "mae_points": mae,
        "hold_bars": int(exit_pos - entry_pos + 1),
        "year": int(ts.year),
        "month": ts.strftime("%Y-%m"),
        "day": ts.date().isoformat(),
        "session": str(data["session"][entry_pos]),
    }


def make_fade_trade_arrays(data: dict, entry_pos: int, breakout_pos: int, breakout_direction: str, level: float, max_risk: float) -> dict | None:
    idx = data["idx"]
    if entry_pos >= len(idx):
        return None
    if not data["entry_allowed"][entry_pos]:
        return None

    direction = "short" if breakout_direction == "long" else "long"
    entry = float(data["open"][entry_pos])
    if direction == "short":
        stop = max(float(data["high"][breakout_pos]) + STOP_BUFFER, level + STOP_BUFFER)
        risk = stop - entry
        target = entry - 2.0 * risk
    else:
        stop = min(float(data["low"][breakout_pos]) - STOP_BUFFER, level - STOP_BUFFER)
        risk = entry - stop
        target = entry + 2.0 * risk

    if not math.isfinite(risk) or risk < MIN_RISK or risk > max_risk:
        return None

    end_pos = min(len(idx) - 1, entry_pos + MAX_HOLD_BARS)
    exit_price = float(data["close"][end_pos])
    exit_pos = end_pos
    exit_reason = "time_exit"
    mfe = 0.0
    mae = 0.0

    high = data["high"]
    low = data["low"]
    for pos in range(entry_pos, end_pos + 1):
        hi = float(high[pos])
        lo = float(low[pos])
        if direction == "long":
            mfe = max(mfe, hi - entry)
            mae = max(mae, entry - lo)
            if lo <= stop:
                exit_price = stop
                exit_pos = pos
                exit_reason = "stop"
                break
            if hi >= target:
                exit_price = target
                exit_pos = pos
                exit_reason = "target_2r"
                break
        else:
            mfe = max(mfe, entry - lo)
            mae = max(mae, hi - entry)
            if hi >= stop:
                exit_price = stop
                exit_pos = pos
                exit_reason = "stop"
                break
            if lo <= target:
                exit_price = target
                exit_pos = pos
                exit_reason = "target_2r"
                break

    gross = exit_price - entry if direction == "long" else entry - exit_price
    net = gross - ROUND_TURN_COST_POINTS
    ts = idx[entry_pos]
    return {
        "entry_time": ts,
        "exit_time": idx[exit_pos],
        "direction": direction,
        "level": level,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "risk_points": risk,
        "gross_points": gross,
        "net_points": net,
        "r_net": net / risk,
        "exit_reason": exit_reason,
        "mfe_points": mfe,
        "mae_points": mae,
        "hold_bars": int(exit_pos - entry_pos + 1),
        "year": int(ts.year),
        "month": ts.strftime("%Y-%m"),
        "day": ts.date().isoformat(),
        "session": str(data["session"][entry_pos]),
    }


def build_entries(
    df: pd.DataFrame,
    lookback: int,
    retest_window: int,
    max_risk: float,
    trend_mode: str,
    break_buffer_atr: float,
    entry_mode: str,
) -> pd.DataFrame:
    prior_high = df["high"].shift(1).rolling(lookback, min_periods=lookback).max()
    prior_low = df["low"].shift(1).rolling(lookback, min_periods=lookback).min()
    prev_close = df["close"].shift(1)

    long_break = (df["close"] > prior_high + break_buffer_atr * df["atr14"]) & (prev_close <= prior_high)
    short_break = (df["close"] < prior_low - break_buffer_atr * df["atr14"]) & (prev_close >= prior_low)

    rows = []
    next_allowed_pos = 0
    data = build_array_cache(df)
    idx = data["idx"]
    high = data["high"]
    low = data["low"]
    close = data["close"]
    prior_high_values = prior_high.to_numpy(float)
    prior_low_values = prior_low.to_numpy(float)
    long_break_values = long_break.fillna(False).to_numpy(bool)
    short_break_values = short_break.fillna(False).to_numpy(bool)
    for pos in range(lookback + 120, len(df) - 2):
        if pos < next_allowed_pos:
            continue
        direction = None
        level = math.nan
        if bool(long_break_values[pos]) and trend_ok_arrays(data, pos, "long", trend_mode):
            direction = "long"
            level = float(prior_high_values[pos])
        elif bool(short_break_values[pos]) and trend_ok_arrays(data, pos, "short", trend_mode):
            direction = "short"
            level = float(prior_low_values[pos])
        else:
            continue

        if entry_mode == "direct":
            retest_pos = pos
            trade = make_direct_trade_arrays(data, pos + 1, pos, direction, level, max_risk)
        elif entry_mode == "fade":
            retest_pos = pos
            trade = make_fade_trade_arrays(data, pos + 1, pos, direction, level, max_risk)
        elif entry_mode == "retest":
            retest_pos = None
            end = min(len(df) - 2, pos + retest_window)
            for rp in range(pos + 1, end + 1):
                if direction == "long":
                    touched = float(low[rp]) <= level
                    confirmed = float(close[rp]) >= level
                else:
                    touched = float(high[rp]) >= level
                    confirmed = float(close[rp]) <= level
                if touched and confirmed:
                    retest_pos = rp
                    break

            if retest_pos is None:
                continue
            trade = make_trade_arrays(data, retest_pos + 1, retest_pos, direction, level, max_risk)
        else:
            raise ValueError("unknown entry_mode: %s" % entry_mode)
        if trade is None:
            continue
        trade.update({
            "lookback": lookback,
            "retest_window": retest_window,
            "max_risk": max_risk,
            "trend_mode": trend_mode,
            "break_buffer_atr": break_buffer_atr,
            "entry_mode": entry_mode,
            "breakout_time": idx[pos],
            "retest_time": idx[retest_pos],
        })
        rows.append(trade)
        next_allowed_pos = int(idx.searchsorted(trade["exit_time"])) + 1

    return pd.DataFrame(rows)


def profit_factor(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").fillna(0.0)
    gp = vals[vals > 0].sum()
    gl = abs(vals[vals < 0].sum())
    if gl == 0:
        return math.inf if gp > 0 else 0.0
    return float(gp / gl)


def max_drawdown(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").fillna(0.0)
    eq = vals.cumsum()
    dd = eq.cummax() - eq
    return float(dd.max()) if len(vals) else 0.0


def summarize_group(group: pd.DataFrame, trading_days: int, extra_cost: float = 0.0) -> dict:
    values = group["net_points"].astype(float) - extra_cost
    return {
        "trades": int(len(group)),
        "trading_days": int(trading_days),
        "trades_per_day": float(len(group) / trading_days) if trading_days else 0.0,
        "net_points": float(values.sum()),
        "avg_points": float(values.mean()) if len(values) else 0.0,
        "avg_r_net": float((values / group["risk_points"].astype(float)).mean()) if len(values) else 0.0,
        "profit_factor": profit_factor(values),
        "win_rate": float((values > 0).mean() * 100) if len(values) else 0.0,
        "max_drawdown_points": max_drawdown(values),
        "target_rate": float((group["exit_reason"] == "target_2r").mean() * 100) if len(group) else 0.0,
        "stop_rate": float((group["exit_reason"] == "stop").mean() * 100) if len(group) else 0.0,
        "avg_risk": float(group["risk_points"].mean()) if len(group) else 0.0,
        "avg_hold_bars": float(group["hold_bars"].mean()) if len(group) else 0.0,
    }


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def grouped(trades: pd.DataFrame, cols: list[str], trading_days: int, extra_cost: float = 0.0) -> pd.DataFrame:
    rows = []
    for key, group in trades.groupby(cols, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        row = dict(zip(cols, key))
        row.update(summarize_group(group, trading_days, extra_cost=extra_cost))
        rows.append(row)
    return round_floats(pd.DataFrame(rows))


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join("<th>%s</th>" % c for c in show.columns)
    rows = []
    for _, row in show.iterrows():
        cells = []
        for col, value in row.items():
            cls = ""
            if col in {"net_points", "avg_points", "avg_r_net", "profit_factor"}:
                try:
                    num = float(value)
                    cls = "pos" if (num >= 1 if col == "profit_factor" else num > 0) else "neg"
                except Exception:
                    pass
            text = "" if pd.isna(value) else ("%.4f" % value if isinstance(value, float) else str(value))
            cells.append("<td class='%s'>%s</td>" % (cls, text))
        rows.append("<tr>%s</tr>" % "".join(cells))
    return "<section><h2>%s</h2><div><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></section>" % (
        title,
        headers,
        "".join(rows),
    )


def write_html(summary, yearly, monthly, cost):
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#101820;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#c9d3df}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2),td:nth-child(3),th:nth-child(3){text-align:left}
    .pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m RR2 Micro Retest Sweep</title><style>%s</style></head>
<body><header><h1>2m RR2 Micro Breakout-Retest Sweep</h1><p>Fixed 1:2 RR, next-open entry after retest, stop-first same-bar rule, cost 0.5P round turn.</p></header><main>
%s%s%s%s
</main></body></html>""" % (
        css,
        table_html(summary.sort_values(["target_freq", "net_points"], ascending=[False, False]), "Config Ranking", 120),
        table_html(cost, "Cost Sensitivity", 160),
        table_html(yearly.sort_values(["config_id", "year"]), "Yearly Report"),
        table_html(monthly.sort_values(["config_id", "month"]), "Monthly Report"),
    )
    (OUTPUT_DIR / "rr2_2m_micro_retest_report.html").write_text(html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    trading_days = int(pd.Series(df.index.date).nunique())
    all_parts = []
    lookbacks = env_int_list("LOOKBACKS", LOOKBACKS)
    retest_windows = env_int_list("RETEST_WINDOWS", RETEST_WINDOWS)
    max_risks = env_float_list("MAX_RISKS", MAX_RISKS)
    trend_modes = env_str_list("TREND_MODES", TREND_MODES)
    break_buffers = env_float_list("BREAK_BUFFERS", BREAK_BUFFERS)
    entry_modes = env_str_list("ENTRY_MODES", ENTRY_MODES)

    for lookback in lookbacks:
        for retest_window in retest_windows:
            for max_risk in max_risks:
                for trend_mode in trend_modes:
                    for break_buffer in break_buffers:
                        for entry_mode in entry_modes:
                            print("RUN", lookback, retest_window, max_risk, trend_mode, break_buffer, entry_mode, flush=True)
                            trades = build_entries(df, lookback, retest_window, max_risk, trend_mode, break_buffer, entry_mode)
                            if trades.empty:
                                continue
                            config_id = "lb%s_rt%s_mr%s_%s_b%s_%s" % (
                                lookback,
                                retest_window,
                                str(max_risk).replace(".", "p"),
                                trend_mode,
                                str(break_buffer).replace(".", "p"),
                                entry_mode,
                            )
                            trades["config_id"] = config_id
                            all_parts.append(trades)
                            print("  trades", len(trades), flush=True)

    trades = pd.concat(all_parts, ignore_index=True) if all_parts else pd.DataFrame()
    if trades.empty:
        raise RuntimeError("No trades generated")

    summary = grouped(trades, ["config_id", "entry_mode", "lookback", "retest_window", "max_risk", "trend_mode", "break_buffer_atr"], trading_days)
    summary["target_freq"] = summary["trades_per_day"].between(10.0, 20.0)
    yearly = grouped(trades, ["config_id", "year"], trading_days)
    monthly = grouped(trades, ["config_id", "month"], trading_days)

    cost_parts = []
    for extra in [0.0, 0.2, 0.3, 0.5, 0.8, 1.0]:
        c = grouped(trades, ["config_id"], trading_days, extra_cost=extra)
        c.insert(1, "extra_cost", extra)
        cost_parts.append(c)
    cost = pd.concat(cost_parts, ignore_index=True)

    trades.to_csv(OUTPUT_DIR / "rr2_2m_micro_retest_trades.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "rr2_2m_micro_retest_summary.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "rr2_2m_micro_retest_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "rr2_2m_micro_retest_monthly.csv", index=False, encoding="utf-8-sig")
    cost.to_csv(OUTPUT_DIR / "rr2_2m_micro_retest_cost_sensitivity.csv", index=False, encoding="utf-8-sig")
    write_html(summary, yearly, monthly, cost)

    ranked = summary.sort_values(["target_freq", "net_points"], ascending=[False, False])
    print("")
    print("=== 2M RR2 MICRO RETEST SWEEP ===")
    print("Trading days:", trading_days)
    print(ranked.head(30).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
