# -*- coding: utf-8 -*-
"""74 - 5m SMA20/120 cross ladder strategy on XAUUSD.

Run from data/:
  python ../src/scripts/74_sma_cross_ladder.py

Rules:
- 5m bars.
- Golden cross: SMA20 crosses above SMA120 -> long next bar open.
- Dead cross: SMA20 crosses below SMA120 -> short next bar open.
- If the cross bar closes on the wrong side of SMA120, skip entry.
- No time filter.
- Add one leg every adverse 10 points, up to 5 total filled legs.
- The 6th adverse zone is hard stop for all legs.
- Trailing starts from average entry after +10 points, then moves every 5 points.

Console output is ASCII-only. Files are UTF-8.
"""
import csv
import json
import math
import os
import time

DATA_FILE = "xauusd_5m_2010-01-01_2026-06-16.csv"
TRADES_FILE = "sma_cross_ladder_trades.csv"
SUMMARY_FILE = "sma_cross_ladder_summary.json"
REPORT_FILE = os.path.join("..", "result", "sma_cross_ladder_report.html")

FAST = 20
SLOW = 120
STEP_POINTS = 10.0
MAX_LEGS = 5
TRAIL_START = 10.0
TRAIL_STEP = 5.0
COST_PER_LEG_ROUNDTRIP = 0.40


class Bar:
    def __init__(self, epoch, open_, high, low, close, volume=0.0):
        self.epoch = int(epoch)
        self.open = float(open_)
        self.high = float(high)
        self.low = float(low)
        self.close = float(close)
        self.volume = float(volume)


def load_bars(path):
    bars = []
    with open(path, encoding="utf-8-sig", newline="") as fp:
        rd = csv.reader(fp)
        next(rd)
        for row in rd:
            epoch = int(float(row[0]))
            if epoch > 100000000000:
                epoch //= 1000
            vol = float(row[5]) if len(row) > 5 and row[5] != "" else 0.0
            bars.append(Bar(epoch, row[1], row[2], row[3], row[4], vol))
    return bars


def sma(values, length):
    out = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= length:
            total -= values[i - length]
        if i >= length - 1:
            out[i] = total / length
    return out


def detect_crosses(fast, slow):
    out = [None] * len(fast)
    for i in range(1, len(fast)):
        if fast[i] is None or slow[i] is None or fast[i - 1] is None or slow[i - 1] is None:
            continue
        if fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]:
            out[i] = "golden"
        elif fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]:
            out[i] = "dead"
    return out


def ladder_prices(first_entry, direction, step_points, max_legs):
    return [first_entry - direction * step_points * i for i in range(max_legs)]


def average_price(prices):
    return sum(prices) / len(prices)


def hard_stop_price(first_entry, direction, step_points, max_legs):
    return first_entry - direction * step_points * max_legs


def trailing_stop(avg_price, direction, best_price, start=TRAIL_START, step=TRAIL_STEP):
    move = (best_price - avg_price) * direction
    if move < start:
        return None
    locked = math.floor((move - start) / step) * step + step
    return avg_price + direction * locked


def kst(epoch):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(epoch + 9 * 3600))


def kyear(epoch):
    return time.strftime("%Y", time.gmtime(epoch + 9 * 3600))


def can_enter(cross, close, slow_value):
    if cross == "golden":
        return close >= slow_value
    if cross == "dead":
        return close <= slow_value
    return False


def close_trade(bars, signal_i, entry_i, exit_i, direction, fill_prices, exit_price, reason):
    gross_points = sum((exit_price - p) * direction for p in fill_prices)
    cost = COST_PER_LEG_ROUNDTRIP * len(fill_prices)
    net_points = gross_points - cost
    avg = average_price(fill_prices)
    return {
        "signal_kst": kst(bars[signal_i].epoch),
        "entry_kst": kst(bars[entry_i].epoch),
        "exit_kst": kst(bars[exit_i].epoch),
        "year": kyear(bars[entry_i].epoch),
        "direction": "LONG" if direction == 1 else "SHORT",
        "legs": len(fill_prices),
        "avg_price": avg,
        "first_entry": fill_prices[0],
        "exit_price": exit_price,
        "gross_points": gross_points,
        "cost": cost,
        "net_points": net_points,
        "points_per_leg": net_points / len(fill_prices),
        "hold_bars": exit_i - entry_i + 1,
        "exit_reason": reason,
    }


