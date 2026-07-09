# -*- coding: utf-8 -*-
"""Double-BB breakout opposite-band grid across 2m/5m/10m/15m.

Purpose:
- Build a trend-following candidate from the two Bollinger bands requested:
  BB20/2 on close and BB4/4 on open.
- Compare 2m, 5m, 10m, and 15m with the same practical rule set.
- Apply the monthly regime filter from Candidate 1, decided only from prior
  daily data.

Rule:
- Monthly filter: ret20 >= 0.0084, ret240 >= -0.0428, ADR20 >= 18P.
- Breakout: close outside both BB20/2 and BB4/4 in the same direction.
- Trend confirmation: SMA20/SMA120 and SMA120 slope agree with breakout.
- Entry: active breakout signal keeps an opposite BB4/4 limit until replaced by
  a new breakout. Fill only KST 09:00 <= time < 18:00.
- Position: 3 entries, 10P spacing, stop 35P from entry1.
- Exit: if 1/2 fills, close arms trail at avg +/-10P with 10P close trail.
  If 3 fills, reduce 50% at avg +/-3P, trail remaining by 10P.
- Same-bar order is conservative: fills first, then stop, then recovery/targets.
"""
from __future__ import annotations

import contextlib
import io
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gold_data_prep as prep  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "result" / "strategy2_grid_multitimeframe_month_filter"

TFS = ["2m", "5m", "10m", "15m"]
RET20_MIN = 0.0084
RET240_MIN = -0.0428
ADR20_MIN = 18.0

ENTRY_START_MINUTE = 9 * 60
ENTRY_END_MINUTE = 18 * 60
COST_PER_UNIT = 0.50
GRID_STEP = 10.0
MAX_ENTRIES = 3
STOP_FROM_ENTRY1 = 35.0
REGULAR_ARM = 10.0
TRAIL_POINTS = 10.0
R2_RECOVERY_PROFIT = 3.0
REDUCE_FRACTION = 0.50
DAY_STOP_POINTS = 50.0


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def load_tf(tf: str) -> pd.DataFrame:
    if tf == "15m":
        one = quiet_call(prep.load_gold_data, DATA_DIR / "xauusd_1m_2010-01-01_2026-06-16.csv", timeframe="1m")
        df = one.resample("15min", label="left", closed="left").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna(subset=["open", "high", "low", "close"])
    else:
        df = quiet_call(prep.load_gold_data, DATA_DIR / ("xauusd_%s_2010-01-01_2026-06-16.csv" % tf), timeframe=tf)
    df = prep.assign_session(df)
    df = prep.add_bollinger_bands(df, ddof=0)
    df = add_trend_columns(df)
    df.attrs["timeframe"] = tf
    return df


def add_trend_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["sma20"] = out["close"].rolling(20, min_periods=20).mean()
    out["sma120"] = out["close"].rolling(120, min_periods=120).mean()
    out["sma120_slope"] = out["sma120"] - out["sma120"].shift(20)
    out["long_breakout"] = (
        (out["close"] > out["bb20_2_upper_close"])
        & (out["close"] > out["bb4_4_upper_open"])
        & (out["sma20"] > out["sma120"])
        & (out["sma120_slope"] > 0)
    ).fillna(False)
    out["short_breakout"] = (
        (out["close"] < out["bb20_2_lower_close"])
        & (out["close"] < out["bb4_4_lower_open"])
        & (out["sma20"] < out["sma120"])
        & (out["sma120_slope"] < 0)
    ).fillna(False)
    return out


def build_month_features() -> tuple[pd.DataFrame, set[str], int]:
    bars = quiet_call(prep.load_gold_data, DATA_DIR / "xauusd_5m_2010-01-01_2026-06-16.csv", timeframe="5m")
    daily = bars.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    daily["range"] = daily["high"] - daily["low"]
    rows = []
    active = set()
    for month in pd.period_range("2010-01", "2026-06", freq="M"):
        month_start = pd.Timestamp(month.start_time, tz="Asia/Seoul")
        prior = daily[daily.index < month_start]
        if len(prior) < 260:
            continue
        ret20 = float(prior["close"].iloc[-1] / prior["close"].iloc[-20] - 1.0)
        ret240 = float(prior["close"].iloc[-1] / prior["close"].iloc[-240] - 1.0)
        adr20 = float(prior["range"].iloc[-20:].mean())
        is_active = ret20 >= RET20_MIN and ret240 >= RET240_MIN and adr20 >= ADR20_MIN
        rows.append({"month": str(month), "ret20": ret20, "ret240": ret240, "adr20": adr20, "active": is_active})
        if is_active:
            active.add(str(month))
    active_days = int(daily[daily.index.strftime("%Y-%m").isin(active)].shape[0])
    return pd.DataFrame(rows), active, active_days


