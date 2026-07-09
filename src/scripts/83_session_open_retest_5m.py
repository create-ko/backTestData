# -*- coding: utf-8 -*-
"""83 - 2026 XAUUSD 5m session first-candle close retest strategy.

Run from data/:
  python ../src/scripts/83_session_open_retest_5m.py

Console output is ASCII-only. Output CSV/JSON/HTML files are UTF-8.
"""
import bisect
import csv
import json
import os
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

DATA_FILE = "xauusd_5m_2010-01-01_2026-06-16.csv"
TRADES_FILE = "session_open_retest_5m_2026_trades.csv"
SUMMARY_FILE = "session_open_retest_5m_2026_summary.json"
REPORT_FILE = os.path.join("..", "result", "session_open_retest_5m_2026_report.html")

YEAR = "2026"
KST = timezone(timedelta(hours=9))
BAR_SECONDS = 300
COST_PER_ROUNDTRIP = 0.40


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
        self.reset_epoch = int(reset_epoch)
        self.next_reset_epoch = int(next_reset_epoch)


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


def kst_dt(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(KST)


def fmt_kst(epoch):
    return kst_dt(epoch).strftime("%Y-%m-%d %H:%M")


def kst_year(epoch):
    return kst_dt(epoch).strftime("%Y")


def kst_date(epoch):
    return kst_dt(epoch).date()


def kst_fixed_epoch(day, hour, minute):
    dt = datetime.combine(day, dtime(hour, minute), tzinfo=KST)
    return int(dt.astimezone(timezone.utc).timestamp())


def local_reset_to_epoch(day, tz_name, hour, minute):
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(tz_name))
    return int(local.astimezone(timezone.utc).timestamp())


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
        resets.append((kst_fixed_epoch(day, 8, 0), "Asia"))
        resets.append((local_reset_to_epoch(day, "Europe/London", 8, 0), "Europe"))
        resets.append((local_reset_to_epoch(day, "America/New_York", 9, 30), "NewYork"))
    resets = sorted(set(resets))
    sessions = []
    sid = 0
    for i in range(len(resets) - 1):
        reset_epoch, name = resets[i]
        next_epoch = resets[i + 1][0]
        if reset_epoch < first_epoch or reset_epoch + BAR_SECONDS >= last_epoch:
            continue
        sid += 1
        sessions.append(Session(sid, name, reset_epoch, next_epoch))
    return sessions


def setup_from_first_bar(first):
    if first.close > first.open:
        direction = 1
    elif first.close < first.open:
        direction = -1
    else:
        return None
    return {
        "direction": direction,
        "level": first.close,
        "stop": (first.open + first.close) / 2.0,
        "first_open": first.open,
        "first_close": first.close,
        "first_high": first.high,
        "first_low": first.low,
    }


def is_retest(bar, setup):
    level = setup["level"]
    if setup["direction"] == 1:
        return bar.low <= level and bar.close >= level
    return bar.high >= level and bar.close <= level


def session_first_bar(bars, epochs, session):
    idx = bisect.bisect_left(epochs, session.reset_epoch)
    if idx >= len(bars) or bars[idx].epoch != session.reset_epoch:
        return None, None
    return idx, bars[idx]


def find_retest_index(bars, start_i, end_i, setup):
    for i in range(start_i, end_i):
        if is_retest(bars[i], setup):
            return i
    return None


def prices_for_trade(entry, stop, direction):
    risk = (entry - stop) * direction
    if risk <= 0:
        return None
    tp = entry + direction * risk * 2.0
    return risk, tp


def resolve_exit(bars, entry_i, direction, stop, tp):
    for i in range(entry_i, len(bars)):
        bar = bars[i]
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