def simulate_trade(bars, signal_i, direction):
    entry_i = signal_i + 1
    if entry_i >= len(bars):
        return None, len(bars) - 1
    first_entry = bars[entry_i].open
    levels = ladder_prices(first_entry, direction, STEP_POINTS, MAX_LEGS)
    hard_stop = hard_stop_price(first_entry, direction, STEP_POINTS, MAX_LEGS)
    fill_prices = [levels[0]]
    next_leg = 1
    best_price = first_entry
    active_trail = None

    for i in range(entry_i, len(bars)):
        bar = bars[i]
        adverse = bar.low if direction == 1 else bar.high
        favorable = bar.high if direction == 1 else bar.low

        while next_leg < MAX_LEGS:
            level = levels[next_leg]
            if direction == 1 and adverse <= level:
                fill_prices.append(level)
                next_leg += 1
                continue
            if direction == -1 and adverse >= level:
                fill_prices.append(level)
                next_leg += 1
                continue
            break

        if direction == 1 and adverse <= hard_stop:
            return close_trade(bars, signal_i, entry_i, i, direction, fill_prices, hard_stop, "HARD_STOP"), i
        if direction == -1 and adverse >= hard_stop:
            return close_trade(bars, signal_i, entry_i, i, direction, fill_prices, hard_stop, "HARD_STOP"), i

        if active_trail is not None:
            if direction == 1 and bar.low <= active_trail:
                return close_trade(bars, signal_i, entry_i, i, direction, fill_prices, active_trail, "TRAIL"), i
            if direction == -1 and bar.high >= active_trail:
                return close_trade(bars, signal_i, entry_i, i, direction, fill_prices, active_trail, "TRAIL"), i

        if (favorable - best_price) * direction > 0:
            best_price = favorable
        avg = average_price(fill_prices)
        new_trail = trailing_stop(avg, direction, best_price)
        if new_trail is not None:
            if active_trail is None:
                active_trail = new_trail
            elif direction == 1 and new_trail > active_trail:
                active_trail = new_trail
            elif direction == -1 and new_trail < active_trail:
                active_trail = new_trail

    return close_trade(bars, signal_i, entry_i, len(bars) - 1, direction, fill_prices, bars[-1].close, "FINAL"), len(bars) - 1


def backtest(bars):
    closes = [b.close for b in bars]
    fast = sma(closes, FAST)
    slow = sma(closes, SLOW)
    crosses = detect_crosses(fast, slow)
    trades = []
    busy_until = -1
    skipped_wrong_side = 0
    signals = 0
    for i, cross in enumerate(crosses):
        if cross is None or i + 1 >= len(bars):
            continue
        signals += 1
        if i <= busy_until:
            continue
        if not can_enter(cross, bars[i].close, slow[i]):
            skipped_wrong_side += 1
            continue
        direction = 1 if cross == "golden" else -1
        trade, exit_i = simulate_trade(bars, i, direction)
        if trade is not None:
            trades.append(trade)
            busy_until = exit_i
    return trades, {"signals": signals, "skipped_wrong_side": skipped_wrong_side}


def profit_factor(values):
    gp = sum(x for x in values if x > 0)
    gl = sum(-x for x in values if x < 0)
    if gl == 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def max_drawdown(values):
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for value in values:
        eq += value
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > mdd:
            mdd = dd
    return mdd


def summarize(trades):
    vals = [t["net_points"] for t in trades]
    wins = sum(1 for v in vals if v > 0)
    pf = profit_factor(vals)
    return {
        "trades": len(trades),
        "win_rate": round(100.0 * wins / len(vals), 2) if vals else 0.0,
        "net_points": round(sum(vals), 3),
        "avg_points": round(sum(vals) / len(vals), 4) if vals else 0.0,
        "pf": "inf" if pf == float("inf") else round(pf, 3),
        "mdd_points": round(max_drawdown(vals), 3),
    }


def grouped_summary(trades, key):
    out = {}
    for tr in trades:
        out.setdefault(tr[key], []).append(tr)
    rows = []
    for k in sorted(out):
        row = summarize(out[k])
        row[key] = k
        rows.append(row)
    return rows


