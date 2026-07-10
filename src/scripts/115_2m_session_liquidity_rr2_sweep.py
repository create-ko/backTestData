# -*- coding: utf-8 -*-
"""2m session liquidity level fixed 1:2 RR sweep.

Concept:
- Build intraday liquidity levels that traders naturally watch:
  opening-range high/low, previous-day high/low, previous-session high/low.
- When 2m close breaks a level, wait for a retest of that level.
- Enter next 2m open in breakout direction, stop behind retest candle or the
  broken level, target exactly 2R.
- Unlike the older session script, this allows multiple level events per day
  and uses cooldown/concurrency caps to target 10-20 trades/day.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import math
import os
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_SCRIPT = SCRIPT_DIR / "100_strategy2_grid_multitimeframe_month_filter.py"

TEST_START = os.environ.get("TEST_START", "2023-01-01")
TEST_END = os.environ.get("TEST_END", "2026-06-17")
ROUND_TURN_COST_POINTS = float(os.environ.get("ROUND_TURN_COST_POINTS", "0.5"))
OUTPUT_DIR = ROOT / "result" / "session_liquidity_rr2_sweep"


spec = importlib.util.spec_from_file_location("base100_for_115", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
sys.modules["base100_for_115"] = base
assert spec.loader is not None
spec.loader.exec_module(base)


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def env_int_list(name: str, default: list[int]) -> list[int]:
    raw = os.environ.get(name)
    return [int(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def env_float_list(name: str, default: list[float]) -> list[float]:
    raw = os.environ.get(name)
    return [float(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def env_str_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else default


def env_level_sets(default: list[str]) -> list[str]:
    raw = os.environ.get("LEVEL_SETS")
    if not raw:
        return default
    if ";" in raw:
        return [x.strip() for x in raw.split(";") if x.strip()]
    return [raw.strip()]


LEVEL_SETS = env_level_sets(["or", "or,pdhpdl", "or,pdhpdl,prev_session", "or,pdhpdl,prev_session,session_dynamic"])
OR_BARS_SET = env_int_list("OR_BARS_SET", [8])
RETEST_WINDOWS = env_int_list("RETEST_WINDOWS", [3, 6])
COOLDOWN_BARS_SET = env_int_list("COOLDOWN_BARS_SET", [0, 3, 6])
STOP_MODES = env_str_list("STOP_MODES", ["retest", "level"])
STOP_BUFFERS = env_float_list("STOP_BUFFERS", [0.2, 0.5])
MIN_RISKS = env_float_list("MIN_RISKS", [0.8])
MAX_RISKS = env_float_list("MAX_RISKS", [3.0, 5.0, 8.0])
MAX_HOLD_BARS_SET = env_int_list("MAX_HOLD_BARS_SET", [10, 20])
CONCURRENCY_CAPS = env_int_list("CONCURRENCY_CAPS", [5])
SIGNAL_MODES = env_str_list("SIGNAL_MODES", ["breakout_retest", "sweep_reversal"])
BIAS_MODES = env_str_list("BIAS_MODES", ["none"])
DISPLACEMENT_MODES = env_str_list("DISPLACEMENT_MODES", ["none"])


def load_data() -> pd.DataFrame:
    full = quiet_call(base.load_tf, "2m")
    start = pd.Timestamp(TEST_START, tz="Asia/Seoul")
    end = pd.Timestamp(TEST_END, tz="Asia/Seoul")
    df = full[(full.index >= start) & (full.index < end)].copy()
    df["kst_date"] = [ts.date().isoformat() for ts in df.index]
    df["session_name"] = df["session"].astype(str)
    session_change = (df["session_name"] != df["session_name"].shift(1)) | (df["kst_date"] != df["kst_date"].shift(1))
    df["session_id"] = session_change.cumsum()
    df["sma120"] = df["close"].rolling(120, min_periods=120).mean()
    df["sma120_slope"] = df["sma120"] - df["sma120"].shift(10)
    df["bar_range"] = df["high"] - df["low"]
    df["body"] = (df["close"] - df["open"]).abs()
    df["body_ratio"] = df["body"] / df["bar_range"].replace(0, math.nan)
    df["range_median20"] = df["bar_range"].rolling(20, min_periods=20).median()
    df["range_to_median20"] = df["bar_range"] / df["range_median20"].replace(0, math.nan)
    df["close_pos"] = (df["close"] - df["low"]) / df["bar_range"].replace(0, math.nan)
    return df


def entry_time_allowed(ts: pd.Timestamp) -> bool:
    return base.entry_time_allowed(ts)


def add_level_columns(df: pd.DataFrame, or_bars: int) -> pd.DataFrame:
    out = df.copy()
    day_high = out.groupby("kst_date")["high"].max()
    day_low = out.groupby("kst_date")["low"].min()
    dates = list(day_high.index)
    prev_high = {}
    prev_low = {}
    for i, day in enumerate(dates):
        if i == 0:
            prev_high[day] = math.nan
            prev_low[day] = math.nan
        else:
            prev_high[day] = float(day_high.iloc[i - 1])
            prev_low[day] = float(day_low.iloc[i - 1])
    out["pdh"] = out["kst_date"].map(prev_high).astype(float)
    out["pdl"] = out["kst_date"].map(prev_low).astype(float)

    session_high = out.groupby("session_id")["high"].max()
    session_low = out.groupby("session_id")["low"].min()
    prev_session_high = {}
    prev_session_low = {}
    session_ids = list(session_high.index)
    for i, sid in enumerate(session_ids):
        if i == 0:
            prev_session_high[sid] = math.nan
            prev_session_low[sid] = math.nan
        else:
            prev_session_high[sid] = float(session_high.iloc[i - 1])
            prev_session_low[sid] = float(session_low.iloc[i - 1])
    out["prev_session_high"] = out["session_id"].map(prev_session_high).astype(float)
    out["prev_session_low"] = out["session_id"].map(prev_session_low).astype(float)

    out["bar_in_session"] = out.groupby("session_id").cumcount()
    opening = out[out["bar_in_session"] < or_bars].groupby("session_id").agg(or_high=("high", "max"), or_low=("low", "min"))
    out = out.join(opening, on="session_id")
    out.loc[out["bar_in_session"] < or_bars, ["or_high", "or_low"]] = math.nan
    out["session_prior_high"] = out.groupby("session_id")["high"].cummax().shift(1)
    out["session_prior_low"] = out.groupby("session_id")["low"].cummin().shift(1)
    first_bar = out["bar_in_session"] == 0
    out.loc[first_bar, ["session_prior_high", "session_prior_low"]] = math.nan
    return out


def level_specs(level_set: str) -> list[tuple[str, str, str]]:
    tokens = {x.strip() for x in level_set.split(",") if x.strip()}
    specs: list[tuple[str, str, str]] = []
    if "or" in tokens:
        specs.extend([("or_high", "long", "or_high"), ("or_low", "short", "or_low")])
    if "pdhpdl" in tokens:
        specs.extend([("pdh", "long", "pdh"), ("pdl", "short", "pdl")])
    if "prev_session" in tokens:
        specs.extend([
            ("prev_session_high", "long", "prev_session_high"),
            ("prev_session_low", "short", "prev_session_low"),
        ])
    if "session_dynamic" in tokens:
        specs.extend([
            ("session_prior_high", "long", "session_prior_high"),
            ("session_prior_low", "short", "session_prior_low"),
        ])
    return specs


def bias_allowed(df: pd.DataFrame, pos: int, direction: str, bias_mode: str) -> bool:
    if bias_mode == "none":
        return True
    close = float(df["close"].iloc[pos])
    sma = float(df["sma120"].iloc[pos])
    slope = float(df["sma120_slope"].iloc[pos])
    if not math.isfinite(sma) or not math.isfinite(slope):
        return False
    trend_up = close > sma and slope > 0
    trend_down = close < sma and slope < 0
    price_up = close > sma
    price_down = close < sma
    if bias_mode == "trend_follow":
        return trend_up if direction == "long" else trend_down
    if bias_mode == "trend_fade":
        return trend_down if direction == "long" else trend_up
    if bias_mode == "price_follow":
        return price_up if direction == "long" else price_down
    if bias_mode == "price_fade":
        return price_down if direction == "long" else price_up
    raise ValueError("unknown bias mode: %s" % bias_mode)


def displacement_allowed(df: pd.DataFrame, pos: int, direction: str, mode: str) -> bool:
    if mode == "none":
        return True
    body_ratio = float(df["body_ratio"].iloc[pos])
    range_to_median = float(df["range_to_median20"].iloc[pos])
    close_pos = float(df["close_pos"].iloc[pos])
    if not all(math.isfinite(x) for x in [body_ratio, range_to_median, close_pos]):
        return False
    if mode == "body35":
        return body_ratio >= 0.35
    if mode == "body50":
        return body_ratio >= 0.50
    if mode == "range120":
        return range_to_median >= 1.20
    if mode == "body35_range120":
        return body_ratio >= 0.35 and range_to_median >= 1.20
    if mode == "close_extreme":
        return close_pos >= 0.65 if direction == "long" else close_pos <= 0.35
    if mode == "body35_close_extreme":
        return body_ratio >= 0.35 and (close_pos >= 0.65 if direction == "long" else close_pos <= 0.35)
    raise ValueError("unknown displacement mode: %s" % mode)


def find_entries(
    df: pd.DataFrame,
    level_set: str,
    retest_window: int,
    cooldown_bars: int,
    signal_mode: str,
    bias_mode: str,
    displacement_mode: str,
) -> pd.DataFrame:
    if signal_mode == "combined":
        parts = [
            find_entries(df, level_set, retest_window, cooldown_bars, "sweep_reversal", bias_mode, displacement_mode),
            find_entries(df, level_set, retest_window, cooldown_bars, "breakout_retest", bias_mode, displacement_mode),
        ]
        parts = [part for part in parts if not part.empty]
        return pd.concat(parts, ignore_index=True).sort_values("entry_time").reset_index(drop=True) if parts else pd.DataFrame()

    idx = df.index
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    prev_close = df["close"].shift(1).to_numpy(float)
    session_id = df["session_id"].to_numpy(int)
    session_name = df["session_name"].astype(str).to_numpy()
    kst_date = df["kst_date"].astype(str).to_numpy()
    levels = {name: df[name].to_numpy(float) for name, _, _ in level_specs(level_set)}
    rows = []
    last_signal_pos: dict[tuple[str, str], int] = {}

    for level_col, direction, level_name in level_specs(level_set):
        values = levels[level_col]
        for breakout_pos in range(1, len(df) - retest_window - 2):
            level = float(values[breakout_pos])
            if not math.isfinite(level):
                continue
            key = (level_name, direction)
            if cooldown_bars and breakout_pos - last_signal_pos.get(key, -10**9) < cooldown_bars:
                continue

            trade_direction = direction
            if signal_mode == "breakout_retest":
                if direction == "long":
                    triggered = close[breakout_pos] > level and prev_close[breakout_pos] <= level
                else:
                    triggered = close[breakout_pos] < level and prev_close[breakout_pos] >= level
                if not triggered:
                    continue
                retest_pos = None
                search_end = min(len(df) - 2, breakout_pos + retest_window)
                for pos in range(breakout_pos + 1, search_end + 1):
                    if session_id[pos] != session_id[breakout_pos]:
                        break
                    if direction == "long":
                        touched = low[pos] <= level
                        confirmed = close[pos] >= level
                    else:
                        touched = high[pos] >= level
                        confirmed = close[pos] <= level
                    if touched and confirmed:
                        retest_pos = pos
                        break
            elif signal_mode == "sweep_reversal":
                if direction == "long":
                    triggered = high[breakout_pos] >= level and close[breakout_pos] < level
                    trade_direction = "short"
                else:
                    triggered = low[breakout_pos] <= level and close[breakout_pos] > level
                    trade_direction = "long"
                if not triggered:
                    continue
                retest_pos = breakout_pos
            else:
                raise ValueError("unknown signal mode: %s" % signal_mode)

            if retest_pos is None:
                continue
            entry_pos = retest_pos + 1
            if entry_pos >= len(df) or session_id[entry_pos] != session_id[breakout_pos]:
                continue
            if not bias_allowed(df, entry_pos, trade_direction, bias_mode):
                continue
            if not displacement_allowed(df, retest_pos, trade_direction, displacement_mode):
                continue
            if not entry_time_allowed(idx[entry_pos]):
                continue
            last_signal_pos[key] = breakout_pos
            ts = idx[entry_pos]
            rows.append({
                "level_set": level_set,
                "signal_mode": signal_mode,
                "bias_mode": bias_mode,
                "displacement_mode": displacement_mode,
                "level_name": level_name,
                "direction": trade_direction,
                "breakout_pos": breakout_pos,
                "retest_pos": retest_pos,
                "entry_pos": entry_pos,
                "breakout_time": idx[breakout_pos],
                "retest_time": idx[retest_pos],
                "entry_time": ts,
                "level": level,
                "entry_price": float(open_[entry_pos]),
                "breakout_high": float(high[breakout_pos]),
                "breakout_low": float(low[breakout_pos]),
                "retest_high": float(high[retest_pos]),
                "retest_low": float(low[retest_pos]),
                "session": str(session_name[entry_pos]),
                "session_id": int(session_id[entry_pos]),
                "year": int(ts.year),
                "month": ts.strftime("%Y-%m"),
                "day": str(kst_date[entry_pos]),
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def apply_concurrency_cap(trades: pd.DataFrame, cap: int) -> pd.DataFrame:
    open_exits = []
    kept_indices = []
    ordered = trades.sort_values("entry_time")
    entry_loc = ordered.columns.get_loc("entry_time")
    exit_loc = ordered.columns.get_loc("exit_time")
    for row in ordered.itertuples(index=True, name=None):
        entry_time = row[entry_loc + 1]
        open_exits = [exit_time for exit_time in open_exits if exit_time > entry_time]
        if len(open_exits) >= cap:
            continue
        kept_indices.append(row[0])
        open_exits.append(row[exit_loc + 1])
    return trades.loc[kept_indices].reset_index(drop=True) if kept_indices else trades.iloc[0:0].copy()


def simulate_rr2(
    df: pd.DataFrame,
    entries: pd.DataFrame,
    stop_mode: str,
    stop_buffer: float,
    min_risk: float,
    max_risk: float,
    max_hold_bars: int,
    cap: int,
) -> pd.DataFrame:
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    session_id = df["session_id"].to_numpy(int)
    rows = []

    for entry_row in entries.itertuples(index=False):
        entry_pos = int(entry_row.entry_pos)
        direction = str(entry_row.direction)
        entry_price = float(entry_row.entry_price)
        level = float(entry_row.level)
        if direction == "long":
            stop_price = (float(entry_row.retest_low) if stop_mode == "retest" else level) - stop_buffer
            risk = entry_price - stop_price
            target_price = entry_price + 2.0 * risk
        else:
            stop_price = (float(entry_row.retest_high) if stop_mode == "retest" else level) + stop_buffer
            risk = stop_price - entry_price
            target_price = entry_price - 2.0 * risk
        if not math.isfinite(risk) or risk < min_risk or risk > max_risk:
            continue

        end_pos = min(len(df) - 1, entry_pos + max_hold_bars)
        while end_pos > entry_pos and session_id[end_pos] != session_id[entry_pos]:
            end_pos -= 1
        exit_price = float(close[end_pos])
        exit_pos = end_pos
        exit_reason = "time_exit"
        for pos in range(entry_pos, end_pos + 1):
            if direction == "long":
                if low[pos] <= stop_price:
                    exit_price = stop_price
                    exit_pos = pos
                    exit_reason = "stop"
                    break
                if high[pos] >= target_price:
                    exit_price = target_price
                    exit_pos = pos
                    exit_reason = "target_2r"
                    break
            else:
                if high[pos] >= stop_price:
                    exit_price = stop_price
                    exit_pos = pos
                    exit_reason = "stop"
                    break
                if low[pos] <= target_price:
                    exit_price = target_price
                    exit_pos = pos
                    exit_reason = "target_2r"
                    break

        gross = exit_price - entry_price if direction == "long" else entry_price - exit_price
        net = gross - ROUND_TURN_COST_POINTS
        rows.append({
            **entry_row._asdict(),
            "stop_mode": stop_mode,
            "stop_buffer": stop_buffer,
            "max_hold_bars": max_hold_bars,
            "max_concurrent_positions": cap,
            "exit_time": idx[exit_pos],
            "stop_price": stop_price,
            "target_price": target_price,
            "risk_points": risk,
            "gross_points": gross,
            "net_points": net,
            "r_net": net / risk,
            "exit_reason": exit_reason,
            "hold_bars": int(exit_pos - entry_pos + 1),
        })

    trades = pd.DataFrame(rows)
    if trades.empty:
        return trades
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    return apply_concurrency_cap(trades, cap)


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


def summarize(trades: pd.DataFrame, trading_days: int) -> dict:
    pnl = trades["net_points"].astype(float) if len(trades) else pd.Series(dtype=float)
    yearly = trades.groupby("year")["net_points"].sum() if len(trades) else pd.Series(dtype=float)
    monthly = trades.groupby("month")["net_points"].sum() if len(trades) else pd.Series(dtype=float)
    return {
        "trades": int(len(trades)),
        "trading_days": int(trading_days),
        "active_days": int(trades["day"].nunique()) if len(trades) else 0,
        "trades_per_day": float(len(trades) / trading_days) if trading_days else 0.0,
        "trades_per_active_day": float(len(trades) / trades["day"].nunique()) if len(trades) and trades["day"].nunique() else 0.0,
        "net_points": float(pnl.sum()) if len(pnl) else 0.0,
        "avg_points": float(pnl.mean()) if len(pnl) else 0.0,
        "profit_factor": profit_factor(pnl),
        "win_rate": float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
        "target_rate": float((trades["exit_reason"] == "target_2r").mean() * 100) if len(trades) else 0.0,
        "max_drawdown_points": max_drawdown(pnl),
        "positive_years": int((yearly > 0).sum()) if len(yearly) else 0,
        "years": int(yearly.size),
        "positive_month_rate": float((monthly > 0).mean() * 100) if monthly.size else 0.0,
        "avg_risk": float(trades["risk_points"].mean()) if len(trades) else 0.0,
        "avg_hold_bars": float(trades["hold_bars"].mean()) if len(trades) else 0.0,
    }


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def prefix_metrics(prefix: str, metrics: dict) -> dict:
    return {prefix + "_" + key: value for key, value in metrics.items()}


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join("<th>%s</th>" % c for c in show.columns)
    rows = []
    for _, row in show.iterrows():
        cells = []
        for col, value in row.items():
            cls = ""
            if col in {"full_net_points", "sample2026_net_points", "full_profit_factor", "sample2026_profit_factor", "score"}:
                try:
                    num = float(value)
                    cls = "pos" if (num >= 1 if "profit_factor" in col else num > 0) else "neg"
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


def write_reports(summary: pd.DataFrame, best_trades: pd.DataFrame | None) -> None:
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#18332f;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#d8e7e2}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    target = summary[summary["full_target_frequency"]].sort_values("full_net_points", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m Session Liquidity RR2 Sweep</title><style>%s</style></head>
<body><header><h1>2m Session Liquidity RR2 Sweep</h1><p>Fixed 1:2 RR multi-level breakout/retest: opening range, previous day, previous session.</p></header><main>
%s%s
</main></body></html>""" % (
        css,
        table_html(target, "Configs Within 10-20 Trades/Day On Full Period", 160),
        table_html(summary.sort_values("score", ascending=False), "All Configs Ranked", 220),
    )
    (OUTPUT_DIR / "session_liquidity_rr2_sweep_report.html").write_text(html, encoding="utf-8")

    if best_trades is None or best_trades.empty:
        return
    yearly = round_floats(best_trades.groupby("year").agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
        avg_risk=("risk_points", "mean"),
    ).reset_index())
    monthly = round_floats(best_trades.groupby("month").agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
        avg_risk=("risk_points", "mean"),
    ).reset_index())
    yearly.to_csv(OUTPUT_DIR / "session_liquidity_rr2_best_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "session_liquidity_rr2_best_monthly.csv", index=False, encoding="utf-8-sig")
    period_html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m Session Liquidity RR2 Period Report</title><style>%s</style></head>
<body><header><h1>2m Session Liquidity RR2 Period Report</h1><p>Yearly and monthly report for the selected target-frequency configuration.</p></header><main>
%s%s
</main></body></html>""" % (css, table_html(yearly, "Yearly Report"), table_html(monthly, "Monthly Report"))
    (OUTPUT_DIR / "session_liquidity_rr2_best_period_report.html").write_text(period_html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_df = load_data()
    trading_days = int(pd.Series(raw_df.index.date).nunique())
    trading_days_2026 = int(pd.Series(raw_df[raw_df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")].index.date).nunique())
    rows = []
    best_trades = None
    best_key = None
    best_net = -math.inf

    def evaluate_entries(
        df: pd.DataFrame,
        entries: pd.DataFrame,
        or_bars: int,
        level_set: str,
        signal_mode: str,
        bias_mode: str,
        displacement_mode: str,
        retest_window: int,
        cooldown_bars: int,
    ) -> None:
        nonlocal best_trades, best_key, best_net
        if entries.empty:
            return
        for stop_mode in STOP_MODES:
            for stop_buffer in STOP_BUFFERS:
                for min_risk in MIN_RISKS:
                    for max_risk in MAX_RISKS:
                        if min_risk >= max_risk:
                            continue
                        for max_hold_bars in MAX_HOLD_BARS_SET:
                            for cap in CONCURRENCY_CAPS:
                                trades = simulate_rr2(df, entries, stop_mode, stop_buffer, min_risk, max_risk, max_hold_bars, cap)
                                if trades.empty:
                                    continue
                                trades2026 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
                                config_id = "or%s_%s_%s_%s_%s_rt%s_cd%s_%s_sb%s_min%s_max%s_hold%s_cap%s" % (
                                    or_bars,
                                    level_set.replace(",", "-"),
                                    signal_mode,
                                    bias_mode,
                                    displacement_mode,
                                    retest_window,
                                    cooldown_bars,
                                    stop_mode,
                                    str(stop_buffer).replace(".", "p"),
                                    str(min_risk).replace(".", "p"),
                                    str(max_risk).replace(".", "p"),
                                    max_hold_bars,
                                    cap,
                                )
                                row = {
                                    "config_id": config_id,
                                    "or_bars": or_bars,
                                    "level_set": level_set,
                                    "signal_mode": signal_mode,
                                    "bias_mode": bias_mode,
                                    "displacement_mode": displacement_mode,
                                    "retest_window": retest_window,
                                    "cooldown_bars": cooldown_bars,
                                    "stop_mode": stop_mode,
                                    "stop_buffer": stop_buffer,
                                    "min_risk": min_risk,
                                    "max_risk": max_risk,
                                    "max_hold_bars": max_hold_bars,
                                    "max_concurrent_positions": cap,
                                }
                                row.update(prefix_metrics("full", summarize(trades, trading_days)))
                                row.update(prefix_metrics("sample2026", summarize(trades2026, trading_days_2026)))
                                row["full_target_frequency"] = 10.0 <= row["full_trades_per_day"] <= 20.0
                                row["sample2026_target_frequency"] = 10.0 <= row["sample2026_trades_per_day"] <= 20.0
                                row["score"] = (
                                    row["full_net_points"]
                                    - row["full_max_drawdown_points"] * 0.20
                                    + row["full_positive_month_rate"] * 5.0
                                    + (1000.0 if row["full_target_frequency"] else 0.0)
                                    + row["sample2026_net_points"] * 0.10
                                )
                                rows.append(row)
                                if row["full_target_frequency"] and row["full_net_points"] > best_net:
                                    best_net = row["full_net_points"]
                                    best_key = config_id
                                    best_trades = trades.copy()

    for or_bars in OR_BARS_SET:
        df = add_level_columns(raw_df, or_bars)
        for level_set in LEVEL_SETS:
            for signal_mode in SIGNAL_MODES:
                for bias_mode in BIAS_MODES:
                    for displacement_mode in DISPLACEMENT_MODES:
                        for retest_window in RETEST_WINDOWS:
                            for cooldown_bars in COOLDOWN_BARS_SET:
                                entries = find_entries(df, level_set, retest_window, cooldown_bars, signal_mode, bias_mode, displacement_mode)
                                print(
                                    "ENTRIES",
                                    "or", or_bars,
                                    "levels", level_set,
                                    "mode", signal_mode,
                                    "bias", bias_mode,
                                    "disp", displacement_mode,
                                    "retest", retest_window,
                                    "cooldown", cooldown_bars,
                                    len(entries),
                                    flush=True,
                                )
                                evaluate_entries(df, entries, or_bars, level_set, signal_mode, bias_mode, displacement_mode, retest_window, cooldown_bars)

    summary = round_floats(pd.DataFrame(rows).sort_values(["full_target_frequency", "full_net_points"], ascending=[False, False]))
    summary.to_csv(OUTPUT_DIR / "session_liquidity_rr2_sweep_summary.csv", index=False, encoding="utf-8-sig")
    if best_trades is not None:
        best_trades.to_csv(OUTPUT_DIR / "session_liquidity_rr2_best_trades.csv", index=False, encoding="utf-8-sig")
    write_reports(summary, best_trades)
    print("=== 2M SESSION LIQUIDITY RR2 SWEEP ===")
    print("Configs:", len(summary), "Trading days:", trading_days, "2026 days:", trading_days_2026)
    print("Best target-frequency config:", best_key)
    print(summary.head(40).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
