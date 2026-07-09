# -*- coding: utf-8 -*-
"""73 - XAUUSD session KTR first-pass backtest.

Run from data/:
  python ../src/scripts/73_xauusd_session_ktr.py

Console output is ASCII-only. Output CSV/JSON/HTML files are UTF-8.
"""
import bisect
import csv
import json
import math
import os
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

DATA_FILE = "xauusd_10m_2010-01-01_2026-06-16.csv"
TRADES_FILE = "session_ktr_trades.csv"
SUMMARY_FILE = "session_ktr_summary.json"
REPORT_FILE = os.path.join("..", "result", "session_ktr_backtest_report.html")

KST = timezone(timedelta(hours=9))
BAR_SECONDS = 600
OBS_SECONDS = 3600
SMA_LEN = 20
BASE_COST = 0.40
STOP_MULTS = [1.0, 1.5]
TP_RS = [1.0, 1.5, 2.0]
MODELS = ["A", "B"]
EXIT_MODES = ["normal", "forced_session_close"]


class Bar:
    def __init__(self, epoch, open_, high, low, close, volume=0.0):
        self.epoch = int(epoch)
        self.open = float(open_)
        self.high = float(high)
        self.low = float(low)
        self.close = float(close)
        self.volume = float(volume)


class Session:
    def __init__(self, sid, name, reset_epoch, next_reset_epoch):
        self.sid = sid
        self.name = name
        self.reset_epoch = reset_epoch
        self.observe_end_epoch = reset_epoch + OBS_SECONDS
        self.next_reset_epoch = next_reset_epoch


def load_bars(path):
    out = []
    with open(path, encoding="utf-8-sig", newline="") as fp:
        rd = csv.reader(fp)
        next(rd)
        for row in rd:
            epoch = int(float(row[0]))
            if epoch > 100000000000:
                epoch //= 1000
            vol = float(row[5]) if len(row) > 5 and row[5] != "" else 0.0
            out.append(Bar(epoch, row[1], row[2], row[3], row[4], vol))
    return out


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


def kst_dt(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(KST)


def kst_date(epoch):
    return kst_dt(epoch).date()


def kst_hm(epoch):
    dt = kst_dt(epoch)
    return dt.hour, dt.minute


def fmt_kst(epoch):
    return kst_dt(epoch).strftime("%Y-%m-%d %H:%M")


def local_reset_to_kst_epoch(year, month, day, tz_name, hour, minute):
    local = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz_name))
    return int(local.astimezone(timezone.utc).timestamp())


def kst_fixed_epoch(day, hour, minute):
    dt = datetime.combine(day, dtime(hour, minute), tzinfo=KST)
    return int(dt.astimezone(timezone.utc).timestamp())


def daterange(start_day, end_day):
    cur = start_day
    while cur <= end_day:
        yield cur
        cur += timedelta(days=1)


def build_session_resets(first_epoch, last_epoch):
    start_day = kst_date(first_epoch) - timedelta(days=2)
    end_day = kst_date(last_epoch) + timedelta(days=2)
    resets = []
    for day in daterange(start_day, end_day):
        resets.append(("Asia", kst_fixed_epoch(day, 8, 0)))
        resets.append(("Europe", local_reset_to_kst_epoch(day.year, day.month, day.day, "Europe/London", 8, 0)))
        resets.append(("NewYork", local_reset_to_kst_epoch(day.year, day.month, day.day, "America/New_York", 9, 30)))
    resets = sorted(set((epoch, name) for name, epoch in resets))
    sessions = []
    sid = 0
    for i in range(len(resets) - 1):
        epoch, name = resets[i]
        next_epoch = resets[i + 1][0]
        if epoch < first_epoch or epoch + OBS_SECONDS >= last_epoch:
            continue
        sid += 1
        sessions.append(Session(sid, name, epoch, next_epoch))
    return sessions


