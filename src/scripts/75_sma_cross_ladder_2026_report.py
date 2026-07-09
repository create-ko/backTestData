# -*- coding: utf-8 -*-
"""75 - 2026-only report for the 5m SMA cross ladder strategy.

Run from data/:
  python ../src/scripts/75_sma_cross_ladder_2026_report.py
"""
import csv
import importlib.util
import json
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
MOD74 = os.path.join(BASE, "74_sma_cross_ladder.py")
spec = importlib.util.spec_from_file_location("ladder74", MOD74)
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

YEAR = "2026"
TRADES_FILE = "sma_cross_ladder_2026_trades.csv"
SUMMARY_FILE = "sma_cross_ladder_2026_summary.json"
REPORT_FILE = os.path.join("..", "result", "sma_cross_ladder_2026_report.html")


def kst_year(epoch):
    return time.strftime("%Y", time.gmtime(epoch + 9 * 3600))


def filter_bars_by_kst_year(bars, year):
    return [b for b in bars if kst_year(b.epoch) == str(year)]


def format_hold_minutes(minutes):
    days = minutes // (24 * 60)
    minutes %= 24 * 60
    hours = minutes // 60
    mins = minutes % 60
    parts = []
    if days:
        parts.append("%dd" % days)
    if hours:
        parts.append("%dh" % hours)
    if mins or not parts:
        parts.append("%dm" % mins)
    return " ".join(parts)


def month_key(kst_text):
    return kst_text[:7]


def equity_curve(trades):
    values = [0.0]
    total = 0.0
    for tr in trades:
        total += float(tr["net_points"])
        values.append(total)
    return values


def line_chart_svg(values, width=920, height=220):
    if not values:
        values = [0.0]
    vmin = min(values)
    vmax = max(values)
    if vmax == vmin:
        vmax = vmin + 1.0
    pad = 10.0
    inner_w = width - 2 * pad
    inner_h = height - 2 * pad
    points = []
    for i, value in enumerate(values):
        x = pad + (inner_w * i / max(1, len(values) - 1))
        y = pad + inner_h * (1.0 - (value - vmin) / (vmax - vmin))
        points.append("%.1f,%.1f" % (x, y))
    zero_y = pad + inner_h * (1.0 - (0.0 - vmin) / (vmax - vmin))
    return (
        '<svg viewBox="0 0 %d %d" role="img" aria-label="equity curve">'
        '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>'
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#d8dee8" stroke-width="1"/>'
        '<polyline fill="none" stroke="#1f5eff" stroke-width="2" points="%s"/>'
        '</svg>'
    ) % (width, height, width, height, pad, zero_y, width - pad, zero_y, " ".join(points))


def bar_chart_svg(rows, label_key, value_key, width=920, height=240):
    if not rows:
        return "<svg></svg>"
    max_abs = max(abs(float(r[value_key])) for r in rows)
    if max_abs == 0:
        max_abs = 1.0
    left = 56
    bottom = 34
    top = 14
    chart_h = height - top - bottom
    slot = (width - left - 12) / len(rows)
    zero = top + chart_h / 2
    parts = [
        '<svg viewBox="0 0 %d %d" role="img" aria-label="bar chart">' % (width, height),
        '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (width, height),
        '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#98a2b3" stroke-width="1"/>' % (left, zero, width - 12, zero),
    ]
    for i, row in enumerate(rows):
        value = float(row[value_key])
        x = left + i * slot + slot * 0.14
        bar_w = slot * 0.72
        bar_h = abs(value) / max_abs * (chart_h / 2 - 4)
        y = zero - bar_h if value >= 0 else zero
        color = "#0f8f63" if value >= 0 else "#c2410c"
        parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>' % (x, y, bar_w, bar_h, color))
        parts.append('<text x="%.1f" y="%d" text-anchor="middle" font-size="11" fill="#344054">%s</text>' % (x + bar_w / 2, height - 12, row[label_key][-2:]))
    parts.append("</svg>")
    return "".join(parts)


def enrich_trades(trades):
    out = []
    for tr in trades:
        row = dict(tr)
        hold_minutes = int(row["hold_bars"]) * 5
        row["hold_minutes"] = hold_minutes
        row["hold_text"] = format_hold_minutes(hold_minutes)
        row["month"] = month_key(row["entry_kst"])
        out.append(row)
    return out


def grouped_summary(trades, key):
    groups = {}
    for tr in trades:
        groups.setdefault(tr[key], []).append(tr)
    rows = []
    for name in sorted(groups):
        rows.append(dict(L.summarize(groups[name]), **{key: name}))
    return rows


def avg_hold(trades):
    if not trades:
        return "0m"
    return format_hold_minutes(int(sum(t["hold_minutes"] for t in trades) / len(trades)))


def max_hold(trades):
    if not trades:
        return "0m"
    return format_hold_minutes(max(t["hold_minutes"] for t in trades))


