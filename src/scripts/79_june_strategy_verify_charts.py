# -*- coding: utf-8 -*-
"""Create June 2026 strategy-applied verification charts.

Baseline strategy shown in the HTML:
- pullback candidates: within_6_bars
- 1V: session_opening_range
- max entries: 3
- exit model: split_v_targets
- max holding bars: 48
"""
from __future__ import annotations

import html
import importlib.util
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gold_data_prep as prep  # noqa: E402


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RESULT_DIR = Path(__file__).resolve().parents[2] / "result"
OUTPUT_FILE = RESULT_DIR / "june_strategy_verify_charts.html"

JUNE_START = pd.Timestamp("2026-06-01 00:00", tz=prep.KST)
JUNE_END = pd.Timestamp("2026-07-01 00:00", tz=prep.KST)

V_METHOD = "session_opening_range"
EXIT_MODEL = "split_v_targets"
MAX_ENTRIES = 3
MAX_HOLDING_BARS = 48


def _load_chart_helpers():
    helper_path = SCRIPT_DIR / "78_june_doublebb_verify_charts.py"
    spec = importlib.util.spec_from_file_location("june_doublebb_verify_charts", helper_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHART = _load_chart_helpers()


def _fmt(value, digits=3):
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _strategy_trades_for_tf(timeframe):
    csv_path = DATA_DIR / f"xauusd_{timeframe}_2010-01-01_2026-06-16.csv"
    data = prep.load_gold_data(csv_path, timeframe=timeframe)
    data = prep.assign_session(data)
    data = prep.add_bollinger_bands(data)
    data = prep.detect_buy_breakout_double_bb(data)

    candidates = prep.find_buy_pullback_entries(data, max_bars=6)
    candidates = candidates[
        (candidates["entry_time"] >= JUNE_START)
        & (candidates["entry_time"] < JUNE_END)
    ].copy()
    candidates = candidates.sort_values("entry_time").tail(10)
    candidates = prep.add_v_metrics_to_candidates(data, candidates)

    grid = prep.simulate_grid_path(
        data,
        candidates,
        v_method=V_METHOD,
        max_entries=MAX_ENTRIES,
        max_holding_bars=MAX_HOLDING_BARS,
    )
    trades = prep.backtest_exit_model(
        data,
        grid,
        model_name=EXIT_MODEL,
        conservative_same_bar=True,
        fee_points=0.0,
        slippage_points=0.0,
        max_entries=MAX_ENTRIES,
        max_holding_bars=MAX_HOLDING_BARS,
    )
    return data, trades.sort_values("entry_time").reset_index(drop=True)


def _trade_detail_table(trade):
    cols = [
        "timeframe",
        "session",
        "breakout_time",
        "pullback_touch_time",
        "entry_time",
        "exit_time",
        "entry_1_price",
        "entry_2_price",
        "entry_3_price",
        "stop_price",
        "filled_entries_count",
        "max_filled_entries",
        "exit_reason",
        "realized_pnl_v",
        "realized_pnl_points",
        "v_method",
        "exit_model",
        "bars_to_pullback",
        "midline_broken_before_entry",
    ]
    headers = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    cells = "".join(f"<td>{html.escape(_fmt(trade.get(c)))}</td>" for c in cols)
    return f"<table><thead><tr>{headers}</tr></thead><tbody><tr>{cells}</tr></tbody></table>"


def _trade_ohlc_table(window, trade):
    event_times = {
        trade["breakout_time"]: "breakout",
        trade["pullback_touch_time"]: "pullback_touch",
        trade["entry_time"]: "entry",
        trade["exit_time"]: "exit",
    }
    cols = [
        "open",
        "high",
        "low",
        "close",
        "bb20_2_upper_close",
        "bb20_2_mid_close",
        "bb20_2_lower_close",
        "bb4_4_upper_open",
        "bb4_4_mid_open",
        "bb4_4_lower_open",
        "session",
    ]
    rows = window.loc[window.index.isin([t for t in event_times if pd.notna(t)]), cols].copy()
    rows.insert(0, "datetime_kst", rows.index.strftime("%Y-%m-%d %H:%M"))
    rows.insert(1, "event", "")
    for ts, label in event_times.items():
        if pd.notna(ts):
            rows.loc[rows.index == ts, "event"] = label
    headers = "".join(f"<th>{html.escape(c)}</th>" for c in rows.columns)
    body = []
    for _, row in rows.iterrows():
        body.append("<tr>" + "".join(f"<td>{html.escape(_fmt(row[c]))}</td>" for c in rows.columns) + "</tr>")
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _estimated_exit_price(trade):
    reason = str(trade.get("exit_reason", ""))
    avg = trade.get("avg_entry_price")
    v = trade.get("v_session_opening_range") if trade.get("v_method") == "session_opening_range" else trade.get("v_avg_range_20")
    if reason == "stop":
        return trade.get("stop_price")
    if pd.isna(avg) or pd.isna(v):
        return trade.get("entry_1_price")
    target_map = {
        "target_0_3v": 0.3,
        "target_0_5v": 0.5,
        "target_0_8v": 0.8,
        "target_1_0v": 1.0,
        "target_1_5v": 1.5,
        "target_2_0v": 2.0,
        "defensive_remaining_1v": 1.0,
    }
    if reason == "defensive_entry1_70pct":
        return trade.get("entry_1_price")
    if reason in target_map:
        return float(avg) + target_map[reason] * float(v)
    return trade.get("entry_1_price")


def _chart_for_trade(data, trade, chart_id, title):
    idx = data.index
    breakout_pos = idx.searchsorted(trade["breakout_time"])
    exit_pos = idx.searchsorted(trade["exit_time"]) if pd.notna(trade["exit_time"]) else idx.searchsorted(trade["entry_time"])
    start_pos = max(0, breakout_pos - 30)
    end_pos = min(len(data) - 1, exit_pos + 20)
    window = data.iloc[start_pos:end_pos + 1].copy()

    markers = [
        ("B", trade["breakout_time"], data.loc[trade["breakout_time"], "close"], "breakout"),
        ("P", trade["pullback_touch_time"], data.loc[trade["pullback_touch_time"], "low"], "pullback"),
        ("E1", trade["entry_time"], trade["entry_1_price"], "entry"),
        ("X", trade["exit_time"], _estimated_exit_price(trade), "exit"),
    ]
    if trade.get("max_filled_entries", 1) >= 2:
        markers.append(("E2", trade["entry_time"], trade["entry_2_price"], "entry2"))
    if trade.get("max_filled_entries", 1) >= 3:
        markers.append(("E3", trade["entry_time"], trade["entry_3_price"], "entry3"))
    chart = CHART._svg_chart(window, chart_id, title, markers)
    return chart + _trade_detail_table(trade) + _trade_ohlc_table(window, trade)


def _summary_table(summary):
    if summary.empty:
        return "<p>No strategy trades found.</p>"
    headers = "".join(f"<th>{html.escape(c)}</th>" for c in summary.columns)
    rows = []
    for _, row in summary.iterrows():
        rows.append("<tr>" + "".join(f"<td>{html.escape(_fmt(row[c]))}</td>" for c in summary.columns) + "</tr>")
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def build_html():
    sections = []
    summaries = []
    for timeframe in ["5m", "10m"]:
        data, trades = _strategy_trades_for_tf(timeframe)
        sections.append(f"<h2>{timeframe.upper()} latest 10 June 2026 strategy trades</h2>")
        summary_cols = [
            "timeframe",
            "entry_time",
            "exit_time",
            "session",
            "max_filled_entries",
            "exit_reason",
            "realized_pnl_v",
            "realized_pnl_points",
            "bars_to_pullback",
            "midline_broken_before_entry",
        ]
        summaries.append(trades[summary_cols].copy())
        for num, (_, trade) in enumerate(trades.iterrows(), start=1):
            title = (
                f"{timeframe.upper()} #{num} | entry {trade['entry_time'].strftime('%Y-%m-%d %H:%M')} KST | "
                f"fills {trade['max_filled_entries']} | pnl_v {trade['realized_pnl_v']:.3f} | {trade['exit_reason']}"
            )
            sections.append(_chart_for_trade(data, trade, f"{timeframe}-trade-{num}", title))

    summary = pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame()
    css = """
body { font-family: Arial, sans-serif; margin: 24px; background: #f5f6f7; color: #1b1f23; }
h1 { margin-bottom: 4px; }
h2 { margin-top: 36px; border-top: 1px solid #d8dee4; padding-top: 24px; }
.note { color: #57606a; margin-bottom: 24px; }
.chart-card { background: #fff; border: 1px solid #d8dee4; border-radius: 8px; padding: 14px; margin: 16px 0 8px; }
.chart-card h3 { margin: 0 0 8px; font-size: 15px; }
svg { width: 100%; height: auto; background: #ffffff; }
.plot-bg { fill: #fbfbfc; stroke: #d0d7de; }
.grid { stroke: #eaeef2; stroke-width: 1; }
.axis-label, .time-label { fill: #57606a; font-size: 11px; }
.wick { stroke-width: 1.2; }
.candle.up { fill: #16833a; stroke: #16833a; }
.wick.up { stroke: #16833a; }
.candle.down { fill: #c62828; stroke: #c62828; }
.wick.down { stroke: #c62828; }
.bb20-upper, .bb20-lower { fill: none; stroke: #2563eb; stroke-width: 1.5; }
.bb20-mid { fill: none; stroke: #1d4ed8; stroke-width: 1.2; stroke-dasharray: 5 4; }
.bb44-upper, .bb44-lower { fill: none; stroke: #f59e0b; stroke-width: 1.5; }
.bb44-mid { fill: none; stroke: #b45309; stroke-width: 1.1; stroke-dasharray: 4 4; }
.marker-line { stroke-width: 1.2; stroke-dasharray: 3 3; }
.marker-line.breakout, .marker.breakout { stroke: #7c3aed; fill: #7c3aed; }
.marker-line.pullback, .marker.pullback { stroke: #0891b2; fill: #0891b2; }
.marker-line.entry, .marker.entry { stroke: #dc2626; fill: #dc2626; }
.marker-line.entry2, .marker.entry2 { stroke: #f97316; fill: #f97316; }
.marker-line.entry3, .marker.entry3 { stroke: #ea580c; fill: #ea580c; }
.marker-line.exit, .marker.exit { stroke: #111827; fill: #111827; }
.marker-text { fill: #111827; font-weight: 700; font-size: 12px; }
table { border-collapse: collapse; width: 100%; background: #fff; margin: 8px 0 18px; font-size: 12px; }
th, td { border: 1px solid #d8dee4; padding: 5px 7px; text-align: right; white-space: nowrap; }
th { background: #f0f3f6; }
td:nth-child(1), td:nth-child(2), th:nth-child(1), th:nth-child(2) { text-align: left; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; margin: 12px 0 20px; font-size: 13px; }
.swatch { display: inline-block; width: 18px; height: 3px; vertical-align: middle; margin-right: 5px; }
"""
    legend = """
<div class="legend">
  <span><i class="swatch" style="background:#2563eb"></i>BB20/2 close</span>
  <span><i class="swatch" style="background:#f59e0b"></i>BB4/4 open</span>
  <span>B = breakout, P = pullback, E1/E2/E3 = grid fills, X = exit candle</span>
</div>
"""
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>June 2026 Strategy Verification Charts</title>
<style>{css}</style>
</head>
<body>
<h1>June 2026 Strategy Verification Charts</h1>
<p class="note">XAUUSD, KST. Latest available June 2026 strategy trades per timeframe, up to 10 rows. Baseline: within_6_bars, {V_METHOD}, max_entries={MAX_ENTRIES}, exit_model={EXIT_MODEL}, max_holding_bars={MAX_HOLDING_BARS}. Data ends at 2026-06-16 09:00 KST.</p>
{legend}
<h2>Summary</h2>
{_summary_table(summary)}
{''.join(sections)}
</body>
</html>
"""
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html_text, encoding="utf-8")
    return OUTPUT_FILE, summary


if __name__ == "__main__":
    output, summary_df = build_html()
    print("Wrote HTML:", output)
    print("Rows:", len(summary_df))