def compute_daily_ranges(bars):
    by_day = {}
    last_close = {}
    for bar in bars:
        day = kst_date(bar.epoch)
        item = by_day.setdefault(day, {"high": bar.high, "low": bar.low})
        if bar.high > item["high"]:
            item["high"] = bar.high
        if bar.low < item["low"]:
            item["low"] = bar.low
        last_close[day] = bar.close
    days = sorted(by_day)
    ranges = {day: by_day[day]["high"] - by_day[day]["low"] for day in days}
    prev_close = {}
    prev = None
    for day in days:
        prev_close[day] = prev
        prev = last_close[day]
    return days, ranges, prev_close


def recent_10_ranges(day, days, ranges):
    prior = [d for d in days if d < day and d.weekday() < 5]
    selected = prior[-10:]
    if len(selected) < 10:
        return None
    return [ranges[d] for d in selected]


def compute_asia_ktr(open_high, open_low, prev_close, recent_ranges):
    raw = max(open_high, prev_close) - min(open_low, prev_close)
    avg10 = sum(recent_ranges) / len(recent_ranges)
    effective = min(raw, 0.25 * avg10)
    return raw, avg10, effective


def observation_bars(bars, epochs, start_epoch):
    i = bisect.bisect_left(epochs, start_epoch)
    obs = []
    end = start_epoch + OBS_SECONDS
    while i < len(bars) and bars[i].epoch < end:
        obs.append(bars[i])
        i += 1
    if len(obs) != 6:
        return None
    if obs[0].epoch != start_epoch or obs[-1].epoch != start_epoch + 5 * BAR_SECONDS:
        return None
    return obs


def range_of(bars):
    return max(b.high for b in bars) - min(b.low for b in bars)


def hourly_sma20_at(bar_by_epoch, end_epoch):
    closes = []
    for n in range(SMA_LEN):
        close_epoch = end_epoch - BAR_SECONDS - n * OBS_SECONDS
        bar = bar_by_epoch.get(close_epoch)
        if bar is None:
            return None
        closes.append(bar.close)
    return sum(closes) / len(closes)


def session_ktr(session, obs, daily_days, daily_ranges, prev_closes):
    if session.name != "Asia":
        raw = range_of(obs)
        return raw, raw, None, False
    day = kst_date(session.reset_epoch)
    prev_close = prev_closes.get(day)
    recent = recent_10_ranges(day, daily_days, daily_ranges)
    if prev_close is None or recent is None:
        return None, None, None, False
    raw, avg10, effective = compute_asia_ktr(obs[0].high, obs[0].low, prev_close, recent)
    return raw, effective, avg10, effective < raw


def model_a_bias(obs, sma20):
    first = obs[0]
    last = obs[-1]
    if sma20 is None:
        return 0
    if last.close > first.open and last.close > sma20:
        return 1
    if last.close < first.open and last.close < sma20:
        return -1
    return 0


def trigger_direction(model, session, obs, bars, epochs, sma20_10m, start_i, end_i, bias_a):
    if model == "A":
        return bias_a, start_i
    box_high = max(b.high for b in obs)
    box_low = min(b.low for b in obs)
    for i in range(start_i, end_i):
        if bars[i].close > box_high:
            return 1, i + 1
        if bars[i].close < box_low:
            return -1, i + 1
    return 0, end_i


def find_entry(bars, sma20_10m, direction, start_i, end_i):
    for i in range(start_i, end_i - 1):
        ma = sma20_10m[i]
        if ma is None:
            continue
        if direction == 1 and bars[i].low <= ma and bars[i].close > ma:
            return i + 1
        if direction == -1 and bars[i].high >= ma and bars[i].close < ma:
            return i + 1
    return None