def write_trades(path, trades):
    fields = [
        "signal_kst", "entry_kst", "exit_kst", "month", "direction", "legs",
        "avg_price", "first_entry", "exit_price", "gross_points", "cost",
        "net_points", "points_per_leg", "hold_bars", "hold_minutes", "hold_text", "exit_reason",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as fp:
        wr = csv.DictWriter(fp, fieldnames=fields)
        wr.writeheader()
        for tr in trades:
            wr.writerow({k: tr.get(k, "") for k in fields})


def esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def summary_table(rows, key):
    cols = [key, "trades", "win_rate", "net_points", "avg_points", "pf", "mdd_points"]
    body = []
    for row in rows:
        body.append("<tr>" + "".join("<td>%s</td>" % esc(row.get(c, "")) for c in cols) + "</tr>")
    return "<table><tr>%s</tr>%s</table>" % (
        "".join("<th>%s</th>" % esc(c) for c in cols), "".join(body)
    )


def trade_table(trades):
    cols = ["entry_kst", "exit_kst", "direction", "legs", "avg_price", "exit_price", "net_points", "hold_text", "exit_reason"]
    body = []
    for tr in trades:
        body.append("<tr>" + "".join("<td>%s</td>" % esc(tr.get(c, "")) for c in cols) + "</tr>")
    return "<table><tr>%s</tr>%s</table>" % (
        "".join("<th>%s</th>" % esc(c) for c in cols), "".join(body)
    )


def write_report(path, trades, summary, monthly, by_dir, by_reason, by_legs):
    curve = equity_curve(trades)
    html = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>2026 SMA Cross Ladder Backtest</title>
<style>
body{font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;margin:24px;background:#f7f8fa;color:#172033}
h1{font-size:26px}h2{font-size:19px;margin-top:28px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.card{background:white;border:1px solid #d8dee8;border-radius:8px;padding:14px}.k{color:#667085;font-size:12px}.v{font-size:22px;font-weight:700}
.note{background:#fff9ec;border-left:4px solid #b7791f;padding:10px 12px;border-radius:6px;margin:12px 0}
table{border-collapse:collapse;background:white;font-size:13px;margin-top:8px;width:100%%}
th,td{border:1px solid #d8dee8;padding:7px;text-align:right;vertical-align:top}th{background:#eef1f6}
td:first-child,th:first-child{text-align:left}.chart{background:white;border:1px solid #d8dee8;border-radius:8px;padding:10px}
</style></head><body>
<h1>2026 5m SMA20/120 Cross Ladder Backtest</h1>
<p class="note">2026 KST bars only. No time filter. Entry is next bar open after cross. Average-price trailing starts after +10p and moves by 5p. Conservative same-bar ordering is used.</p>
<div class="grid">
<div class="card"><div class="k">Trades</div><div class="v">%s</div></div>
<div class="card"><div class="k">Win Rate</div><div class="v">%s%%</div></div>
<div class="card"><div class="k">Net Points</div><div class="v">%s</div></div>
<div class="card"><div class="k">MDD Points</div><div class="v">%s</div></div>
<div class="card"><div class="k">PF</div><div class="v">%s</div></div>
<div class="card"><div class="k">Average Hold</div><div class="v">%s</div></div>
<div class="card"><div class="k">Max Hold</div><div class="v">%s</div></div>
<div class="card"><div class="k">Avg Points</div><div class="v">%s</div></div>
</div>
<h2>누적 손익 곡선</h2><div class="chart">%s</div>
<h2>월별 순손익</h2><div class="chart">%s</div>
<h2>월별 요약</h2>%s
<h2>방향별 요약</h2>%s
<h2>청산 사유별 요약</h2>%s
<h2>진입 구간 수별 요약</h2>%s
<h2>거래별 시간표</h2>%s
</body></html>""" % (
        summary["trades"], summary["win_rate"], summary["net_points"], summary["mdd_points"],
        summary["pf"], avg_hold(trades), max_hold(trades), summary["avg_points"],
        line_chart_svg(curve), bar_chart_svg(monthly, "month", "net_points"),
        summary_table(monthly, "month"), summary_table(by_dir, "direction"),
        summary_table(by_reason, "exit_reason"), summary_table(by_legs, "legs"), trade_table(trades)
    )
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(html)


def main():
    print("2026 SMA cross ladder report | XAUUSD 5m")
    bars = filter_bars_by_kst_year(L.load_bars(L.DATA_FILE), YEAR)
    trades, meta = L.backtest(bars)
    trades = enrich_trades(trades)
    summary = L.summarize(trades)
    monthly = grouped_summary(trades, "month")
    by_dir = grouped_summary(trades, "direction")
    by_reason = grouped_summary(trades, "exit_reason")
    by_legs = grouped_summary(trades, "legs")
    out = {
        "summary": summary,
        "meta": meta,
        "average_hold": avg_hold(trades),
        "max_hold": max_hold(trades),
        "monthly": monthly,
        "by_direction": by_dir,
        "by_exit_reason": by_reason,
        "by_legs": by_legs,
    }
    write_trades(TRADES_FILE, trades)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)
    write_report(REPORT_FILE, trades, summary, monthly, by_dir, by_reason, by_legs)
    print("trades=%d win=%.2f net=%.2f avg=%.4f pf=%s mdd=%.2f avg_hold=%s max_hold=%s" % (
        summary["trades"], summary["win_rate"], summary["net_points"], summary["avg_points"],
        str(summary["pf"]), summary["mdd_points"], avg_hold(trades), max_hold(trades)
    ))
    print("WROTE %s" % TRADES_FILE)
    print("WROTE %s" % SUMMARY_FILE)
    print("WROTE %s" % REPORT_FILE)


if __name__ == "__main__":
    main()
