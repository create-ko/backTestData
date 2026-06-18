# -*- coding: utf-8 -*-
"""
14_tf_level_chart.py
ktr_takeprofit_N -> 단계 × TF × 연도별 도달수익(KTR) 집계
-> 인터랙티브 HTML(tf_level_chart.html). 토글: base / 측정 / 지표 / 연도.
"""
import csv, json, sys
from collections import defaultdict

SRC = sys.argv[1] if len(sys.argv) > 1 else "ktr_takeprofit_N_all_tf_2010-01-01_2026-06-16.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "tf_level_chart.html"
LAB_ORDER = ["바로출발","1번눌림","2번눌림","3번눌림","4번눌림","6차"]
LAB_KTR = {"바로출발":"0","1번눌림":"-1","2번눌림":"-2","3번눌림":"-3","4번눌림":"-4","6차":"-4.5"}
MEAS = {"트레일(결국 얼마나)":"최대도달R_트레일1base"}
TFS = ["2m","5m","10m"]
YEARS = ["전체","2020","2021","2022","2023","2024","2025","2026"]
THR = [1,2,3,4,5]
WICKS = [("전체",None),("≤0.1",0.1),("≤0.2",0.2),("≤0.3",0.3)]

rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8-sig")) if r["손절여부"]=="No"]
for r in rows: r["_y"]=r["datetime_kst"][:4]; r["_w"]=float(r["꼬리비율"])

