# -*- coding: utf-8 -*-
"""76 - Per-trade 2026 charts for the 5m SMA cross ladder strategy.

Run from data/:
  python ../src/scripts/76_sma_cross_ladder_2026_charts.py
"""
import csv
import importlib.util
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
MOD74 = os.path.join(BASE, "74_sma_cross_ladder.py")
spec = importlib.util.spec_from_file_location("ladder74", MOD74)
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

TRADES_FILE = "sma_cross_ladder_2026_trades.csv"
REPORT_FILE = os.path.join("..", "result", "sma_cross_ladder_2026_trade_charts.html")
YEAR = "2026"
BEFORE_BARS = 36
AFTER_BARS = 24


def kst(epoch):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(epoch + 9 * 3600))


def kst_year(epoch):
    return time.strftime("%Y", time.gmtime(epoch + 9 * 3600))


def parse_kst(text):
    dt = time.strptime(text, "%Y-%m-%d %H:%M")
    return int(time.mktime(dt)) - 9 * 3600


def esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def load_trades(path):
    with open(path, encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def polyline(points, color, width=2):
    if not points:
        return ""
    return '<polyline fill="none" stroke="%s" stroke-width="%s" points="%s"/>' % (
        color, width, " ".join(points)
    )


def marker_line_svg(values, sma20, sma120, markers, levels, width=980, height=280):
    all_values = [v for v in values if v is not None]
    all_values += [v for v in sma20 if v is not None]
    all_values += [v for v in sma120 if v is not None]
    all_values += [float(x["price"]) for x in levels]
    if not all_values:
        all_values = [0.0, 1.0]
    vmin = min(all_values)
    vmax = max(all_values)
    if vmax == vmin:
        vmax = vmin + 1.0
    pad_l = 54.0
    pad_r = 16.0
    pad_t = 12.0
    pad_b = 24.0
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_t - pad_b

    def x_at(idx):
        return pad_l + inner_w * idx / max(1, len(values) - 1)

    def y_at(value):
        return pad_t + inner_h * (1.0 - (value - vmin) / (vmax - vmin))

    price_pts = ["%.1f,%.1f" % (x_at(i), y_at(v)) for i, v in enumerate(values)]
    sma20_pts = ["%.1f,%.1f" % (x_at(i), y_at(v)) for i, v in enumerate(sma20) if v is not None]
    sma120_pts = ["%.1f,%.1f" % (x_at(i), y_at(v)) for i, v in enumerate(sma120) if v is not None]
    parts = [
        '<svg viewBox="0 0 %d %d" role="img" aria-label="trade chart">' % (width, height),
        '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (width, height),
        '<text x="8" y="18" font-size="11" fill="#667085">%.2f</text>' % vmax,
        '<text x="8" y="%d" font-size="11" fill="#667085">%.2f</text>' % (height - 8, vmin),
        polyline(price_pts, "#172033", 2),
        polyline(sma20_pts, "#1f5eff", 1.5),
        polyline(sma120_pts, "#b7791f", 1.5),
    ]
    for level in levels:
        y = y_at(float(level["price"]))
        color = level["color"]
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1" stroke-dasharray="4 4"/>' % (pad_l, y, width - pad_r, y, color))
        parts.append('<text x="%.1f" y="%.1f" font-size="11" fill="%s">%s</text>' % (width - pad_r - 70, y - 3, color, esc(level["label"])))
    for marker in markers:
        idx = marker["idx"]
        if idx < 0 or idx >= len(values):
            continue
        x = x_at(idx)
        color = marker["color"]
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1.5"/>' % (x, pad_t, x, height - pad_b, color))
        parts.append('<text x="%.1f" y="%.1f" font-size="11" fill="%s" transform="rotate(-90 %.1f %.1f)">%s</text>' % (x - 4, height - 34, color, x - 4, height - 34, esc(marker["label"])))
    parts.append("</svg>")
    return "".join(parts)


def build_trade_chart(trade, bars, index_by_epoch, sma20, sma120):
    entry_epoch = parse_kst(trade["entry_kst"])
    exit_epoch = parse_kst(trade["exit_kst"])
    entry_i = index_by_epoch.get(entry_epoch)
    exit_i = index_by_epoch.get(exit_epoch)
    if entry_i is None or exit_i is None:
        return "<p>chart unavailable</p>"
    start = max(0, entry_i - BEFORE_BARS)
    end = min(len(bars), max(exit_i + AFTER_BARS + 1, entry_i + BEFORE_BARS + 1))
    window = bars[start:end]
    values = [b.close for b in window]
    markers = [
        {"idx": entry_i - start, "label": "ENTRY", "color": "#0f8f63"},
        {"idx": exit_i - start, "label": "EXIT", "color": "#c2410c"},
    ]
    direction = 1 if trade["direction"] == "LONG" else -1
    first = float(trade["first_entry"])
    avg = float(trade["avg_price"])
    legs = int(trade["legs"])
    levels = [
        {"price": avg, "label": "AVG", "color": "#344054"},
        {"price": float(trade["exit_price"]), "label": "EXIT", "color": "#c2410c"},
        {"price": L.hard_stop_price(first, direction, L.STEP_POINTS, L.MAX_LEGS), "label": "STOP6", "color": "#7f1d1d"},
    ]
    for n in range(legs):
        level = first - direction * L.STEP_POINTS * n
        levels.append({"price": level, "label": "L%d" % (n + 1), "color": "#6941c6"})
    return marker_line_svg(values, sma20[start:end], sma120[start:end], markers, levels)


def write_report(path, trades, bars):
    closes = [b.close for b in bars]
    sma20 = L.sma(closes, L.FAST)
    sma120 = L.sma(closes, L.SLOW)
    index_by_epoch = {b.epoch: i for i, b in enumerate(bars)}
    cards = []
    for i, trade in enumerate(trades, 1):
        chart = build_trade_chart(trade, bars, index_by_epoch, sma20, sma120)
        cards.append(
            '<section class="trade"><h2>#%03d %s %s legs=%s net=%s hold=%s</h2>'
            '<div class="meta">entry %s / exit %s / avg %s / exit reason %s</div>'
            '<div class="chart">%s</div></section>' % (
                i, esc(trade["direction"]), esc(trade["entry_kst"]), esc(trade["legs"]),
                esc(trade["net_points"]), esc(trade["hold_text"]), esc(trade["entry_kst"]),
                esc(trade["exit_kst"]), esc(trade["avg_price"]), esc(trade["exit_reason"]), chart
            )
        )
    html = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>2026 SMA Cross Ladder Trade Charts</title>
<style>
body{font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;margin:24px;background:#f7f8fa;color:#172033}
h1{font-size:26px}.note{background:#eef4ff;border-left:4px solid #1f5eff;padding:10px 12px;border-radius:6px}
.trade{background:white;border:1px solid #d8dee8;border-radius:8px;margin:16px 0;padding:14px}
.trade h2{font-size:17px;margin:0 0 4px}.meta{font-size:13px;color:#667085;margin-bottom:10px}.chart{overflow-x:auto}
svg{width:100%%;min-width:880px;height:auto}
</style></head><body>
<h1>2026 SMA20/120 Cross Ladder - Entry Situation Charts</h1>
<p class="note">Each chart shows close price, SMA20(blue), SMA120(gold), entry/exit markers, average price, filled ladder levels, and 6th-zone hard stop. Window: 36 bars before entry and at least 24 bars after exit.</p>
%s
</body></html>""" % "\n".join(cards)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(html)


def main():
    print("2026 trade chart report | XAUUSD 5m")
    bars = [b for b in L.load_bars(L.DATA_FILE) if kst_year(b.epoch) == YEAR]
    trades = load_trades(TRADES_FILE)
    write_report(REPORT_FILE, trades, bars)
    print("trades=%d bars=%d" % (len(trades), len(bars)))
    print("WROTE %s" % REPORT_FILE)


if __name__ == "__main__":
    main()
