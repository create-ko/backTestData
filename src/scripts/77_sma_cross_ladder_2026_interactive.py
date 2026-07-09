# -*- coding: utf-8 -*-
"""77 - One-frame interactive candlestick report for 2026 ladder trades.

Run from data/:
  python ../src/scripts/77_sma_cross_ladder_2026_interactive.py
"""
import csv
import importlib.util
import json
import math
import os
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
MOD74 = os.path.join(BASE, "74_sma_cross_ladder.py")
spec = importlib.util.spec_from_file_location("ladder74", MOD74)
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

YEAR = "2026"
TRADES_FILE = "sma_cross_ladder_2026_trades.csv"
REPORT_FILE = os.path.join("..", "result", "sma_cross_ladder_2026_interactive.html")
KST = timezone(timedelta(hours=9))


def kst_year(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(KST).strftime("%Y")


def kst_text(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(KST).strftime("%Y-%m-%d %H:%M")


def parse_kst(text):
    dt = datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    return int(dt.astimezone(timezone.utc).timestamp())


def bollinger(src, length, mult):
    up = [None] * len(src)
    mid = [None] * len(src)
    lo = [None] * len(src)
    total = 0.0
    total_sq = 0.0
    for i, value in enumerate(src):
        total += value
        total_sq += value * value
        if i >= length:
            old = src[i - length]
            total -= old
            total_sq -= old * old
        if i >= length - 1:
            mean = total / length
            var = total_sq / length - mean * mean
            if var < 0:
                var = 0.0
            dev = mult * math.sqrt(var)
            up[i] = mean + dev
            mid[i] = mean
            lo[i] = mean - dev
    return up, mid, lo


def load_trades(path):
    with open(path, encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def trade_option_label(idx, trade):
    return "#%03d %s %s legs %s net %s exit %s" % (
        idx, trade["entry_kst"], trade["direction"], trade["legs"], trade["net_points"], trade["exit_kst"]
    )


def bar_payload(bars):
    closes = [b.close for b in bars]
    opens = [b.open for b in bars]
    sma20 = L.sma(closes, L.FAST)
    sma120 = L.sma(closes, L.SLOW)
    close_up, close_mid, close_lo = bollinger(closes, 20, 2.0)
    open_up, open_mid, open_lo = bollinger(opens, 4, 4.0)
    out = []
    for i, b in enumerate(bars):
        out.append({
            "t": kst_text(b.epoch),
            "o": round(b.open, 4),
            "h": round(b.high, 4),
            "l": round(b.low, 4),
            "c": round(b.close, 4),
            "s20": None if sma20[i] is None else round(sma20[i], 4),
            "s120": None if sma120[i] is None else round(sma120[i], 4),
            "bb20u": None if close_up[i] is None else round(close_up[i], 4),
            "bb20l": None if close_lo[i] is None else round(close_lo[i], 4),
            "bb4u": None if open_up[i] is None else round(open_up[i], 4),
            "bb4l": None if open_lo[i] is None else round(open_lo[i], 4),
        })
    return out


def trade_payload(trades, index_by_epoch):
    out = []
    for i, tr in enumerate(trades, 1):
        entry_epoch = parse_kst(tr["entry_kst"])
        exit_epoch = parse_kst(tr["exit_kst"])
        entry_idx = index_by_epoch.get(entry_epoch)
        exit_idx = index_by_epoch.get(exit_epoch)
        if entry_idx is None or exit_idx is None:
            continue
        direction = 1 if tr["direction"] == "LONG" else -1
        first = float(tr["first_entry"])
        levels = []
        for n in range(int(tr["legs"])):
            levels.append({"price": first - direction * L.STEP_POINTS * n, "label": "L%d" % (n + 1)})
        out.append({
            "num": i,
            "label": trade_option_label(i, tr),
            "entryIdx": entry_idx,
            "exitIdx": exit_idx,
            "entryKst": tr["entry_kst"],
            "exitKst": tr["exit_kst"],
            "direction": tr["direction"],
            "legs": int(tr["legs"]),
            "avg": float(tr["avg_price"]),
            "first": first,
            "exit": float(tr["exit_price"]),
            "net": float(tr["net_points"]),
            "hold": tr.get("hold_text", ""),
            "reason": tr["exit_reason"],
            "stop6": L.hard_stop_price(first, direction, L.STEP_POINTS, L.MAX_LEGS),
            "levels": levels,
        })
    return out


def html_shell(bars, trades, summary):
    payload = {
        "bars": bars,
        "trades": trades,
        "summary": summary,
    }
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>2026 SMA Cross Ladder Interactive Chart</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0b0f14;color:#e6edf3;font-family:Segoe UI,Malgun Gothic,Arial,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:18px}.top{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:12px}
h1{font-size:22px;margin:0 0 10px}.ctrl{display:flex;flex-direction:column;gap:4px}.ctrl label{font-size:12px;color:#98a2b3}
select,button{background:#111827;color:#e6edf3;border:1px solid #344054;border-radius:6px;padding:8px 10px}
select{min-width:620px;max-width:100%%}button{cursor:pointer}.stats{display:grid;grid-template-columns:repeat(8,1fr);gap:8px;margin:8px 0 12px}
.card{background:#111827;border:1px solid #293241;border-radius:8px;padding:10px}.k{font-size:11px;color:#98a2b3}.v{font-size:17px;font-weight:700}
#chartFrame{height:720px;background:#05070a;border:1px solid #293241;border-radius:8px;overflow:hidden}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#cbd5e1;margin:8px 0 12px}
.sw{display:inline-block;width:16px;height:3px;margin-right:5px;vertical-align:middle}.details{background:#111827;border:1px solid #293241;border-radius:8px;padding:10px;margin-top:12px;font-size:13px}
svg text{font-family:Segoe UI,Arial,sans-serif}.gridline{stroke:#1f2937;stroke-width:1}.axis{fill:#98a2b3;font-size:11px}
</style></head><body><div class="wrap">
<h1>2026 XAUUSD 5m SMA20/120 Cross Ladder - TradingView 검증용</h1>
<div class="top">
  <div class="ctrl"><label>거래 선택</label><select id="tradeSelect"></select></div>
  <button id="prevBtn">Prev</button><button id="nextBtn">Next</button>
</div>
<div class="stats">
  <div class="card"><div class="k">Trades</div><div class="v" id="stTrades"></div></div>
  <div class="card"><div class="k">Selected</div><div class="v" id="stSelected"></div></div>
  <div class="card"><div class="k">Direction</div><div class="v" id="stDirection"></div></div>
  <div class="card"><div class="k">Legs</div><div class="v" id="stLegs"></div></div>
  <div class="card"><div class="k">Net</div><div class="v" id="stNet"></div></div>
  <div class="card"><div class="k">Hold</div><div class="v" id="stHold"></div></div>
  <div class="card"><div class="k">Entry</div><div class="v" id="stEntry"></div></div>
  <div class="card"><div class="k">Exit</div><div class="v" id="stExit"></div></div>
</div>
<div class="legend">
  <span><span class="sw" style="background:#22c55e"></span>상승캔들</span>
  <span><span class="sw" style="background:#ef4444"></span>하락캔들</span>
  <span><span class="sw" style="background:#ffffff"></span>20/2 종가 BB</span>
  <span><span class="sw" style="background:#ef4444"></span>4/4 시가 BB</span>
  <span><span class="sw" style="background:#b8ff7a"></span>120 장기 SMA</span>
  <span><span class="sw" style="background:#ffffff"></span>20 단기 SMA</span>
</div>
<div id="chartFrame"></div>
<div class="details" id="details"></div>
</div>
<script id="payload" type="application/json">%s</script>
<script>
const payload = JSON.parse(document.getElementById('payload').textContent);
const bars = payload.bars;
const trades = payload.trades;
const select = document.getElementById('tradeSelect');
for (const t of trades) {
  const opt = document.createElement('option');
  opt.value = String(t.num - 1);
  opt.textContent = t.label;
  select.appendChild(opt);
}
document.getElementById('stTrades').textContent = trades.length;
document.getElementById('prevBtn').onclick = () => { select.selectedIndex = Math.max(0, select.selectedIndex - 1); renderTrade(select.selectedIndex); };
document.getElementById('nextBtn').onclick = () => { select.selectedIndex = Math.min(trades.length - 1, select.selectedIndex + 1); renderTrade(select.selectedIndex); };
select.onchange = () => renderTrade(select.selectedIndex);

function fmt(x){ return Number(x).toFixed(2); }
function xScale(i, n, left, width){ return left + width * i / Math.max(1, n - 1); }
function yScale(v, min, max, top, height){ return top + height * (1 - (v - min) / (max - min)); }
function pathLine(points, color, w, dash){
  if(points.length < 2) return '';
  return `<polyline fill="none" stroke="${color}" stroke-width="${w}" ${dash ? `stroke-dasharray="${dash}"` : ''} points="${points.join(' ')}"/>`;
}
function renderTrade(idx){
  const t = trades[idx];
  if(!t) return;
  const before = 90;
  const after = 90;
  const start = Math.max(0, t.entryIdx - before);
  const end = Math.min(bars.length - 1, Math.max(t.exitIdx + after, t.entryIdx + 160));
  const slice = bars.slice(start, end + 1);
  const W = 1460, H = 700, L = 62, R = 88, T = 18, B = 34;
  const cw = W - L - R, ch = H - T - B;
  let vals = [];
  for(const b of slice){
    vals.push(b.h,b.l);
    for(const k of ['s20','s120','bb20u','bb20l','bb4u','bb4l']) if(b[k] !== null) vals.push(b[k]);
  }
  vals.push(t.avg,t.exit,t.stop6);
  for(const lv of t.levels) vals.push(lv.price);
  let min = Math.min(...vals), max = Math.max(...vals);
  const pad = (max - min) * 0.08 || 1;
  min -= pad; max += pad;
  let out = [`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`, `<rect x="0" y="0" width="${W}" height="${H}" fill="#05070a"/>`];
  for(let g=0; g<=6; g++){
    const y = T + ch * g / 6;
    const price = max - (max-min)*g/6;
    out.push(`<line class="gridline" x1="${L}" y1="${y}" x2="${W-R}" y2="${y}"/>`);
    out.push(`<text class="axis" x="${W-R+8}" y="${y+4}">${fmt(price)}</text>`);
  }
  const n = slice.length;
  const bodyW = Math.max(2, Math.min(8, cw / n * 0.68));
  function sx(i){ return xScale(i, n, L, cw); }
  function sy(v){ return yScale(v, min, max, T, ch); }
  const lines = {s20:[],s120:[],bb20u:[],bb20l:[],bb4u:[],bb4l:[]};
  slice.forEach((b,i)=>{
    for(const k in lines){ if(b[k] !== null) lines[k].push(`${sx(i).toFixed(1)},${sy(b[k]).toFixed(1)}`); }
  });
  out.push(pathLine(lines.bb20u, '#ffffff', 1.2, '5 5'));
  out.push(pathLine(lines.bb20l, '#ffffff', 1.2, '5 5'));
  out.push(pathLine(lines.bb4u, '#ef4444', 1.1, '4 4'));
  out.push(pathLine(lines.bb4l, '#ef4444', 1.1, '4 4'));
  out.push(pathLine(lines.s120, '#b8ff7a', 2.0, ''));
  out.push(pathLine(lines.s20, '#ffffff', 2.0, ''));
  slice.forEach((b,i)=>{
    const x = sx(i), yo = sy(b.o), yc = sy(b.c), yh = sy(b.h), yl = sy(b.l);
    const up = b.c >= b.o;
    const color = up ? '#22c55e' : '#ef4444';
    out.push(`<line x1="${x}" y1="${yh}" x2="${x}" y2="${yl}" stroke="${color}" stroke-width="1"/>`);
    out.push(`<rect x="${x-bodyW/2}" y="${Math.min(yo,yc)}" width="${bodyW}" height="${Math.max(1,Math.abs(yc-yo))}" fill="${color}"/>`);
  });
  function hLine(price,label,color,dash='4 4'){
    const y=sy(price);
    out.push(`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="${color}" stroke-width="1.2" stroke-dasharray="${dash}"/>`);
    out.push(`<text x="${L+6}" y="${y-4}" font-size="12" fill="${color}">${label} ${fmt(price)}</text>`);
  }
  hLine(t.avg,'AVG','#38bdf8');
  hLine(t.stop6,'STOP6','#fb7185');
  hLine(t.exit,'EXIT','#facc15');
  for(const lv of t.levels) hLine(lv.price,lv.label,'#a78bfa','2 6');
  function vLine(globalIdx,label,color){
    const local = globalIdx - start;
    const x = sx(local);
    out.push(`<line x1="${x}" y1="${T}" x2="${x}" y2="${H-B}" stroke="${color}" stroke-width="2"/>`);
    out.push(`<text x="${x+5}" y="${T+16}" font-size="12" fill="${color}">${label}</text>`);
  }
  vLine(t.entryIdx,'ENTRY','#22c55e');
  vLine(t.exitIdx,'EXIT','#facc15');
  out.push('</svg>');
  document.getElementById('chartFrame').innerHTML = out.join('');
  document.getElementById('stSelected').textContent = `#${String(t.num).padStart(3,'0')}`;
  document.getElementById('stDirection').textContent = t.direction;
  document.getElementById('stLegs').textContent = t.legs;
  document.getElementById('stNet').textContent = fmt(t.net);
  document.getElementById('stHold').textContent = t.hold;
  document.getElementById('stEntry').textContent = t.entryKst.slice(5);
  document.getElementById('stExit').textContent = t.exitKst.slice(5);
  document.getElementById('details').innerHTML =
    `<b>${t.label}</b><br>` +
    `진입: ${t.entryKst}, 청산: ${t.exitKst}, 방향: ${t.direction}, 청산사유: ${t.reason}<br>` +
    `평균단가: ${fmt(t.avg)}, 최초진입: ${fmt(t.first)}, 청산가: ${fmt(t.exit)}, 6구간 손절선: ${fmt(t.stop6)}<br>` +
    `표시 구간: ${bars[start].t} ~ ${bars[end].t}`;
}
if(trades.length) renderTrade(0);
</script></body></html>""" % data_json


def main():
    print("2026 interactive candlestick report | XAUUSD 5m")
    bars = [b for b in L.load_bars(L.DATA_FILE) if kst_year(b.epoch) == YEAR]
    trades = load_trades(TRADES_FILE)
    index_by_epoch = {b.epoch: i for i, b in enumerate(bars)}
    bp = bar_payload(bars)
    tp = trade_payload(trades, index_by_epoch)
    summary = {"trades": len(tp), "bars": len(bp)}
    html = html_shell(bp, tp, summary)
    with open(REPORT_FILE, "w", encoding="utf-8") as fp:
        fp.write(html)
    print("bars=%d trades=%d" % (len(bp), len(tp)))
    print("WROTE %s" % REPORT_FILE)


if __name__ == "__main__":
    main()