def resolve_exit(bars, entry_i, direction, stop, tp, force_exit_epoch=None):
    for i in range(entry_i, len(bars)):
        bar = bars[i]
        if force_exit_epoch is not None and bar.epoch >= force_exit_epoch:
            return i, bar.open, "FORCED_SESSION_CLOSE"
        if direction == 1:
            if bar.low <= stop:
                return i, stop, "SL"
            if bar.high >= tp:
                return i, tp, "TP"
        else:
            if bar.high >= stop:
                return i, stop, "SL"
            if bar.low <= tp:
                return i, tp, "TP"
    return len(bars) - 1, bars[-1].close, "FINAL"


def profit_factor(values):
    gp = sum(x for x in values if x > 0)
    gl = sum(-x for x in values if x < 0)
    if gl == 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def max_drawdown(values):
    peak = 0.0
    equity = 0.0
    mdd = 0.0
    for value in values:
        equity += value
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > mdd:
            mdd = dd
    return mdd


def summarize(trades):
    rs = [t["r_net"] for t in trades]
    wins = sum(1 for x in rs if x > 0)
    days = sorted(set(t["entry_day"] for t in trades))
    pf = profit_factor(rs)
    return {
        "trades": len(trades),
        "days": len(days),
        "trades_per_day": round(float(len(trades)) / len(days), 3) if days else 0.0,
        "win_rate": round(100.0 * wins / len(rs), 2) if rs else 0.0,
        "total_r": round(sum(rs), 3),
        "avg_r": round(sum(rs) / len(rs), 4) if rs else 0.0,
        "pf": "inf" if pf == float("inf") else round(pf, 3),
        "mdd_r": round(max_drawdown(rs), 3),
        "net_points": round(sum(t["net_points"] for t in trades), 3),
    }


def group_count(trades, key):
    out = {}
    for tr in trades:
        out[tr[key]] = out.get(tr[key], 0) + 1
    return out


def yearly_summary(trades):
    by = {}
    for tr in trades:
        by.setdefault(tr["year"], []).append(tr)
    rows = []
    for year in sorted(by):
        sm = summarize(by[year])
        sm["year"] = year
        rows.append(sm)
    return rows


def cost_sensitivity(trades):
    rows = {}
    for cost in (0.20, 0.30, 0.40, 0.50):
        rs = []
        for tr in trades:
            r = (tr["gross_points"] - cost) / tr["risk_points"]
            rs.append(r)
        rows[str(cost)] = {
            "total_r": round(sum(rs), 3),
            "avg_r": round(sum(rs) / len(rs), 4) if rs else 0.0,
            "mdd_r": round(max_drawdown(rs), 3),
            "pf": "inf" if profit_factor(rs) == float("inf") else round(profit_factor(rs), 3),
        }
    return rows