def write_trades(path, trades):
    fields = [
        "signal_kst", "entry_kst", "exit_kst", "year", "direction", "legs",
        "avg_price", "first_entry", "exit_price", "gross_points", "cost",
        "net_points", "points_per_leg", "hold_bars", "exit_reason",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as fp:
        wr = csv.DictWriter(fp, fieldnames=fields)
        wr.writeheader()
        for tr in trades:
            wr.writerow({k: tr[k] for k in fields})


def esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table(rows, first_key):
    if not rows:
        return "<p>No rows.</p>"
    cols = [first_key, "trades", "win_rate", "net_points", "avg_points", "pf", "mdd_points"]
    head = "".join("<th>%s</th>" % esc(c) for c in cols)
    body = []
    for row in rows:
        body.append("<tr>" + "".join("<td>%s</td>" % esc(row.get(c, "")) for c in cols) + "</tr>")
    return "<table><tr>%s</tr>%s</table>" % (head, "".join(body))


def write_report(path, summary, yearly, by_dir, by_reason, by_legs, meta):
    html = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>SMA Cross Ladder Backtest</title>
<style>
body{font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;margin:24px;background:#f7f8fa;color:#172033}
h1{font-size:26px}h2{font-size:19px;margin-top:28px}
.note{background:#eef4ff;border-left:4px solid #1f5eff;padding:10px 12px;border-radius:6px}
table{border-collapse:collapse;background:white;font-size:13px;margin-top:8px}
th,td{border:1px solid #d8dee8;padding:7px;text-align:right}th{background:#eef1f6}
td:first-child,th:first-child{text-align:left}
</style></head><body>
<h1>5m SMA20/120 Cross Ladder Backtest</h1>
<p class="note">No time filter. Entry is next bar open after cross. Ladder step=10 points, max legs=5, hard stop at 6th zone. Trailing starts from average price after +10 points and moves every 5 points. Same-bar ordering is conservative.</p>
<h2>Summary</h2>
<table><tr><th>signals</th><th>skipped wrong side</th><th>trades</th><th>win%%</th><th>net points</th><th>avg points</th><th>PF</th><th>MDD points</th></tr>
<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr></table>
<h2>By Year</h2>%s
<h2>By Direction</h2>%s
<h2>By Exit Reason</h2>%s
<h2>By Filled Legs</h2>%s
</body></html>""" % (
        meta["signals"], meta["skipped_wrong_side"], summary["trades"], summary["win_rate"],
        summary["net_points"], summary["avg_points"], summary["pf"], summary["mdd_points"],
        table(yearly, "year"), table(by_dir, "direction"), table(by_reason, "exit_reason"), table(by_legs, "legs")
    )
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(html)


def main():
    print("SMA cross ladder | XAUUSD 5m | no time filter")
    bars = load_bars(DATA_FILE)
    trades, meta = backtest(bars)
    summary = summarize(trades)
    yearly = grouped_summary(trades, "year")
    by_dir = grouped_summary(trades, "direction")
    by_reason = grouped_summary(trades, "exit_reason")
    by_legs = grouped_summary(trades, "legs")
    out = {
        "summary": summary,
        "meta": meta,
        "yearly": yearly,
        "by_direction": by_dir,
        "by_exit_reason": by_reason,
        "by_legs": by_legs,
        "assumptions": {
            "entry": "next bar open after SMA20/120 cross",
            "ladder_step_points": STEP_POINTS,
            "max_legs": MAX_LEGS,
            "hard_stop_zone": 6,
            "trail_start_points_from_average": TRAIL_START,
            "trail_step_points": TRAIL_STEP,
            "cost_per_leg_roundtrip": COST_PER_LEG_ROUNDTRIP,
            "same_bar_order": "adverse ladder/hard stop, existing trail, then update new trail",
        },
    }
    write_trades(TRADES_FILE, trades)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)
    write_report(REPORT_FILE, summary, yearly, by_dir, by_reason, by_legs, meta)
    print("signals=%d skipped=%d trades=%d win=%.2f net=%.2f avg=%.4f pf=%s mdd=%.2f" % (
        meta["signals"], meta["skipped_wrong_side"], summary["trades"], summary["win_rate"],
        summary["net_points"], summary["avg_points"], str(summary["pf"]), summary["mdd_points"]
    ))
    print("WROTE %s" % TRADES_FILE)
    print("WROTE %s" % SUMMARY_FILE)
    print("WROTE %s" % REPORT_FILE)


if __name__ == "__main__":
    main()