def entry_time_allowed(ts: pd.Timestamp) -> bool:
    kst = ts.tz_convert("Asia/Seoul") if ts.tzinfo is not None else ts.tz_localize("Asia/Seoul")
    minute = kst.hour * 60 + kst.minute
    return ENTRY_START_MINUTE <= minute < ENTRY_END_MINUTE


def find_entries(df: pd.DataFrame, tf: str, active_months: set[str]) -> pd.DataFrame:
    rows = []
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    bb44_upper = df["bb4_4_upper_open"].to_numpy(float)
    bb44_lower = df["bb4_4_lower_open"].to_numpy(float)
    long_break = df["long_breakout"].to_numpy(bool)
    short_break = df["short_breakout"].to_numpy(bool)
    active = None

    for pos in range(len(df)):
        month = idx[pos].strftime("%Y-%m")
        if month not in active_months:
            active = None
            continue

        if long_break[pos] and not pd.isna(bb44_lower[pos]):
            active = {"direction": "long", "breakout_pos": pos, "limit_price": float(bb44_lower[pos])}
            continue
        if short_break[pos] and not pd.isna(bb44_upper[pos]):
            active = {"direction": "short", "breakout_pos": pos, "limit_price": float(bb44_upper[pos])}
            continue
        if active is None or pos <= active["breakout_pos"]:
            continue

        direction = active["direction"]
        limit_price = active["limit_price"]
        hit = low[pos] <= limit_price if direction == "long" else high[pos] >= limit_price
        if not hit or not entry_time_allowed(idx[pos]):
            continue

        bi = active["breakout_pos"]
        candle_range = float(high[bi] - low[bi])
        close_pos = math.nan
        if candle_range > 0:
            close_pos = float((close[bi] - low[bi]) / candle_range) if direction == "long" else float((high[bi] - close[bi]) / candle_range)
        rows.append({
            "tf": tf,
            "direction": direction,
            "breakout_pos": bi,
            "entry_pos": pos,
            "breakout_time": idx[bi],
            "entry_time": idx[pos],
            "entry_price": limit_price,
            "breakout_close_position": close_pos,
            "bars_to_fill": pos - bi,
            "session": str(df["session"].iloc[pos]),
            "year": int(idx[pos].year),
            "month": idx[pos].strftime("%Y-%m"),
            "day": idx[pos].date().isoformat(),
        })
        active = None

    return pd.DataFrame(rows)


def pnl_for_exit(direction: str, avg_entry: float, exit_price: float, qty: float) -> float:
    return (exit_price - avg_entry) * qty if direction == "long" else (avg_entry - exit_price) * qty


