# -*- coding: utf-8 -*-
"""
15_risk_by_year.py — 연도별 손절률 + 기대값 (TP 2배수, KTR, 등량 랏). TF 토글.
sim_tp2 기준. 회복폭 차트(tf_level_chart)의 짝 = 수익성/위험 면.
출력: risk_by_year.html
"""
import csv, json
from collections import defaultdict

SRC="sim_tp2_all_tf_2010-01-01_2026-06-16.csv"
OUT="../result/risk_by_year.html"
MULT=[0,1,2,3,4,4.5]
def win_pnl(k): return sum(MULT[i]-MULT[k-1]+2.0 for i in range(k))
STOP=sum(MULT[i]-5 for i in range(6))   # -15.5
TFS=["전체","2m","5m","10m"]

rows=[r for r in csv.DictReader(open(SRC,encoding="utf-8-sig"))
      if r["base종류"]=="KTR" and r["exitReason"] in ("TP","STOP")]
YEARS=sorted({r["datetime_kst"][:4] for r in rows})   # 데이터 기간에서 자동 도출

def stats(sub):
    n=len(sub)
    if not n: return None
    stop=sum(1 for r in sub if r["exitReason"]=="STOP")
    six=sum(1 for r in sub if r["maxFilledCount"]=="6")
    ps=[STOP if r["exitReason"]=="STOP" else win_pnl(int(r["maxFilledCount"])) for r in sub]
    exp=sum(ps)/n; win=sum(1 for p in ps if p>0)/n
    return dict(n=n, stop=round(100*stop/n,2), six=round(100*six/n,1),
               win=round(100*win,1), exp=round(exp,3))

DATA={}
for tf in TFS:
    DATA[tf]={"years":YEARS,"n":[],"stop":[],"six":[],"win":[],"exp":[]}
    for yr in YEARS:
        sub=[r for r in rows if r["datetime_kst"][:4]==yr and (tf=="전체" or r["TF"]==tf)]
        s=stats(sub) or dict(n=0,stop=0,six=0,win=0,exp=0)
        for k in ["n","stop","six","win","exp"]: DATA[tf][k].append(s[k])

HTML=r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>연도별 수익성 & 손절률</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
 body{font-family:'Segoe UI','Malgun Gothic',sans-serif;background:#f7f7f8;margin:0;padding:24px;color:#222}
 .card{background:#fff;border:1px solid #eee;border-radius:16px;padding:22px;box-shadow:0 1px 6px rgba(0,0,0,.05);max-width:920px;margin:auto}
 h1{font-size:20px;margin:0 0 4px}.sub{color:#888;font-size:13px;margin-bottom:16px}
 .ctrl{display:flex;gap:20px;margin-bottom:14px;flex-wrap:wrap}
 .ctrl label{font-size:12px;color:#999;display:block;margin-bottom:4px}
 select{padding:7px 12px;border:1px solid #ddd;border-radius:9px;font-size:14px;background:#fff}
 table{border-collapse:collapse;width:100%;margin-top:18px;font-size:13px}
 th,td{padding:7px 9px;text-align:center;border-bottom:1px solid #f0f0f0}
 th{color:#999;font-weight:600}td.lab{text-align:left;font-weight:600}
 .note{color:#999;font-size:12px;margin-top:14px;line-height:1.6}
 .leg{display:flex;gap:16px;font-size:12px;color:#666;margin-bottom:8px}
 .leg span{display:flex;align-items:center;gap:5px}.sw{width:11px;height:11px;border-radius:2px}
</style></head><body><div class="card">
<h1>📉 연도별 수익성 & 손절률 (TP 2배수, 등량 랏, KTR)</h1>
<div class="sub">회복폭 차트의 짝 — "돈을 버나 / 국면 위험"을 봄. 막대=기대값(R=base), 선=손절률(%)</div>
<div class="ctrl"><div><label>타임프레임</label><select id="tf"></select></div></div>
<div class="leg"><span><span class="sw" style="background:#5dcaa5"></span>기대값(R=base, 좌축)</span>
 <span><span class="sw" style="background:#e24b4a"></span>손절률 %(우축)</span></div>
<canvas id="ch" height="150"></canvas>
<table id="tbl"></table>
<div class="note">· 기대값 R=base (1 KTR 단위), 등량 랏·익절 2배수·손절 -15.5R 기준<br>
· 연도별로 손절률은 비슷해도 기대값은 크게 갈림 → '평균 안정'의 함정 보정용</div>
</div>
<script>
const DATA=__DATA__;const tf=document.getElementById('tf');
Object.keys(DATA).forEach(t=>tf.add(new Option(t,t)));
let chart;
function draw(){
 const d=DATA[tf.value];
 if(chart)chart.destroy();
 chart=new Chart(document.getElementById('ch'),{data:{labels:d.years,datasets:[
   {type:'bar',label:'기대값(R)',data:d.exp,backgroundColor:'#5dcaa5',borderRadius:5,yAxisID:'y',order:2},
   {type:'line',label:'손절률%',data:d.stop,borderColor:'#e24b4a',backgroundColor:'#e24b4a',pointRadius:4,yAxisID:'y1',order:1,tension:.2}
 ]},options:{responsive:true,plugins:{legend:{display:false},
   tooltip:{callbacks:{afterBody:it=>{const i=it[0].dataIndex;return `n=${d.n[i]}  승률 ${d.win[i]}%  6차 ${d.six[i]}%`;}}}},
   scales:{y:{title:{display:true,text:'기대값 (R=base)'},beginAtZero:true},
           y1:{position:'right',title:{display:true,text:'손절률 %'},beginAtZero:true,grid:{drawOnChartArea:false}}}}});
 let h='<tr><th>연도</th><th>n</th><th>손절%</th><th>6차%</th><th>승률%</th><th>기대값(R)</th></tr>';
 d.years.forEach((y,i)=>{h+=`<tr><td class="lab">${y}</td><td>${d.n[i]}</td><td>${d.stop[i]}%</td>`
   +`<td>${d.six[i]}%</td><td>${d.win[i]}%</td><td>${d.exp[i]>=0?'+':''}${d.exp[i]}</td></tr>`;});
 document.getElementById('tbl').innerHTML=h;
}
tf.onchange=draw;draw();
</script></body></html>"""
open(OUT,"w",encoding="utf-8").write(HTML.replace("__DATA__",json.dumps(DATA,ensure_ascii=False)))
print(f"생성: {OUT}")
for tf in TFS:
    d=DATA[tf]
    print(f"[{tf}] 기대값(R): "+" ".join(f"{y}={e:+.2f}" for y,e in zip(d['years'],d['exp']))+
          f" / 손절%: "+" ".join(f"{s}" for s in d['stop']))
