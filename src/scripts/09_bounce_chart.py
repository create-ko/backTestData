# -*- coding: utf-8 -*-
"""
09_bounce_chart.py
ktr_takeprofit_N(반등=손절제외) -> 단계별 도달수익(ktr) 집계 (KTR & BREAKOUT 둘 다)
-> 자체완결 인터랙티브 HTML(bounce_chart.html). 토글: 측정 / TF / 지표(평균·중앙·최대)
   차트는 단일축에 KTR vs BREAKOUT 두 막대만 -> 보기 쉬움. 막대 위 값 표시.
"""
import csv, json
from collections import defaultdict

SRC = "ktr_takeprofit_N_all_tf_2020-01-01_2026-06-16.csv"
OUT = "bounce_chart.html"
LAB_ORDER = ["바로출발", "1번눌림", "2번눌림", "3번눌림", "4번눌림", "6차"]
LAB_KTR = {"바로출발":"0","1번눌림":"-1","2번눌림":"-2","3번눌림":"-3","4번눌림":"-4","6차":"-4.5"}
MEAS = {"트레일(결국 얼마나)":"최대도달R_트레일1base", "본전복귀(보수)":"최대도달R_본전복귀"}

rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8-sig")) if r["손절여부"] == "No"]

def agg(vals):
    if not vals: return None
    s = sorted(vals)
    return dict(n=len(vals), avg=round(sum(vals)/len(vals),2),
                med=round(s[len(s)//2],2), mx=round(max(vals),2))

DATA = {}
for mname, col in MEAS.items():
    DATA[mname] = {}
    for tf in ["전체","2m","5m","10m"]:
        bk = {"KTR": defaultdict(list), "BREAKOUT": defaultdict(list)}
        for r in rows:
            if tf != "전체" and r["TF"] != tf: continue
            bk[r["base종류"]][r["단계라벨"]].append(float(r[col]))
        labels=[]; out={"KTR":{"n":[],"avg":[],"med":[],"max":[]},
                        "BREAKOUT":{"n":[],"avg":[],"med":[],"max":[]}}
        for lab in LAB_ORDER:
            ak, ab = agg(bk["KTR"].get(lab,[])), agg(bk["BREAKOUT"].get(lab,[]))
            if not ak and not ab: continue
            labels.append(f"{lab} ({LAB_KTR[lab]}ktr)")
            for base, a in [("KTR",ak),("BREAKOUT",ab)]:
                out[base]["n"].append(a["n"] if a else 0)
                out[base]["avg"].append(a["avg"] if a else None)
                out[base]["med"].append(a["med"] if a else None)
                out[base]["max"].append(a["mx"] if a else None)
        DATA[mname][tf] = dict(labels=labels, **out)

HTML = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>반등 단계별 도달 수익 — KTR vs BREAKOUT</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<style>
 body{font-family:'Segoe UI','Malgun Gothic',sans-serif;background:#f7f7f8;margin:0;padding:24px;color:#222}
 .card{background:#fff;border:1px solid #eee;border-radius:16px;padding:22px;box-shadow:0 1px 6px rgba(0,0,0,.05);max-width:980px;margin:auto}
 h1{font-size:20px;margin:0 0 4px}.sub{color:#888;font-size:13px;margin-bottom:18px}
 .ctrl{display:flex;gap:22px;margin-bottom:14px;flex-wrap:wrap}
 .ctrl label{font-size:12px;color:#999;display:block;margin-bottom:4px}
 select{padding:7px 12px;border:1px solid #ddd;border-radius:9px;font-size:14px;background:#fff}
 table{border-collapse:collapse;width:100%;margin-top:20px;font-size:13px}
 th,td{padding:7px 9px;text-align:center;border-bottom:1px solid #f0f0f0}
 th{color:#999;font-weight:600}td.lab{text-align:left;font-weight:600}
 .k{color:#e0a400}.b{color:#3b82f6}
 .note{color:#999;font-size:12px;margin-top:14px;line-height:1.6}
</style></head><body><div class="card">
<h1>📊 반등 단계별 도달 수익 (ktr) — KTR vs BREAKOUT</h1>
<div class="sub">바로출발·N번눌림 후 출발 시 바닥에서 도달한 수익폭 (2020~2026, 반등=손절 제외)</div>
<div class="ctrl">
 <div><label>지표</label><select id="metric"><option value="avg">평균</option><option value="med">중앙값</option><option value="max">최대</option></select></div>
 <div><label>측정</label><select id="meas"></select></div>
 <div><label>타임프레임</label><select id="tf"></select></div>
</div>
<canvas id="ch" height="135"></canvas>
<table id="tbl"></table>
<div class="note">· <b class="k">KTR</b> = 세션 KTR 기준 그리드 · <b class="b">BREAKOUT</b> = 돌파캔들크기 기준 그리드<br>
· x축 = 반등이 일어난 단계(괄호=그리드 바닥 위치, ktr) · y축 = 바닥 기준 도달 수익(ktr)<br>
· 깊은 단계는 표본이 적음(막대 위 n 확인) → 평균 해석 주의</div>
</div>
<script>
const DATA=__DATA__;
const metric=document.getElementById('metric'),meas=document.getElementById('meas'),tf=document.getElementById('tf');
Object.keys(DATA).forEach(m=>meas.add(new Option(m,m)));
['전체','2m','5m','10m'].forEach(t=>tf.add(new Option(t,t)));
Chart.register(ChartDataLabels);
let chart;
function draw(){
 const d=DATA[meas.value][tf.value],mt=metric.value;
 if(chart)chart.destroy();
 chart=new Chart(document.getElementById('ch'),{type:'bar',
  data:{labels:d.labels,datasets:[
   {label:'KTR',data:d.KTR[mt],backgroundColor:'#ffce4d',borderRadius:5},
   {label:'BREAKOUT',data:d.BREAKOUT[mt],backgroundColor:'#7fb2ff',borderRadius:5}]},
  options:{responsive:true,plugins:{legend:{position:'top'},
    datalabels:{anchor:'end',align:'end',font:{size:11,weight:'600'},formatter:v=>v==null?'':v},
    tooltip:{callbacks:{afterBody:it=>{const i=it[0].dataIndex;return 'n(KTR)='+d.KTR.n[i]+'  n(BRK)='+d.BREAKOUT.n[i];}}}},
   scales:{y:{title:{display:true,text:'도달 수익 (ktr)'},beginAtZero:true,grace:'12%'}}}});
 let h='<tr><th>단계 (바닥)</th><th class="k">KTR 평균</th><th class="k">중앙</th><th class="k">최대</th><th class="k">n</th>'
      +'<th class="b">BRK 평균</th><th class="b">중앙</th><th class="b">최대</th><th class="b">n</th></tr>';
 d.labels.forEach((l,i)=>{h+=`<tr><td class="lab">${l}</td>`
   +`<td>${d.KTR.avg[i]??'-'}</td><td>${d.KTR.med[i]??'-'}</td><td>${d.KTR.max[i]??'-'}</td><td>${d.KTR.n[i]}</td>`
   +`<td>${d.BREAKOUT.avg[i]??'-'}</td><td>${d.BREAKOUT.med[i]??'-'}</td><td>${d.BREAKOUT.max[i]??'-'}</td><td>${d.BREAKOUT.n[i]}</td></tr>`;});
 document.getElementById('tbl').innerHTML=h;
}
[metric,meas,tf].forEach(s=>s.onchange=draw);draw();
</script></body></html>"""

open(OUT, "w", encoding="utf-8").write(HTML.replace("__DATA__", json.dumps(DATA, ensure_ascii=False)))
print(f"생성: {OUT}")
d = DATA["트레일(결국 얼마나)"]["전체"]
print("전체/트레일 — 단계별 평균 도달수익 (KTR / BREAKOUT):")
for i,l in enumerate(d["labels"]):
    print(f"  {l}: KTR 평균 {d['KTR']['avg'][i]}(n={d['KTR']['n'][i]}) / BRK 평균 {d['BREAKOUT']['avg'][i]}(n={d['BREAKOUT']['n'][i]})")