def close_trade(bars, session, first_i, retest_i, entry_i, exit_i, setup, entry, stop, tp, exit_price, reason):
    direction = setup["direction"]
    gross = (exit_price - entry) * direction
    net = gross - COST_PER_ROUNDTRIP
    risk = abs(entry - stop)
    return {
        "session_id": session.sid,
        "session": session.name,
        "session_start_kst": fmt_kst(session.reset_epoch),
        "first_bar_kst": fmt_kst(bars[first_i].epoch),
        "retest_kst": fmt_kst(bars[retest_i].epoch),
        "entry_kst": fmt_kst(bars[entry_i].epoch),
        "exit_kst": fmt_kst(bars[exit_i].epoch),
        "entry_day": str(kst_date(bars[entry_i].epoch)),
        "year": kst_year(bars[entry_i].epoch),
        "direction": "LONG" if direction == 1 else "SHORT",
        "first_open": setup["first_open"],
        "first_close": setup["first_close"],
        "level": setup["level"],
        "entry_price": entry,
        "stop": stop,
        "tp": tp,
        "exit_price": exit_price,
        "risk_points": risk,
        "gross_points": gross,
        "cost": COST_PER_ROUNDTRIP,
        "net_points": net,
        "r_gross": gross / risk if risk > 0 else 0.0,
        "r_net": net / risk if risk > 0 else 0.0,
        "hold_bars": exit_i - entry_i + 1,
        "exit_reason": reason,
        "first_epoch": bars[first_i].epoch,
        "retest_epoch": bars[retest_i].epoch,
        "entry_epoch": bars[entry_i].epoch,
        "exit_epoch": bars[exit_i].epoch,
    }


def backtest(bars, sessions):
    epochs = [b.epoch for b in bars]
    trades = []
    busy_until_epoch = -1
    meta = {
        "sessions": 0,
        "missing_first_bar": 0,
        "setups": 0,
        "doji_first_bar": 0,
        "no_retest": 0,
        "bad_risk": 0,
        "busy_sessions": 0,
    }
    for session in sessions:
        meta["sessions"] += 1
        if session.reset_epoch <= busy_until_epoch:
            meta["busy_sessions"] += 1
            continue
        first_i, first = session_first_bar(bars, epochs, session)
        if first is None:
            meta["missing_first_bar"] += 1
            continue
        setup = setup_from_first_bar(first)
        if setup is None:
            meta["doji_first_bar"] += 1
            continue
        meta["setups"] += 1
        scan_start = first_i + 1
        scan_end = bisect.bisect_left(epochs, session.next_reset_epoch)
        retest_i = find_retest_index(bars, scan_start, scan_end, setup)
        if retest_i is None or retest_i + 1 >= len(bars):
            meta["no_retest"] += 1
            continue
        entry_i = retest_i + 1
        if bars[entry_i].epoch >= session.next_reset_epoch:
            meta["no_retest"] += 1
            continue
        entry = bars[entry_i].open
        prices = prices_for_trade(entry, setup["stop"], setup["direction"])
        if prices is None:
            meta["bad_risk"] += 1
            continue
        risk, tp = prices
        exit_i, exit_price, reason = resolve_exit(bars, entry_i, setup["direction"], setup["stop"], tp)
        trades.append(close_trade(
            bars, session, first_i, retest_i, entry_i, exit_i, setup,
            entry, setup["stop"], tp, exit_price, reason
        ))
        busy_until_epoch = bars[exit_i].epoch
    return trades, meta


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
    vals = [float(t["net_points"]) for t in trades]
    rs = [float(t["r_net"]) for t in trades]
    wins = sum(1 for v in vals if v > 0)
    pf = profit_factor(vals)
    return {
        "trades": len(trades),
        "win_rate": round(100.0 * wins / len(vals), 2) if vals else 0.0,
        "net_points": round(sum(vals), 3),
        "avg_points": round(sum(vals) / len(vals), 4) if vals else 0.0,
        "total_r_net": round(sum(rs), 3),
        "avg_r_net": round(sum(rs) / len(rs), 4) if rs else 0.0,
        "pf": "inf" if pf == float("inf") else round(pf, 3),
        "mdd_points": round(max_drawdown(vals), 3),
        "mdd_r": round(max_drawdown(rs), 3),
    }


def group_summary(trades, key):
    groups = {}
    for tr in trades:
        groups.setdefault(tr[key], []).append(tr)
    rows = []
    for name in sorted(groups):
        row = summarize(groups[name])
        row[key] = name
        rows.append(row)
    return rows


def filter_bars_by_year(bars, year):
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


def enrich_trades(trades):
    out = []
    for tr in trades:
        row = dict(tr)
        row["month"] = row["entry_kst"][:7]
        row["hold_minutes"] = int(row["hold_bars"]) * 5
        row["hold_text"] = format_hold_minutes(row["hold_minutes"])
        out.append(row)
    return out