def simulate_trade(df: pd.DataFrame, row: pd.Series) -> dict:
    direction = str(row["direction"])
    entry_pos = int(row["entry_pos"])
    entry1 = float(row["entry_price"])
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)

    levels = [entry1 - i * GRID_STEP for i in range(MAX_ENTRIES)] if direction == "long" else [entry1 + i * GRID_STEP for i in range(MAX_ENTRIES)]
    stop = entry1 - STOP_FROM_ENTRY1 if direction == "long" else entry1 + STOP_FROM_ENTRY1
    filled = [False] * MAX_ENTRIES
    fill_prices = []
    open_qty = 0.0
    avg_entry = math.nan
    realized = 0.0
    reduced_after_third = False
    trailing = False
    trail_stop = math.nan
    trail_active_from = math.inf
    exit_reason = "open_at_data_end"
    exit_time = idx[-1]
    exit_price = float(close[-1])
    mfe = 0.0
    mae = 0.0

    for pos in range(entry_pos, len(idx)):
        hi = float(high[pos])
        lo = float(low[pos])
        cl = float(close[pos])

        for i, level in enumerate(levels):
            if filled[i]:
                continue
            fill_hit = lo <= level if direction == "long" else hi >= level
            if fill_hit:
                filled[i] = True
                fill_prices.append(level)
                open_qty += 1.0
                avg_entry = sum(fill_prices) / len(fill_prices)

        if open_qty <= 0 or math.isnan(avg_entry):
            continue

        if direction == "long":
            mfe = max(mfe, hi - avg_entry)
            mae = max(mae, avg_entry - lo)
        else:
            mfe = max(mfe, avg_entry - lo)
            mae = max(mae, hi - avg_entry)

        stop_hit = lo <= stop if direction == "long" else hi >= stop
        if stop_hit:
            realized += pnl_for_exit(direction, avg_entry, stop, open_qty)
            exit_reason = "stop_35p"
            exit_price = stop
            exit_time = idx[pos]
            open_qty = 0.0
            break

        if len(fill_prices) >= 3 and not reduced_after_third:
            recovery = avg_entry + R2_RECOVERY_PROFIT if direction == "long" else avg_entry - R2_RECOVERY_PROFIT
            recovery_hit = hi >= recovery if direction == "long" else lo <= recovery
            if recovery_hit:
                qty = open_qty * REDUCE_FRACTION
                realized += pnl_for_exit(direction, avg_entry, recovery, qty)
                open_qty -= qty
                reduced_after_third = True
                trailing = True
                trail_stop = avg_entry
                trail_active_from = pos + 1

        if open_qty <= 0:
            exit_reason = "recovery_full"
            exit_price = avg_entry
            exit_time = idx[pos]
            break

        trail_hit = trailing and pos >= trail_active_from and not math.isnan(trail_stop) and (lo <= trail_stop if direction == "long" else hi >= trail_stop)
        if trail_hit:
            realized += pnl_for_exit(direction, avg_entry, trail_stop, open_qty)
            exit_reason = "trail_10p"
            exit_price = trail_stop
            exit_time = idx[pos]
            open_qty = 0.0
            break

        if reduced_after_third:
            trail_stop = max(trail_stop, avg_entry, cl - TRAIL_POINTS) if direction == "long" else min(trail_stop, avg_entry, cl + TRAIL_POINTS)
            continue

        arm_hit = cl >= avg_entry + REGULAR_ARM if direction == "long" else cl <= avg_entry - REGULAR_ARM
        if arm_hit:
            trailing = True
            trail_active_from = min(trail_active_from, pos + 1)
            if direction == "long":
                trail_stop = max(avg_entry, cl - TRAIL_POINTS) if math.isnan(trail_stop) else max(trail_stop, avg_entry, cl - TRAIL_POINTS)
            else:
                trail_stop = min(avg_entry, cl + TRAIL_POINTS) if math.isnan(trail_stop) else min(trail_stop, avg_entry, cl + TRAIL_POINTS)

    if open_qty > 0:
        final_close = float(close[-1])
        realized += pnl_for_exit(direction, avg_entry, final_close, open_qty)

    fills = len(fill_prices)
    return {
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "filled_entries": int(fills),
        "net_points": float(realized - COST_PER_UNIT * fills),
        "extra_cost_units": int(fills),
        "mfe_points": float(mfe),
        "mae_points": float(mae),
    }


def apply_day_stop(trades: pd.DataFrame) -> pd.DataFrame:
    kept = []
    day_pnl: dict[str, float] = {}
    stopped: set[str] = set()
    for _, row in trades.sort_values("entry_time").iterrows():
        day = str(row["day"])
        if day in stopped:
            continue
        kept.append(row)
        day_pnl[day] = day_pnl.get(day, 0.0) + float(row["net_points"])
        if day_pnl[day] <= -DAY_STOP_POINTS:
            stopped.add(day)
    return pd.DataFrame(kept)


def run_tf(tf: str, active_months: set[str]) -> pd.DataFrame:
    df = load_tf(tf)
    entries = find_entries(df, tf, active_months)
    rows = []
    next_allowed_pos = 0
    for _, entry in entries.sort_values("entry_pos").iterrows():
        if int(entry["entry_pos"]) < next_allowed_pos:
            continue
        sim = simulate_trade(df, entry)
        out = entry.to_dict()
        out.update(sim)
        rows.append(out)
        next_allowed_pos = int(df.index.searchsorted(sim["exit_time"])) + 1
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