def agg(v):
    if not v: return None
    s=sorted(v); n=len(v)
    d=dict(n=n, avg=round(sum(v)/n,2), med=round(s[n//2],2), mx=round(max(v),2))
    for t in THR: d[f"ge{t}"]=round(100*sum(1 for x in v if x>=t)/n)
    return d

DATA={}
for mname,col in MEAS.items():
    DATA[mname]={}
    for base in ["KTR","BREAKOUT"]:
        DATA[mname][base]={}
        for wlabel,wthr in WICKS:
            DATA[mname][base][wlabel]={}
            for yr in YEARS:
                bk=defaultdict(list)
                for r in rows:
                    if r["base종류"]!=base: continue
                    if yr!="전체" and r["_y"]!=yr: continue
                    if wthr is not None and r["_w"]>wthr: continue
                    bk[(r["TF"],r["단계라벨"])].append(float(r[col]))
                labels=[]; tfobj={tf:dict(n=[],avg=[],med=[],max=[],**{f"ge{t}":[] for t in THR}) for tf in TFS}
                for lab in LAB_ORDER:
                    if not any(bk.get((tf,lab)) for tf in TFS): continue
                    labels.append(f"{lab}({LAB_KTR[lab]})")
                    for tf in TFS:
                        a=agg(bk.get((tf,lab),[])); o=tfobj[tf]
                        o["n"].append(a["n"] if a else 0); o["avg"].append(a["avg"] if a else None)
                        o["med"].append(a["med"] if a else None); o["max"].append(a["mx"] if a else None)
                        for t in THR: o[f"ge{t}"].append(a[f"ge{t}"] if a else None)
                DATA[mname][base][wlabel][yr]=dict(labels=labels,tfs=tfobj)

HTML=r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>단계 × TF × 연도 도달수익 (KTR)</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
 body{font-family:'Segoe UI','Malgun Gothic',sans-serif;background:#f7f7f8;margin:0;padding:24px;color:#222}
 .card{background:#fff;border:1px solid #eee;border-radius:16px;padding:22px;box-shadow:0 1px 6px rgba(0,0,0,.05);max-width:1000px;margin:auto}
 h1{font-size:20px;margin:0 0 4px}.sub{color:#888;font-size:13px;margin-bottom:16px}
 .ctrl{display:flex;gap:20px;margin-bottom:14px;flex-wrap:wrap}
 .ctrl label{font-size:12px;color:#999;display:block;margin-bottom:4px}
 select{padding:7px 12px;border:1px solid #ddd;border-radius:9px;font-size:14px;background:#fff}
 table{border-collapse:collapse;width:100%;margin-top:18px;font-size:12.5px}
 th,td{padding:6px 8px;text-align:center;border-bottom:1px solid #f0f0f0}
 th{color:#999;font-weight:600}td.lab{text-align:left;font-weight:600}
 tr.sep td{border-top:2px solid #eee}
 .note{color:#999;font-size:12px;margin-top:14px;line-height:1.6}.lown{color:#c00}
</style></head><body><div class="card">
<h1>📊 반등 단계 × 분봉 × 연도별 도달수익 (ktr)</h1>
<div class="sub">반등 후 바닥 기준 도달 수익폭 — 분봉·연도별 비교 (손절 제외)</div>
<div class="ctrl">
 <div><label>연도</label><select id="year"></select></div>
 <div><label>분봉</label><select id="tfsel"><option>전체</option><option>2m</option><option>5m</option><option>10m</option></select></div>
 <div><label>꼬리필터</label><select id="wick"><option>전체</option><option>≤0.1</option><option>≤0.2</option><option>≤0.3</option></select></div>
 <div><label>base</label><select id="base"><option>KTR</option><option>BREAKOUT</option></select></div>
 <div><label>지표</label><select id="metric"><option value="avg">평균</option><option value="med">중앙값</option><option value="max">최대</option></select></div>
</div>
<canvas id="ch" height="150"></canvas>
<table id="tbl"></table>
<div class="note">· 막대 = 단계별 2m·5m·10m 비교 · 괄호 = 그리드 바닥 위치(ktr) · <span class="lown">빨강 n</span> = 표본 30 미만<br>
· 연도를 바꾸면 국면별(2020 코로나·2022 추세장 등) 회복폭 변화를 볼 수 있음</div>
</div>
<script>
const DATA=__DATA__;const TFS=["2m","5m","10m"];const COL={"2m":"#ffce4d","5m":"#7fb2ff","10m":"#5dcaa5"};const THR=__THR__;
const YEARS=__YEARS__;
const year=document.getElementById('year'),tfsel=document.getElementById('tfsel'),wick=document.getElementById('wick'),base=document.getElementById('base'),metric=document.getElementById('metric');
const MEASKEY=Object.keys(DATA)[0];
YEARS.forEach(y=>year.add(new Option(y,y)));
let chart;
function draw(){
 const d=DATA[MEASKEY][base.value][wick.value][year.value],mt=metric.value;
 const showTFs = tfsel.value==='전체' ? TFS : [tfsel.value];
 if(chart)chart.destroy();
 chart=new Chart(document.getElementById('ch'),{type:'bar',
  data:{labels:d.labels,datasets:showTFs.map(tf=>({label:tf,data:d.tfs[tf][mt],backgroundColor:COL[tf],borderRadius:4}))},
  options:{responsive:true,plugins:{legend:{position:'top'},
    tooltip:{callbacks:{afterBody:it=>{const i=it[0].dataIndex,tf=showTFs[it[0].datasetIndex];const o=d.tfs[tf];
      return 'n='+o.n[i]+'  평균 '+o.avg[i]+'  '+THR.map(t=>'≥'+t+':'+(o['ge'+t][i]??'-')+'%').join(' ');}}}},
   scales:{y:{title:{display:true,text:'도달수익 (ktr)'},beginAtZero:true,grace:'8%'}}}});
 let h='<tr><th>단계</th><th>TF</th><th>n</th><th>평균</th><th>중앙</th><th>최대</th>'+THR.map(t=>'<th>≥'+t+'</th>').join('')+'</tr>';
 d.labels.forEach((l,i)=>{showTFs.forEach((tf,j)=>{const o=d.tfs[tf];const low=o.n[i]<30?' class="lown"':'';
   h+=`<tr${j===0?' class="sep"':''}><td class="lab">${j===0?l:''}</td><td>${tf}</td>`
    +`<td${low}>${o.n[i]}</td><td>${o.avg[i]??'-'}</td><td>${o.med[i]??'-'}</td><td>${o.max[i]??'-'}</td>`
    +THR.map(t=>'<td>'+(o['ge'+t][i]??'-')+'%</td>').join('')+'</tr>';});});
 document.getElementById('tbl').innerHTML=h;
}
[year,tfsel,wick,base,metric].forEach(s=>s.onchange=draw);draw();
</script></body></html>"""
out = HTML.replace("__DATA__", json.dumps(DATA, ensure_ascii=False)).replace("__YEARS__", json.dumps(YEARS, ensure_ascii=False)).replace("__THR__", json.dumps(THR))
open(OUT,"w",encoding="utf-8").write(out)
print(f"생성: {OUT}")
# 콘솔: 연도별 0차(바로출발) 평균 도달 (KTR/트레일, 전체TF 합산은 따로)
print("\n바로출발(0차) 연도별 평균 도달 KTR (KTR base, 트레일):")
print("  연도   " + "".join(f"{tf:>10}" for tf in TFS))
for yr in YEARS[1:]:
    dd=DATA["트레일(결국 얼마나)"]["KTR"]["전체"][yr]
    if not dd["labels"] or dd["labels"][0][:4]!="바로출발":
        # 바로출발이 첫 라벨이 아닐 수 있어 인덱스 탐색
        pass
    idx=next((k for k,l in enumerate(dd["labels"]) if l.startswith("바로출발")), None)
    if idx is None: continue
    print(f"  {yr} " + "".join(f"{str(dd['tfs'][tf]['avg'][idx])+'('+str(dd['tfs'][tf]['n'][idx])+')':>10}" for tf in TFS))