def write_trades(path, trades):
    fields = [
        "session", "session_start_kst", "first_bar_kst", "retest_kst", "entry_kst", "exit_kst",
        "month", "direction", "first_open", "first_close", "level", "entry_price", "stop", "tp",
        "exit_price", "risk_points", "gross_points", "cost", "net_points", "r_gross", "r_net",
        "hold_bars", "hold_minutes", "hold_text", "exit_reason",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as fp:
        wr = csv.DictWriter(fp, fieldnames=fields)
        wr.writeheader()
        for tr in trades:
            wr.writerow({k: tr.get(k, "") for k in fields})


def esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table(rows, first_key):
    if not rows:
        return "<p>No rows.</p>"
    cols = [first_key, "trades", "win_rate", "net_points", "avg_points", "total_r_net", "avg_r_net", "pf", "mdd_points"]
    head = "".join("<th>%s</th>" % esc(c) for c in cols)
    body = []
    for row in rows:
        body.append("<tr>" + "".join("<td>%s</td>" % esc(row.get(c, "")) for c in cols) + "</tr>")
    return "<table><tr>%s</tr>%s</table>" % (head, "".join(body))


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
    points = []
    for i, value in enumerate(values):
        x = pad + (width - 2 * pad) * i / max(1, len(values) - 1)
        y = pad + (height - 2 * pad) * (1.0 - (value - vmin) / (vmax - vmin))
        points.append("%.1f,%.1f" % (x, y))
    return (
        '<svg viewBox="0 0 %d %d"><rect width="%d" height="%d" fill="#fff"/>'
        '<polyline fill="none" stroke="#1f5eff" stroke-width="2" points="%s"/></svg>'
    ) % (width, height, width, height, " ".join(points))


def trade_rows(trades):
    cols = ["entry_kst", "exit_kst", "session", "direction", "entry_price", "stop", "tp", "exit_price", "net_points", "r_net", "hold_text", "exit_reason"]
    head = "".join("<th>%s</th>" % esc(c) for c in cols)
    body = []
    for tr in trades:
        body.append("<tr>" + "".join("<td>%s</td>" % esc(tr.get(c, "")) for c in cols) + "</tr>")
    return "<table><tr>%s</tr>%s</table>" % (head, "".join(body))


def bar_payload(bars):
    return [{
        "t": fmt_kst(b.epoch),
        "epoch": b.epoch,
        "o": round(b.open, 4),
        "h": round(b.high, 4),
        "l": round(b.low, 4),
        "c": round(b.close, 4),
    } for b in bars]


def trade_option_label(idx, trade):
    return "#%03d %s %s %s net %.2f %s" % (
        idx, trade["entry_kst"], trade["session"], trade["direction"],
        float(trade["net_points"]), trade["exit_reason"]
    )


def trade_payload(trades, index_by_epoch):
    out = []
    for i, tr in enumerate(trades, 1):
        first_i = index_by_epoch.get(tr["first_epoch"])
        retest_i = index_by_epoch.get(tr["retest_epoch"])
        entry_i = index_by_epoch.get(tr["entry_epoch"])
        exit_i = index_by_epoch.get(tr["exit_epoch"])
        if None in (first_i, retest_i, entry_i, exit_i):
            continue
        out.append({
            "num": i,
            "label": trade_option_label(i, tr),
            "session": tr["session"],
            "direction": tr["direction"],
            "firstIdx": first_i,
            "retestIdx": retest_i,
            "entryIdx": entry_i,
            "exitIdx": exit_i,
            "firstKst": tr["first_bar_kst"],
            "retestKst": tr["retest_kst"],
            "entryKst": tr["entry_kst"],
            "exitKst": tr["exit_kst"],
            "level": round(float(tr["level"]), 4),
            "entry": round(float(tr["entry_price"]), 4),
            "stop": round(float(tr["stop"]), 4),
            "tp": round(float(tr["tp"]), 4),
            "exit": round(float(tr["exit_price"]), 4),
            "risk": round(float(tr["risk_points"]), 4),
            "net": round(float(tr["net_points"]), 4),
            "rNet": round(float(tr["r_net"]), 4),
            "hold": tr.get("hold_text", ""),
            "reason": tr["exit_reason"],
        })
    return out


def html_shell(bars, trades, summary):
    payload = json.dumps({"bars": bars, "trades": trades, "summary": summary}, ensure_ascii=False, separators=(",", ":"))
    return """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>2026 Session Open Retest 5m Backtest</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0b0f14;color:#e6edf3;font-family:Segoe UI,Malgun Gothic,Arial,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:18px}h1{font-size:22px;margin:0 0 12px}
.top{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap}.ctrl{display:flex;flex-direction:column;gap:4px}
.ctrl label{font-size:12px;color:#98a2b3}select,button{background:#111827;color:#e6edf3;border:1px solid #344054;border-radius:6px;padding:8px 10px}
select{min-width:680px;max-width:100%%}.stats{display:grid;grid-template-columns:repeat(8,1fr);gap:8px;margin:12px 0}
.card{background:#111827;border:1px solid #293241;border-radius:8px;padding:10px}.k{font-size:11px;color:#98a2b3}.v{font-size:17px;font-weight:700}
#chartFrame{height:720px;background:#05070a;border:1px solid #293241;border-radius:8px;overflow:hidden}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#cbd5e1;margin:8px 0 12px}
.sw{display:inline-block;width:16px;height:3px;margin-right:5px;vertical-align:middle}.details{background:#111827;border:1px solid #293241;border-radius:8px;padding:10px;margin-top:12px;font-size:13px}
.gridline{stroke:#1f2937;stroke-width:1}.axis{fill:#98a2b3;font-size:11px}
</style></head><body><div class="wrap">
<h1>2026 XAUUSD 5m Session First-Candle Close Retest</h1>
<div class="top"><div class="ctrl"><label>거래 선택</label><select id="tradeSelect"></select></div><button id="prevBtn">Prev</button><button id="nextBtn">Next</button></div>
<div class="stats">
<div class="card"><div class="k">Trades</div><div class="v" id="stTrades"></div></div>
<div class="card"><div class="k">Selected</div><div class="v" id="stSelected"></div></div>
<div class="card"><div class="k">Session</div><div class="v" id="stSession"></div></div>
<div class="card"><div class="k">Direction</div><div class="v" id="stDirection"></div></div>
<div class="card"><div class="k">Net</div><div class="v" id="stNet"></div></div>
<div class="card"><div class="k">R Net</div><div class="v" id="stR"></div></div>
<div class="card"><div class="k">Entry</div><div class="v" id="stEntry"></div></div>
<div class="card"><div class="k">Exit</div><div class="v" id="stExit"></div></div>
</div>
<div class="legend">
<span><span class="sw" style="background:#22c55e"></span>상승캔들</span>
<span><span class="sw" style="background:#ef4444"></span>하락캔들</span>
<span><span class="sw" style="background:#38bdf8"></span>FIRST</span>
<span><span class="sw" style="background:#a78bfa"></span>RETEST</span>
<span><span class="sw" style="background:#22c55e"></span>ENTRY</span>
<span><span class="sw" style="background:#fb7185"></span>SL</span>
<span><span class="sw" style="background:#facc15"></span>TP/EXIT</span>
</div>
<div id="chartFrame"></div><div class="details" id="details"></div></div>
<script id="payload" type="application/json">%s</script>
<script>
const payload = JSON.parse(document.getElementById('payload').textContent);
const bars = payload.bars, trades = payload.trades, select = document.getElementById('tradeSelect');
for (const t of trades){ const opt=document.createElement('option'); opt.value=String(t.num-1); opt.textContent=t.label; select.appendChild(opt); }
document.getElementById('stTrades').textContent = trades.length;
document.getElementById('prevBtn').onclick = () => { select.selectedIndex=Math.max(0,select.selectedIndex-1); renderTrade(select.selectedIndex); };
document.getElementById('nextBtn').onclick = () => { select.selectedIndex=Math.min(trades.length-1,select.selectedIndex+1); renderTrade(select.selectedIndex); };
select.onchange = () => renderTrade(select.selectedIndex);
function fmt(x){ return Number(x).toFixed(2); }
function xScale(i,n,left,width){ return left + width*i/Math.max(1,n-1); }
function yScale(v,min,max,top,height){ return top + height*(1-(v-min)/(max-min)); }
function renderTrade(idx){
  const t=trades[idx]; if(!t) return;
  const start=Math.max(0,t.firstIdx-24), end=Math.min(bars.length-1,Math.max(t.exitIdx+36,t.entryIdx+80));
  const slice=bars.slice(start,end+1);
  const W=1460,H=700,L=62,R=88,T=18,B=34,cw=W-L-R,ch=H-T-B;
  let vals=[]; for(const b of slice){ vals.push(b.h,b.l); } vals.push(t.level,t.entry,t.stop,t.tp,t.exit);
  let min=Math.min(...vals), max=Math.max(...vals), pad=(max-min)*0.08||1; min-=pad; max+=pad;
  function sx(i){ return xScale(i,slice.length,L,cw); } function sy(v){ return yScale(v,min,max,T,ch); }
  let out=[`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`,`<rect width="${W}" height="${H}" fill="#05070a"/>`];
  for(let g=0; g<=6; g++){ const y=T+ch*g/6, p=max-(max-min)*g/6; out.push(`<line class="gridline" x1="${L}" y1="${y}" x2="${W-R}" y2="${y}"/>`); out.push(`<text class="axis" x="${W-R+8}" y="${y+4}">${fmt(p)}</text>`); }
  const bodyW=Math.max(2,Math.min(8,cw/slice.length*0.68));
  slice.forEach((b,i)=>{ const x=sx(i),yo=sy(b.o),yc=sy(b.c),yh=sy(b.h),yl=sy(b.l),color=b.c>=b.o?'#22c55e':'#ef4444'; out.push(`<line x1="${x}" y1="${yh}" x2="${x}" y2="${yl}" stroke="${color}" stroke-width="1"/>`); out.push(`<rect x="${x-bodyW/2}" y="${Math.min(yo,yc)}" width="${bodyW}" height="${Math.max(1,Math.abs(yc-yo))}" fill="${color}"/>`); });
  function hLine(price,label,color,dash='4 4'){ const y=sy(price); out.push(`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="${color}" stroke-width="1.3" stroke-dasharray="${dash}"/>`); out.push(`<text x="${L+6}" y="${y-4}" font-size="12" fill="${color}">${label} ${fmt(price)}</text>`); }
  hLine(t.level,'LEVEL','#38bdf8'); hLine(t.entry,'ENTRY','#22c55e'); hLine(t.stop,'SL','#fb7185'); hLine(t.tp,'TP','#facc15'); hLine(t.exit,'EXIT','#ffffff','2 6');
  function vLine(globalIdx,label,color){ const local=globalIdx-start, x=sx(local); out.push(`<line x1="${x}" y1="${T}" x2="${x}" y2="${H-B}" stroke="${color}" stroke-width="2"/>`); out.push(`<text x="${x+5}" y="${T+16}" font-size="12" fill="${color}">${label}</text>`); }
  vLine(t.firstIdx,'FIRST','#38bdf8'); vLine(t.retestIdx,'RETEST','#a78bfa'); vLine(t.entryIdx,'ENTRY','#22c55e'); vLine(t.exitIdx,'EXIT','#facc15');
  out.push('</svg>'); document.getElementById('chartFrame').innerHTML=out.join('');
  document.getElementById('stSelected').textContent = `#${String(t.num).padStart(3,'0')}`;
  document.getElementById('stSession').textContent=t.session; document.getElementById('stDirection').textContent=t.direction;
  document.getElementById('stNet').textContent=fmt(t.net); document.getElementById('stR').textContent=Number(t.rNet).toFixed(3);
  document.getElementById('stEntry').textContent=t.entryKst.slice(5); document.getElementById('stExit').textContent=t.exitKst.slice(5);
  document.getElementById('details').innerHTML = `<b>${t.label}</b><br>FIRST: ${t.firstKst}, RETEST: ${t.retestKst}, ENTRY: ${t.entryKst}, EXIT: ${t.exitKst}<br>Level ${fmt(t.level)}, Entry ${fmt(t.entry)}, SL ${fmt(t.stop)}, TP ${fmt(t.tp)}, Exit ${fmt(t.exit)}, Risk ${fmt(t.risk)}, Reason ${t.reason}<br>Window: ${bars[start].t} ~ ${bars[end].t}`;
}
if(trades.length) renderTrade(0);
</script></body></html>""" % payload


def write_summary_report(path, trades, summary, meta, monthly, by_session, by_direction, by_reason, chart_html):
    html = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>2026 Session Open Retest 5m Backtest</title>
<style>
body{font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;margin:24px;background:#f7f8fa;color:#172033}
h1{font-size:26px}h2{font-size:19px;margin-top:28px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.card{background:white;border:1px solid #d8dee8;border-radius:8px;padding:14px}.k{color:#667085;font-size:12px}.v{font-size:22px;font-weight:700}
.note{background:#eef4ff;border-left:4px solid #1f5eff;padding:10px 12px;border-radius:6px;margin:12px 0}
table{border-collapse:collapse;background:white;font-size:13px;margin-top:8px;width:100%%}
th,td{border:1px solid #d8dee8;padding:7px;text-align:right;vertical-align:top}th{background:#eef1f6}
td:first-child,th:first-child{text-align:left}.chart{background:white;border:1px solid #d8dee8;border-radius:8px;padding:10px}
</style></head><body>
<h1>2026 XAUUSD 5m 세션 첫봉 종가 리테스트 백테스트</h1>
<p class="note">세션 시작 첫 5분봉이 양봉이면 종가 리테스트 후 다음봉 시가 롱, 음봉이면 반대 숏. 손절은 첫봉 몸통 50%%, 익절은 진입가 기준 1:2입니다. 같은 봉에서 SL/TP가 모두 닿으면 SL 우선으로 처리했습니다.</p>
<div class="grid">
<div class="card"><div class="k">Trades</div><div class="v">%s</div></div>
<div class="card"><div class="k">Win Rate</div><div class="v">%s%%</div></div>
<div class="card"><div class="k">Net Points</div><div class="v">%s</div></div>
<div class="card"><div class="k">Total R Net</div><div class="v">%s</div></div>
<div class="card"><div class="k">PF</div><div class="v">%s</div></div>
<div class="card"><div class="k">MDD Points</div><div class="v">%s</div></div>
<div class="card"><div class="k">Sessions</div><div class="v">%s</div></div>
<div class="card"><div class="k">No Retest</div><div class="v">%s</div></div>
</div>
<h2>누적 손익 곡선</h2><div class="chart">%s</div>
<h2>월별 요약</h2>%s
<h2>세션별 요약</h2>%s
<h2>방향별 요약</h2>%s
<h2>청산 사유별 요약</h2>%s
<h2>거래별 상세</h2>%s
<h2>차트 검증</h2>
<p><a href="%s">드롭다운 캔들차트 리포트 열기</a></p>
</body></html>""" % (
        summary["trades"], summary["win_rate"], summary["net_points"], summary["total_r_net"],
        summary["pf"], summary["mdd_points"], meta.get("sessions", 0), meta.get("no_retest", 0),
        line_chart_svg(equity_curve(trades)), table(monthly, "month"), table(by_session, "session"),
        table(by_direction, "direction"), table(by_reason, "exit_reason"), trade_rows(trades),
        os.path.basename(REPORT_FILE),
    )
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(html)


def main():
    print("session open retest 5m | XAUUSD | 2026")
    bars = filter_bars_by_year(load_bars(DATA_FILE), YEAR)
    sessions = build_session_resets(bars[0].epoch, bars[-1].epoch)
    trades, meta = backtest(bars, sessions)
    trades = enrich_trades(trades)
    summary = summarize(trades)
    monthly = group_summary(trades, "month")
    by_session = group_summary(trades, "session")
    by_direction = group_summary(trades, "direction")
    by_reason = group_summary(trades, "exit_reason")
    out = {
        "summary": summary,
        "meta": meta,
        "monthly": monthly,
        "by_session": by_session,
        "by_direction": by_direction,
        "by_exit_reason": by_reason,
        "assumptions": {
            "year": YEAR,
            "data_file": DATA_FILE,
            "session_resets": "Asia 08:00 KST, Europe 08:00 London, NewYork 09:30 New York",
            "entry": "next 5m bar open after retest candle",
            "long_retest": "low <= first close and close >= first close",
            "short_retest": "high >= first close and close <= first close",
            "stop": "midpoint of first 5m candle body",
            "take_profit": "2R from entry",
            "cost_per_roundtrip_points": COST_PER_ROUNDTRIP,
            "same_bar_order": "SL before TP",
        },
    }
    write_trades(TRADES_FILE, trades)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)
    index_by_epoch = {b.epoch: i for i, b in enumerate(bars)}
    chart_html = html_shell(bar_payload(bars), trade_payload(trades, index_by_epoch), summary)
    with open(REPORT_FILE, "w", encoding="utf-8") as fp:
        fp.write(chart_html)
    write_summary_report(os.path.join("..", "result", "session_open_retest_5m_2026_summary.html"),
                         trades, summary, meta, monthly, by_session, by_direction, by_reason, chart_html)
    print("sessions=%d setups=%d trades=%d win=%.2f net=%.2f totalR=%.3f pf=%s mdd=%.2f" % (
        meta["sessions"], meta["setups"], summary["trades"], summary["win_rate"],
        summary["net_points"], summary["total_r_net"], str(summary["pf"]), summary["mdd_points"]
    ))
    print("WROTE %s" % TRADES_FILE)
    print("WROTE %s" % SUMMARY_FILE)
    print("WROTE %s" % REPORT_FILE)
    print("WROTE %s" % os.path.join("..", "result", "session_open_retest_5m_2026_summary.html"))


if __name__ == "__main__":
    main()
