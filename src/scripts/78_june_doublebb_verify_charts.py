# -*- coding: utf-8 -*-
"""Create June 2026 double-BB verification charts.

The output is a static HTML file for TradingView cross-checks:
- XAUUSD 5m and 10m
- latest 10 June 2026 buy breakout double-BB events per timeframe
- candles, BB20/2 close bands, BB4/4 open bands, breakout/pullback/entry markers
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gold_data_prep as prep  # noqa: E402


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RESULT_DIR = Path(__file__).resolve().parents[2] / "result"
OUTPUT_FILE = RESULT_DIR / "june_doublebb_verify_charts.html"

JUNE_START = pd.Timestamp("2026-06-01 00:00", tz=prep.KST)
JUNE_END = pd.Timestamp("2026-07-01 00:00", tz=prep.KST)


def _fmt(value, digits=3):
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _scale(value, ymin, ymax, height, top_pad=18, bottom_pad=24):
    usable = height - top_pad - bottom_pad
    if ymax <= ymin:
        return top_pad + usable / 2
    return top_pad + (ymax - value) / (ymax - ymin) * usable


def _polyline(points, cls):
    clean = [(x, y) for x, y in points if pd.notna(y)]
    if len(clean) < 2:
        return ""
    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in clean)
    return f'<polyline class="{cls}" points="{pts}" />'


def _svg_chart(df, chart_id, title, markers):
    width = 1120
    height = 420
    left = 54
    right = 18
    top = 24
    bottom = 42
    plot_w = width - left - right
    n = len(df)
    candle_gap = plot_w / max(n, 1)
    body_w = max(2.0, min(8.0, candle_gap * 0.62))

    price_cols = [
        "high",
        "low",
        "bb20_2_upper_close",
        "bb20_2_mid_close",
        "bb20_2_lower_close",
        "bb4_4_upper_open",
        "bb4_4_mid_open",
        "bb4_4_lower_open",
    ]
    ymin = float(df[price_cols].min(skipna=True).min())
    ymax = float(df[price_cols].max(skipna=True).max())
    pad = (ymax - ymin) * 0.06 if ymax > ymin else 1.0
    ymin -= pad
    ymax += pad

    parts = [
        f'<section class="chart-card" id="{html.escape(chart_id)}">',
        f"<h3>{html.escape(title)}</h3>",
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
        f'<rect class="plot-bg" x="{left}" y="{top}" width="{plot_w}" height="{height - top - bottom}" />',
    ]

    for i in range(5):
        price = ymin + (ymax - ymin) * i / 4
        y = _scale(price, ymin, ymax, height, top, bottom)
        parts.append(f'<line class="grid" x1="{left}" x2="{width-right}" y1="{y:.2f}" y2="{y:.2f}" />')
        parts.append(f'<text class="axis-label" x="8" y="{y+4:.2f}">{price:.2f}</text>')

    xs = [left + candle_gap * (i + 0.5) for i in range(n)]
    for i, (_, row) in enumerate(df.iterrows()):
        x = xs[i]
        yo = _scale(float(row["open"]), ymin, ymax, height, top, bottom)
        yh = _scale(float(row["high"]), ymin, ymax, height, top, bottom)
        yl = _scale(float(row["low"]), ymin, ymax, height, top, bottom)
        yc = _scale(float(row["close"]), ymin, ymax, height, top, bottom)
        cls = "up" if row["close"] >= row["open"] else "down"
        body_y = min(yo, yc)
        body_h = max(1.0, abs(yc - yo))
        parts.append(f'<line class="wick {cls}" x1="{x:.2f}" x2="{x:.2f}" y1="{yh:.2f}" y2="{yl:.2f}" />')
        parts.append(
            f'<rect class="candle {cls}" x="{x - body_w / 2:.2f}" y="{body_y:.2f}" '
            f'width="{body_w:.2f}" height="{body_h:.2f}" />'
        )

    line_specs = [
        ("bb20_2_upper_close", "bb20 upper"),
        ("bb20_2_mid_close", "bb20 mid"),
        ("bb20_2_lower_close", "bb20 lower"),
        ("bb4_4_upper_open", "bb44 upper"),
        ("bb4_4_mid_open", "bb44 mid"),
        ("bb4_4_lower_open", "bb44 lower"),
    ]
    for col, cls in line_specs:
        pts = [(xs[i], _scale(float(v), ymin, ymax, height, top, bottom) if pd.notna(v) else pd.NA) for i, v in enumerate(df[col])]
        parts.append(_polyline(pts, cls.replace(" ", "-")))

    time_to_x = {ts: xs[i] for i, ts in enumerate(df.index)}
    for label, ts, price, cls in markers:
        if ts not in time_to_x or pd.isna(price):
            continue
        x = time_to_x[ts]
        y = _scale(float(price), ymin, ymax, height, top, bottom)
        parts.append(f'<line class="marker-line {cls}" x1="{x:.2f}" x2="{x:.2f}" y1="{top}" y2="{height-bottom}" />')
        parts.append(f'<circle class="marker {cls}" cx="{x:.2f}" cy="{y:.2f}" r="5" />')
        parts.append(f'<text class="marker-text" x="{x+7:.2f}" y="{y-7:.2f}">{html.escape(label)}</text>')

    tick_positions = [0, max(0, n // 2), max(0, n - 1)]
    for pos in sorted(set(tick_positions)):
        ts = df.index[pos]
        parts.append(f'<text class="time-label" x="{xs[pos]-34:.2f}" y="{height-12}">{ts.strftime("%m-%d %H:%M")}</text>')

    parts.append("</svg>")
    parts.append("</section>")
    return "\n".join(parts)


def _detail_table(window, item):
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
    keep_times = [item["breakout_time"]]
    if pd.notna(item.get("pullback_touch_time")):
        keep_times.append(item["pullback_touch_time"])
    if pd.notna(item.get("entry_time")):
        keep_times.append(item["entry_time"])
    rows = window.loc[window.index.isin(keep_times), cols].copy()
    rows.insert(0, "datetime_kst", rows.index.strftime("%Y-%m-%d %H:%M"))
    rows.insert(1, "event", "")
    rows.loc[rows.index == item["breakout_time"], "event"] = "breakout"
    if pd.notna(item.get("pullback_touch_time")):
        rows.loc[rows.index == item["pullback_touch_time"], "event"] = "pullback_touch"
    if pd.notna(item.get("entry_time")):
        rows.loc[rows.index == item["entry_time"], "event"] = "entry"

    headers = "".join(f"<th>{html.escape(c)}</th>" for c in rows.columns)
    body = []
    for _, row in rows.iterrows():
        body.append("<tr>" + "".join(f"<td>{html.escape(_fmt(row[c]))}</td>" for c in rows.columns) + "</tr>")
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _candidate_charts_for_tf(timeframe):
    csv_path = DATA_DIR / f"xauusd_{timeframe}_2010-01-01_2026-06-16.csv"
    data = prep.load_gold_data(csv_path, timeframe=timeframe)
    data = prep.assign_session(data)
    data = prep.add_bollinger_bands(data)
    data = prep.detect_buy_breakout_double_bb(data)
    event_times = data.index[
        (data["buy_breakout_double_bb"])
        & (data.index >= JUNE_START)
        & (data.index < JUNE_END)
    ][-10:]

    charts = []
    summary_rows = []
    idx = data.index
    for num, breakout_time in enumerate(event_times, start=1):
        breakout_pos = data.index.searchsorted(breakout_time)
        pullback_time = pd.NaT
        entry_time = pd.NaT
        entry_price = pd.NA
        bars_to_pullback = pd.NA
        midline_broken = False

        search_end = min(len(data) - 2, breakout_pos + 6)
        for pos in range(breakout_pos + 1, search_end + 1):
            lower = data.iloc[pos]["bb4_4_lower_open"]
            if pd.notna(lower) and data.iloc[pos]["low"] < lower:
                pullback_time = idx[pos]
                entry_time = idx[pos + 1]
                entry_price = data.iloc[pos + 1]["open"]
                bars_to_pullback = pos - breakout_pos
                mid_window = data.iloc[breakout_pos + 1:pos + 2]
                midline_broken = bool((mid_window["close"] < mid_window["bb20_2_mid_close"]).fillna(False).any())
                break

        entry_pos = data.index.searchsorted(entry_time) if pd.notna(entry_time) else breakout_pos
        start_pos = max(0, breakout_pos - 30)
        end_pos = min(len(data) - 1, entry_pos + 60)
        window = data.iloc[start_pos:end_pos + 1].copy()

        markers = [("B", breakout_time, data.loc[breakout_time, "close"], "breakout")]
        if pd.notna(pullback_time):
            markers.append(("P", pullback_time, data.loc[pullback_time, "low"], "pullback"))
        if pd.notna(entry_time):
            markers.append(("E", entry_time, entry_price, "entry"))
        item = {
            "breakout_time": breakout_time,
            "pullback_touch_time": pullback_time,
            "entry_time": entry_time,
            "entry_price": entry_price,
        }
        title = (
            f"{timeframe.upper()} #{num} | breakout {breakout_time.strftime('%Y-%m-%d %H:%M')} KST | "
            f"session {data.loc[breakout_time, 'session']} | within6_pullback {pd.notna(pullback_time)} | "
            f"bars {bars_to_pullback}"
        )
        charts.append(_svg_chart(window, f"{timeframe}-{num}", title, markers))
        charts.append(_detail_table(window, item))
        summary_rows.append({
            "tf": timeframe,
            "no": num,
            "breakout_time": breakout_time,
            "breakout_close": data.loc[breakout_time, "close"],
            "pullback_touch_time": pullback_time,
            "entry_time": entry_time,
            "entry_price": entry_price,
            "session": data.loc[breakout_time, "session"],
            "bars_to_pullback": bars_to_pullback,
            "midline_broken_before_entry": midline_broken,
        })
    return charts, pd.DataFrame(summary_rows)


def _summary_table(summary):
    if summary.empty:
        return "<p>No June candidates found.</p>"
    headers = "".join(f"<th>{html.escape(c)}</th>" for c in summary.columns)
    rows = []
    for _, row in summary.iterrows():
        rows.append("<tr>" + "".join(f"<td>{html.escape(_fmt(row[c]))}</td>" for c in summary.columns) + "</tr>")
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def build_html():
    all_charts = []
    summaries = []
    for timeframe in ["5m", "10m"]:
        charts, summary = _candidate_charts_for_tf(timeframe)
        all_charts.extend([f"<h2>{timeframe.upper()} latest 10 June 2026 candidates</h2>"] + charts)
        summaries.append(summary)

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
  <span>B = breakout close, P = pullback low, E = next open entry</span>
</div>
"""
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>June 2026 Latest Double-BB Verification Charts</title>
<style>{css}</style>
</head>
<body>
<h1>June 2026 Latest Double-BB Verification Charts</h1>
<p class="note">XAUUSD, KST 기준. 각 타임프레임별 2026년 6월 매수 돌파더블비 이벤트 중 가장 최신 10개입니다. 데이터는 2026-06-16까지이며, 6봉 이내 눌림이 있으면 P/E 마커를 함께 표시합니다.</p>
{legend}
<h2>Summary</h2>
{_summary_table(summary)}
{''.join(all_charts)}
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