def summarize_group(group: pd.DataFrame, extra_cost: float = 0.0) -> dict:
    values = group["net_points"].astype(float) - extra_cost * group["extra_cost_units"].astype(float)
    active_days = group["day"].nunique()
    return {
        "trades": int(len(group)),
        "active_days": int(active_days),
        "trades_per_active_day": float(len(group) / active_days) if active_days else 0.0,
        "net_points": float(values.sum()),
        "avg_points": float(values.mean()) if len(values) else 0.0,
        "profit_factor": profit_factor(values),
        "win_rate": float((values > 0).mean() * 100) if len(values) else 0.0,
        "max_drawdown_points": max_drawdown(values),
        "avg_filled_entries": float(group["filled_entries"].mean()) if len(group) else 0.0,
        "stop_rate": float((group["exit_reason"] == "stop_35p").mean() * 100) if len(group) else 0.0,
    }


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def grouped(trades: pd.DataFrame, cols: list[str], extra_cost: float = 0.0) -> pd.DataFrame:
    rows = []
    for key, group in trades.groupby(cols, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        row = dict(zip(cols, key))
        row.update(summarize_group(group, extra_cost=extra_cost))
        rows.append(row)
    return round_floats(pd.DataFrame(rows))


def write_html(summary, summary_cost, yearly, monthly, exits):
    def table_html(df, title):
        headers = "".join("<th>%s</th>" % c for c in df.columns)
        rows = []
        for _, row in df.iterrows():
            cells = []
            for col, value in row.items():
                cls = ""
                if col in {"net_points", "avg_points", "profit_factor"}:
                    try:
                        num = float(value)
                        cls = "pos" if (num >= 1 if col == "profit_factor" else num > 0) else "neg"
                    except Exception:
                        pass
                text = "" if pd.isna(value) else ("%.4f" % value if isinstance(value, float) else str(value))
                cells.append("<td class='%s'>%s</td>" % (cls, text))
            rows.append("<tr>%s</tr>" % "".join(cells))
        return "<section><h2>%s</h2><div><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></section>" % (title, headers, "".join(rows))

    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#101820;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#c9d3df}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child{text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Strategy2 Grid Multi-Timeframe</title><style>%s</style></head>
<body><header><h1>Strategy2 Grid Multi-Timeframe With Monthly Filter</h1><p>BB20/2 close + BB4/4 open breakout/opposite-limit grid. 2m/5m/10m/15m, monthly regime filter, KST 09:00-18:00, day stop -50P.</p></header><main>
%s%s%s%s%s
</main></body></html>""" % (
        css,
        table_html(summary.sort_values("net_points", ascending=False), "Timeframe Summary"),
        table_html(summary_cost, "Cost Sensitivity By Timeframe"),
        table_html(yearly.sort_values(["tf", "year"]), "Yearly Report"),
        table_html(monthly.sort_values(["tf", "month"]), "Monthly Report"),
        table_html(exits.sort_values(["tf", "exit_reason"]), "Exit Report"),
    )
    (OUTPUT_DIR / "strategy2_grid_multitimeframe_report.html").write_text(html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    month_features, active_months, active_days = build_month_features()
    month_features.to_csv(OUTPUT_DIR / "month_features.csv", index=False, encoding="utf-8-sig")

    parts = []
    for tf in TFS:
        print("RUN", tf)
        trades = run_tf(tf, active_months)
        print(tf, "raw trades", len(trades))
        parts.append(trades)
    all_trades = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    selected_parts = []
    for tf, group in all_trades.groupby("tf", sort=True):
        selected_parts.append(apply_day_stop(group))
    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else pd.DataFrame()

    summary = grouped(selected, ["tf"])
    yearly = grouped(selected, ["tf", "year"])
    monthly = grouped(selected, ["tf", "month"])
    exits = grouped(selected, ["tf", "exit_reason"])
    cost_rows = []
    for extra in [0.0, 0.2, 0.3, 0.5, 0.8, 1.0]:
        table = grouped(selected, ["tf"], extra_cost=extra)
        table.insert(1, "extra_cost_per_unit", extra)
        cost_rows.append(table)
    summary_cost = pd.concat(cost_rows, ignore_index=True)

    all_trades.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_raw_trades.csv", index=False, encoding="utf-8-sig")
    selected.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_selected_trades.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_summary.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_monthly.csv", index=False, encoding="utf-8-sig")
    exits.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_exits.csv", index=False, encoding="utf-8-sig")
    summary_cost.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_cost_sensitivity.csv", index=False, encoding="utf-8-sig")
    write_html(summary, summary_cost, yearly, monthly, exits)

    print("")
    print("=== STRATEGY2 GRID MULTI-TIMEFRAME MONTH FILTER ===")
    print("Active months:", int(month_features["active"].sum()), "active days:", active_days)
    print(summary.sort_values("net_points", ascending=False).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
