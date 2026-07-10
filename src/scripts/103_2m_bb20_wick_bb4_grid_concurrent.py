# -*- coding: utf-8 -*-
"""2m BB20 wick breakout -> opposite BB4 pullback grid.

Purpose:
- Keep the profitable/high-frequency candidate reproducible.
- Base timeframe: XAUUSD 2m.
- Signal: price wicks outside BB20/2 close band.
- Entry: pullback limit at the opposite BB4/4 open band within N bars.
- Position management: reuse Strategy2 three-entry grid engine.
- Evaluation mode: every signal is tested independently, allowing overlap.

This is not a fixed 1:2 RR system. It is the closest candidate found so far
that can reach the requested 10-20 trades/day range while staying profitable
on the 2026 Jan-Jun sample.
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
TEST_START = os.environ.get("TEST_START", "2026-01-01")
TEST_END = os.environ.get("TEST_END", "2026-06-17")
PENDING_BARS = int(os.environ.get("PENDING_BARS", "20"))
REGIME_FILTER = os.environ.get("REGIME_FILTER", "none")
MAX_CONCURRENT_POSITIONS = int(os.environ.get("MAX_CONCURRENT_POSITIONS", "5"))
PERIOD_LABEL = TEST_START[:10].replace("-", "") + "_" + TEST_END[:10].replace("-", "")
OUTPUT_DIR = ROOT / "result" / ("bb20_wick_bb4_grid_concurrent_2m_" + PERIOD_LABEL + "_" + REGIME_FILTER)


spec = importlib.util.spec_from_file_location("strategy2_base", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
sys.modules["strategy2_base"] = base
assert spec.loader is not None
spec.loader.exec_module(base)


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def load_full_data() -> pd.DataFrame:
    return quiet_call(base.load_tf, "2m")


def filter_test_period(df: pd.DataFrame) -> pd.DataFrame:
    start = pd.Timestamp(TEST_START, tz="Asia/Seoul")
    end = pd.Timestamp(TEST_END, tz="Asia/Seoul")
    return df[(df.index >= start) & (df.index < end)].copy()


def build_month_regime_filter(df: pd.DataFrame) -> set[str]:
    if REGIME_FILTER == "none":
        return set(df.index.strftime("%Y-%m").unique())

    daily = df.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    active = set()
    for month in sorted(set(df.index.strftime("%Y-%m"))):
        month_start = pd.Timestamp(month + "-01", tz="Asia/Seoul")
        prior = daily[daily.index < month_start]
        if len(prior) < 240:
            continue
        ret60 = float(prior["close"].iloc[-1] / prior["close"].iloc[-60] - 1.0)
        ret240 = float(prior["close"].iloc[-1] / prior["close"].iloc[-240] - 1.0)
        if REGIME_FILTER == "ret60_le_0p129_ret240_ge_0p272":
            if ret60 <= 0.12865644775603652 and ret240 >= 0.2717372789169091:
                active.add(month)
        else:
            raise ValueError("unknown REGIME_FILTER: %s" % REGIME_FILTER)
    return active


def find_entries(df: pd.DataFrame, active_months: set[str]) -> pd.DataFrame:
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    upper20 = df["bb20_2_upper_close"].to_numpy(float)
    lower20 = df["bb20_2_lower_close"].to_numpy(float)
    upper4 = df["bb4_4_upper_open"].to_numpy(float)
    lower4 = df["bb4_4_lower_open"].to_numpy(float)
    sessions = df["session"].astype(str).to_numpy()

    rows = []
    for breakout_pos in range(120, len(df) - PENDING_BARS - 1):
        if idx[breakout_pos].strftime("%Y-%m") not in active_months:
            continue
        long_signal = high[breakout_pos] > upper20[breakout_pos]
        short_signal = low[breakout_pos] < lower20[breakout_pos]
        if not (long_signal or short_signal):
            continue

        direction = "long" if long_signal else "short"
        limit_price = lower4[breakout_pos] if direction == "long" else upper4[breakout_pos]
        if not math.isfinite(limit_price):
            continue

        entry_pos = None
        for pos in range(breakout_pos + 1, min(len(df), breakout_pos + PENDING_BARS + 1)):
            if not base.entry_time_allowed(idx[pos]):
                continue
            hit = low[pos] <= limit_price if direction == "long" else high[pos] >= limit_price
            if hit:
                entry_pos = pos
                break
        if entry_pos is None:
            continue

        candle_range = float(high[breakout_pos] - low[breakout_pos])
        close_position = math.nan
        if candle_range > 0:
            close_position = (
                float((close[breakout_pos] - low[breakout_pos]) / candle_range)
                if direction == "long"
                else float((high[breakout_pos] - close[breakout_pos]) / candle_range)
            )

        ts = idx[entry_pos]
        rows.append({
            "tf": "2m",
            "strategy": "bb20_wick_bb4_opposite_grid_concurrent",
            "direction": direction,
            "pending_bars": PENDING_BARS,
            "breakout_pos": breakout_pos,
            "entry_pos": entry_pos,
            "breakout_time": idx[breakout_pos],
            "entry_time": ts,
            "entry_price": float(limit_price),
            "breakout_close_position": close_position,
            "bars_to_fill": int(entry_pos - breakout_pos),
            "session": str(sessions[entry_pos]),
            "year": int(ts.year),
            "month": ts.strftime("%Y-%m"),
            "day": ts.date().isoformat(),
        })
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


def summarize_group(group: pd.DataFrame, trading_days: int) -> dict:
    pnl = pd.to_numeric(group["net_points"], errors="coerce").fillna(0.0)
    return {
        "trades": int(len(group)),
        "trading_days": int(trading_days),
        "active_days": int(group["day"].nunique()),
        "trades_per_day": float(len(group) / trading_days) if trading_days else 0.0,
        "trades_per_active_day": float(len(group) / group["day"].nunique()) if group["day"].nunique() else 0.0,
        "net_points": float(pnl.sum()),
        "avg_points": float(pnl.mean()) if len(pnl) else 0.0,
        "profit_factor": profit_factor(pnl),
        "win_rate": float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
        "max_drawdown_points": max_drawdown(pnl),
        "avg_filled_entries": float(group["filled_entries"].mean()) if len(group) else 0.0,
        "stop_rate": float((group["exit_reason"] == "stop_35p").mean() * 100) if len(group) else 0.0,
        "avg_bars_to_fill": float(group["bars_to_fill"].mean()) if len(group) else 0.0,
    }


def apply_concurrency_cap(trades: pd.DataFrame, cap: int) -> pd.DataFrame:
    if cap <= 0:
        return trades.iloc[0:0].copy()
    open_exits = []
    kept = []
    for _, row in trades.sort_values("entry_time").iterrows():
        entry_time = row["entry_time"]
        open_exits = [exit_time for exit_time in open_exits if exit_time > entry_time]
        if len(open_exits) >= cap:
            continue
        kept.append(row)
        open_exits.append(row["exit_time"])
    return pd.DataFrame(kept).reset_index(drop=True) if kept else trades.iloc[0:0].copy()


def concurrency_cap_report(trades: pd.DataFrame, trading_days: int) -> pd.DataFrame:
    caps = [1, 2, 3, 5, 8, 10, 15, 20, 999999]
    rows = []
    for cap in caps:
        capped = trades.copy() if cap == 999999 else apply_concurrency_cap(trades, cap)
        row = {"max_concurrent_positions": "none" if cap == 999999 else cap}
        row.update(summarize_group(capped, trading_days))
        rows.append(row)
    return round_floats(pd.DataFrame(rows))


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def grouped(
    trades: pd.DataFrame,
    cols: list[str],
    trading_days: int,
    day_counts: dict | None = None,
) -> pd.DataFrame:
    rows = []
    for key, group in trades.groupby(cols, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        group_days = trading_days
        if day_counts is not None:
            lookup_key = key if len(cols) > 1 else key[0]
            group_days = int(day_counts.get(lookup_key, trading_days))
        row = dict(zip(cols, key))
        row.update(summarize_group(group, group_days))
        rows.append(row)
    return round_floats(pd.DataFrame(rows))


def table_html(df: pd.DataFrame, title: str) -> str:
    headers = "".join("<th>%s</th>" % c for c in df.columns)
    body = []
    for _, row in df.iterrows():
        cells = []
        for col, value in row.items():
            cls = ""
            if col in {"net_points", "avg_points", "profit_factor"}:
                try:
                    number = float(value)
                    cls = "pos" if (number >= 1 if col == "profit_factor" else number > 0) else "neg"
                except Exception:
                    pass
            text = "" if pd.isna(value) else ("%.4f" % value if isinstance(value, float) else str(value))
            cells.append("<td class='%s'>%s</td>" % (cls, text))
        body.append("<tr>%s</tr>" % "".join(cells))
    return "<section><h2>%s</h2><div><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></section>" % (
        title,
        headers,
        "".join(body),
    )


def write_html(
    overall: pd.DataFrame,
    cap_summary: pd.DataFrame,
    yearly: pd.DataFrame,
    monthly: pd.DataFrame,
    sessions: pd.DataFrame,
    exits: pd.DataFrame,
):
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#101820;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#c9d3df}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m BB20 Wick BB4 Grid Concurrent</title><style>%s</style></head>
<body><header><h1>2m BB20 Wick -> Opposite BB4 Grid Concurrent</h1><p>Every signal evaluated independently. Cost 0.5P per filled unit through the reused Strategy2 grid engine.</p></header><main>
%s%s%s%s%s%s
</main></body></html>""" % (
        css,
        table_html(overall, "Overall"),
        table_html(cap_summary, "Concurrency Cap Sensitivity"),
        table_html(yearly.sort_values("year"), "Yearly Report"),
        table_html(monthly.sort_values("month"), "Monthly Report"),
        table_html(sessions.sort_values("net_points", ascending=False), "Session Report"),
        table_html(exits.sort_values("exit_reason"), "Exit Report"),
    )
    (OUTPUT_DIR / "bb20_wick_bb4_grid_concurrent_report.html").write_text(html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    full_df = load_full_data()
    df = filter_test_period(full_df)
    active_months = build_month_regime_filter(full_df)
    trading_days = int(pd.Series(df.index.date).nunique())
    df_days = pd.DataFrame({"ts": df.index})
    df_days["day"] = df_days["ts"].dt.date
    df_days["year"] = df_days["ts"].dt.year
    df_days["month"] = df_days["ts"].dt.strftime("%Y-%m")
    year_days = df_days.groupby("year")["day"].nunique().to_dict()
    month_days = df_days.groupby("month")["day"].nunique().to_dict()
    entries = find_entries(df, active_months)
    rows = []
    for _, entry in entries.iterrows():
        sim = base.simulate_trade(df, entry)
        row = entry.to_dict()
        row.update(sim)
        rows.append(row)
    trades = pd.DataFrame(rows)
    if trades.empty:
        raise RuntimeError("No trades generated")
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])

    raw_trades = trades.copy()
    cap_summary = concurrency_cap_report(raw_trades, trading_days)
    trades = apply_concurrency_cap(raw_trades, MAX_CONCURRENT_POSITIONS)

    overall = round_floats(pd.DataFrame([summarize_group(trades, trading_days)]))
    yearly = grouped(trades, ["year"], trading_days, day_counts=year_days)
    monthly = grouped(trades, ["month"], trading_days, day_counts=month_days)
    sessions = grouped(trades, ["session"], trading_days)
    exits = grouped(trades, ["exit_reason"], trading_days)

    entries.to_csv(OUTPUT_DIR / "bb20_wick_bb4_grid_entries.csv", index=False, encoding="utf-8-sig")
    raw_trades.to_csv(OUTPUT_DIR / "bb20_wick_bb4_grid_raw_trades.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(OUTPUT_DIR / "bb20_wick_bb4_grid_capped_trades.csv", index=False, encoding="utf-8-sig")
    overall.to_csv(OUTPUT_DIR / "bb20_wick_bb4_grid_overall.csv", index=False, encoding="utf-8-sig")
    cap_summary.to_csv(OUTPUT_DIR / "bb20_wick_bb4_grid_concurrency_caps.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "bb20_wick_bb4_grid_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "bb20_wick_bb4_grid_monthly.csv", index=False, encoding="utf-8-sig")
    sessions.to_csv(OUTPUT_DIR / "bb20_wick_bb4_grid_sessions.csv", index=False, encoding="utf-8-sig")
    exits.to_csv(OUTPUT_DIR / "bb20_wick_bb4_grid_exits.csv", index=False, encoding="utf-8-sig")
    write_html(overall, cap_summary, yearly, monthly, sessions, exits)

    print("=== 2M BB20 WICK BB4 GRID CONCURRENT ===")
    print(
        "TEST_START:",
        TEST_START,
        "TEST_END:",
        TEST_END,
        "PENDING_BARS:",
        PENDING_BARS,
        "REGIME_FILTER:",
        REGIME_FILTER,
        "MAX_CONCURRENT_POSITIONS:",
        MAX_CONCURRENT_POSITIONS,
    )
    print(overall.to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