def run_variant(bars, sessions, epochs, sma20_10m, daily_days, daily_ranges, prev_closes,
                model, stop_mult, tp_r, exit_mode):
    bar_by_epoch = {b.epoch: b for b in bars}
    busy_until = -1
    daily_count = {}
    trades = []
    for session in sessions:
        if session.reset_epoch < busy_until:
            continue
        obs = observation_bars(bars, epochs, session.reset_epoch)
        if obs is None:
            continue
        raw_ktr, effective_ktr, asia_avg10, asia_capped = session_ktr(
            session, obs, daily_days, daily_ranges, prev_closes
        )
        if raw_ktr is None or effective_ktr is None or effective_ktr <= 0:
            continue
        active_start = session.observe_end_epoch
        start_i = bisect.bisect_left(epochs, active_start)
        end_i = bisect.bisect_left(epochs, session.next_reset_epoch)
        if start_i >= end_i:
            continue
        obs_sma = hourly_sma20_at(bar_by_epoch, session.observe_end_epoch)
        bias_a = model_a_bias(obs, obs_sma)
        direction, scan_i = trigger_direction(model, session, obs, bars, epochs, sma20_10m, start_i, end_i, bias_a)
        if direction == 0:
            continue
        entry_i = find_entry(bars, sma20_10m, direction, scan_i, end_i)
        if entry_i is None or entry_i >= len(bars):
            continue
        if bars[entry_i].epoch >= session.next_reset_epoch:
            continue
        day = str(kst_date(bars[entry_i].epoch))
        if daily_count.get(day, 0) >= 3:
            continue
        entry = bars[entry_i].open
        stop_dist = stop_mult * effective_ktr
        if stop_dist <= 0:
            continue
        if direction == 1:
            stop = entry - stop_dist
            tp = entry + stop_dist * tp_r
        else:
            stop = entry + stop_dist
            tp = entry - stop_dist * tp_r
        force_epoch = session.next_reset_epoch if exit_mode == "forced_session_close" else None
        exit_i, exit_price, reason = resolve_exit(bars, entry_i, direction, stop, tp, force_epoch)
        gross = (exit_price - entry) * direction
        net = gross - BASE_COST
        trades.append({
            "variant": "%s_sl%s_tp%s_%s" % (model, stop_mult, tp_r, exit_mode),
            "model": model,
            "session": session.name,
            "exit_mode": exit_mode,
            "entry_epoch": bars[entry_i].epoch,
            "exit_epoch": bars[exit_i].epoch,
            "entry_kst": fmt_kst(bars[entry_i].epoch),
            "exit_kst": fmt_kst(bars[exit_i].epoch),
            "entry_day": day,
            "year": str(kst_date(bars[entry_i].epoch).year),
            "direction": "LONG" if direction == 1 else "SHORT",
            "entry_price": entry,
            "exit_price": exit_price,
            "stop": stop,
            "tp": tp,
            "stop_mult": stop_mult,
            "tp_r": tp_r,
            "raw_ktr": raw_ktr,
            "effective_ktr": effective_ktr,
            "asia_avg10_range": asia_avg10,
            "asia_ktr_capped": asia_capped,
            "risk_points": stop_dist,
            "gross_points": gross,
            "net_points": net,
            "r_net": net / stop_dist,
            "hold_bars": exit_i - entry_i + 1,
            "exit_reason": reason,
        })
        daily_count[day] = daily_count.get(day, 0) + 1
        busy_until = bars[exit_i].epoch
    return trades


def run_all(bars):
    epochs = [b.epoch for b in bars]
    closes = [b.close for b in bars]
    sma20_10m = sma(closes, SMA_LEN)
    daily_days, daily_ranges, prev_closes = compute_daily_ranges(bars)
    sessions = build_session_resets(bars[0].epoch, bars[-1].epoch)
    all_trades = []
    summary = {"variants": {}, "sessions_total": len(sessions)}
    for model in MODELS:
        for stop_mult in STOP_MULTS:
            for tp_r in TP_RS:
                for exit_mode in EXIT_MODES:
                    trades = run_variant(
                        bars, sessions, epochs, sma20_10m, daily_days, daily_ranges, prev_closes,
                        model, stop_mult, tp_r, exit_mode
                    )
                    key = "%s_sl%s_tp%s_%s" % (model, stop_mult, tp_r, exit_mode)
                    summary["variants"][key] = {
                        "model": model,
                        "stop_mult": stop_mult,
                        "tp_r": tp_r,
                        "exit_mode": exit_mode,
                        "summary": summarize(trades),
                        "by_session": group_count(trades, "session"),
                        "by_direction": group_count(trades, "direction"),
                        "yearly": yearly_summary(trades),
                        "cost_sensitivity": cost_sensitivity(trades),
                    }
                    all_trades.extend(trades)
    return all_trades, summary


def write_trades(path, trades):
    fields = [
        "variant", "model", "session", "exit_mode", "entry_kst", "exit_kst", "direction",
        "entry_price", "exit_price", "stop", "tp", "stop_mult", "tp_r",
        "raw_ktr", "effective_ktr", "asia_avg10_range", "asia_ktr_capped",
        "risk_points", "gross_points", "net_points", "r_net", "hold_bars", "exit_reason",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as fp:
        wr = csv.DictWriter(fp, fieldnames=fields)
        wr.writeheader()
        for tr in trades:
            wr.writerow({k: tr.get(k, "") for k in fields})


def esc(x):
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_html(path, summary):
    rows = []
    ranked = sorted(summary["variants"].items(), key=lambda kv: kv[1]["summary"]["total_r"], reverse=True)
    for key, item in ranked:
        sm = item["summary"]
        rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td>%d</td><td>%.3f</td><td>%.2f</td><td>%.3f</td><td>%s</td><td>%.3f</td><td>%.3f</td>"
            "<td>%s</td><td>%s</td></tr>" % (
                esc(key), item["model"], item["stop_mult"], item["tp_r"],
                sm["trades"], sm["trades_per_day"], sm["win_rate"], sm["total_r"],
                esc(sm["pf"]), sm["mdd_r"], sm["net_points"],
                esc(item["by_session"]), esc(item["by_direction"])
            )
        )
    best_key, best = ranked[0] if ranked else ("", {"summary": {}})
    year_rows = []
    for row in best.get("yearly", []):
        year_rows.append(
            "<tr><td>%s</td><td>%d</td><td>%.2f</td><td>%.3f</td><td>%s</td><td>%.3f</td></tr>" % (
                row["year"], row["trades"], row["win_rate"], row["total_r"], esc(row["pf"]), row["mdd_r"]
            )
        )
    html = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>XAUUSD Session KTR Backtest</title>
<style>
body{font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;margin:24px;background:#f7f8fa;color:#172033}
h1{font-size:26px} h2{font-size:19px;margin-top:28px}
.note{background:#eef4ff;border-left:4px solid #1f5eff;padding:10px 12px;border-radius:6px;margin:12px 0}
table{border-collapse:collapse;width:100%%;background:white;font-size:13px}
th,td{border:1px solid #d8dee8;padding:7px;text-align:right;vertical-align:top}
th{background:#eef1f6;color:#344054}td:first-child,th:first-child{text-align:left}
</style></head><body>
<h1>XAUUSD Session KTR Backtest</h1>
<p class="note">First-pass result. Same-bar SL/TP conflicts count SL first. Baseline cost is 0.40 points per round trip.</p>
<h2>Variant Ranking</h2>
<table><tr><th>variant</th><th>model</th><th>SLx</th><th>TP R</th><th>trades</th><th>trades/day</th><th>win%%</th><th>total R</th><th>PF</th><th>MDD R</th><th>net pts</th><th>sessions</th><th>directions</th></tr>
%s</table>
<h2>Best Variant Yearly Breakdown: %s</h2>
<table><tr><th>year</th><th>trades</th><th>win%%</th><th>total R</th><th>PF</th><th>MDD R</th></tr>
%s</table>
</body></html>""" % ("".join(rows), esc(best_key), "".join(year_rows))
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(html)


def main():
    print("XAUUSD session KTR backtest | 10m | models A/B | cost=0.40")
    bars = load_bars(DATA_FILE)
    trades, summary = run_all(bars)
    write_trades(TRADES_FILE, trades)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2)
    write_html(REPORT_FILE, summary)
    ranked = sorted(summary["variants"].items(), key=lambda kv: kv[1]["summary"]["total_r"], reverse=True)
    print("variants=%d trades=%d sessions=%d" % (len(summary["variants"]), len(trades), summary["sessions_total"]))
    print("top variants:")
    for key, item in ranked[:8]:
        sm = item["summary"]
        print("%-32s trades=%5d tpd=%5.2f win=%6.2f totalR=%8.2f mddR=%7.2f pf=%s" % (
            key, sm["trades"], sm["trades_per_day"], sm["win_rate"], sm["total_r"], sm["mdd_r"], str(sm["pf"])
        ))
    print("WROTE %s" % TRADES_FILE)
    print("WROTE %s" % SUMMARY_FILE)
    print("WROTE %s" % REPORT_FILE)


if __name__ == "__main__":
    main()
