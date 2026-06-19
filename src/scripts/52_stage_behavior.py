# -*- coding: utf-8 -*-
"""52 (Step1) - TP-free 가격행동 통계. 연도별 + 최대깊이별.
각 신호의 그리드를 '익절(TP) 없이' 굴려, 진입가 기준 최대 유리도달(MFE)과 손절(-5)/생존을 본다.
종료규칙(측정용, 전략 TP 아님): 유리쪽 고점에서 1.0*base 되밀리면 종료 / -5 풀스톱 / 데이터끝.
=> '엣지(되돌림 반등)가 어느 해에 살아있나', '깊이별로 얼마나 가나'를 TP 선택값 없이 본다.
지표(진입가 기준, base=KTR): 손절% / 진입가복귀%(MFE>0) / 강한반등%(MFE>=1.5) / MFE중앙.
v1=전 신호 즉시진입, v2=돌파후 BB2 풀백. 콘솔 ASCII만(규칙3). 출력: ../result/stage_behavior.html"""
import csv, math, json, time

MULT=[0,1,2,3,4,4.5]; STOPM=5.0; TRAIL=1.0
LABD={0:"바로출발",1:"1번눌림",2:"2번눌림",3:"3번눌림",4:"4번눌림",5:"6차"}

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
def boll(src,length,m):
    n=len(src); up=[None]*n; lo=[None]*n; s=ss=0.0
    for i in range(n):
        v=src[i]; s+=v; ss+=v*v
        if i>=length: rm=src[i-length]; s-=rm; ss-=rm*rm
        if i>=length-1:
            mean=s/length; var=ss/length-mean*mean
            if var<0: var=0.0
            d=m*math.sqrt(var); up[i]=mean+d; lo[i]=mean-d
    return up,lo
def calib(tf):
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def kyear(e,off):
    e=e//1000 if e>1e11 else e
    return time.strftime("%Y",time.gmtime(e+off*3600))

def trace_b(bars,eb,a,d,base):
    n=len(bars)
    if eb>=n or base<=0: return ("OPEN",0,0.0)
    if d=="LONG": E=[a-base*m for m in MULT]; stop=a-base*STOPM
    else:         E=[a+base*m for m in MULT]; stop=a+base*STOPM
    filled=[False]*6; filled[0]=True; maxd=0; mfeE=0.0
    i=eb
    while i<n:
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((d=="LONG" and l<=E[k]) or (d=="SHORT" and h>=E[k])): filled[k]=True
        maxd=max(k for k in range(6) if filled[k])
        fav=(h-a)/base if d=="LONG" else (a-l)/base
        if fav>mfeE: mfeE=fav
        if (d=="LONG" and l<=stop) or (d=="SHORT" and h>=stop): return ("STOP",maxd,mfeE)
        if mfeE>=TRAIL:
            if (d=="LONG" and l<=a+(mfeE-TRAIL)*base) or (d=="SHORT" and h>=a-(mfeE-TRAIL)*base):
                return ("EXIT",maxd,mfeE)
        i+=1
    return ("OPEN",maxd,mfeE)

def v1_entries(tf,bars,idx,off):
    out=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8]) if s[8] else 0.0
            if k>0: out.append((bi+1,float(s[7]),s[4],k))
    return out
def v2_entries(tf,bars,idx,off):
    u2,l2=boll([b[1] for b in bars],4,4.0); brkd={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brkd[bi]=s
    out=[]; pending=None
    for i in range(len(bars)):
        if i in brkd: pending=(i,brkd[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                eb=i+1
                if eb<len(bars):
                    k=float(ps[8]) if ps[8] else 0.0
                    if k>0: out.append((eb,bars[eb][1],pdir,k))
                pending=None
    return out
def med(v): s=sorted(v); return round(s[len(s)//2],2) if s else 0.0

YEARS=[str(y) for y in range(2010,2027)]
DATA={}
for ver,efn in [("v1",v1_entries),("v2",v2_entries)]:
    DATA[ver]={}
    print(f"\n{'#'*64}\n## {ver}")
    for tf in ["2m","5m","10m"]:
        bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); off=calib(tf)
        ents=efn(tf,bars,idx,off)
        yr={y:{"n":0,"stop":0,"back":0,"strong":0,"mfe":[]} for y in YEARS}
        dp={k:{"n":0,"stop":0,"mfe":[]} for k in range(6)}
        for eb,a,d,k in ents:
            oc,maxd,mfeE=trace_b(bars,eb,a,d,k)
            y=kyear(bars[eb][0],off)
            if y not in yr: continue
            R=yr[y]; R["n"]+=1
            if oc=="STOP": R["stop"]+=1
            if mfeE>0: R["back"]+=1
            if mfeE>=1.5: R["strong"]+=1
            R["mfe"].append(mfeE)
            D=dp[maxd]; D["n"]+=1; D["mfe"].append(mfeE)
            if oc=="STOP": D["stop"]+=1
        yrows=[]
        for y in YEARS:
            R=yr[y]; n=R["n"]
            if n==0: yrows.append([y,0,0,0,0,0]); continue
            yrows.append([y,n,round(100*R["stop"]/n,1),round(100*R["back"]/n,1),
                          round(100*R["strong"]/n,1),med(R["mfe"])])
        drows=[]
        for kk in range(6):
            D=dp[kk]; n=D["n"]
            drows.append([LABD[kk],n,round(100*D["stop"]/n,1) if n else 0,med(D["mfe"])])
        DATA[ver][tf]={"years":yrows,"depths":drows,"total":len(ents)}
        print(f"\n=== {tf} (진입 {len(ents)}) - 연도별 [년 n 손절% 진입가복귀% 강한반등(MFE>=1.5)% MFE중앙] ===")
        for r in yrows:
            if r[1]==0: print(f"{r[0]} -"); continue
            print(f"{r[0]} n={r[1]:>6} stop={r[2]:>5.1f}% back={r[3]:>5.1f}% strong={r[4]:>5.1f}% MFEmed={r[5]:>5.2f}")
        print(f"  [최대깊이별] " + " | ".join(f"{r[0]} n={r[1]} stop={r[2]}% MFE={r[3]}" for r in drows))

HTML="""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Step1 - 가격행동 연도별 통계 (TP-free)</title>
<style>
*{box-sizing:border-box}
body{font-family:'Malgun Gothic','Segoe UI',sans-serif;background:#0f1320;color:#dfe6f0;margin:0;line-height:1.6}
.wrap{max-width:980px;margin:0 auto;padding:24px}
h1{color:#4fc3f7;font-size:1.5em;margin:0 0 4px;text-align:center}
.date{text-align:center;color:#7e8aa0;font-size:.82em;margin-bottom:16px}
h2{color:#7fd4ff;font-size:1.05em;margin:20px 0 6px}
p,li{font-size:.9em;color:#c4cfde}
.box{background:#15203a;border:1px solid #2a3e63;border-radius:10px;padding:12px 16px;margin:12px 0}
.ctl{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0;align-items:center}
.ctl .lbl{color:#7e8aa0;font-size:.8em;margin-right:4px}
.btn{padding:6px 14px;border:1px solid #345;background:transparent;color:#9cf;border-radius:6px;cursor:pointer;font-size:.85em}
.btn.on{background:#4fc3f7;color:#0f1320;font-weight:bold}
table{width:100%;border-collapse:collapse;font-size:.84em;margin:6px 0}
th,td{padding:6px 8px;text-align:right;border-bottom:1px solid #243150}
th{color:#9cc4e8;background:#16203a}
td:first-child,th:first-child{text-align:left;font-weight:bold}
.note{font-size:.8em;color:#8493a8;font-style:italic;margin-top:6px}
.good{color:#5fd97e}.bad{color:#ff6f6f}.warn{color:#ffcf5c}b{color:#fff}
</style></head><body><div class=wrap>
<h1>Step 1 · 가격 행동 연도별 통계 (TP 없음)</h1>
<div class=date>2010-2026 · 그리드를 TP 없이 굴림(종료=고점서 1.0 되밀림/-5스톱) · 진입가 기준 · KTR base</div>
<div class=box>
<p>TP(1.5) 같은 선택값을 빼고 <b>가격이 실제로 어떻게 움직이나</b>만 봅니다. 지표(진입가 기준):</p>
<ul>
<li><b>손절%</b>: -5 풀스톱 비율(낮을수록 좋음, 꼬리위험)</li>
<li><b>진입가복귀%</b>: 진입가 위로 한 번이라도 올라온 비율(되돌림 반등이 작동했나)</li>
<li><b class=good>강한반등%</b>: 진입가 위로 <b>1.5KTR 이상</b> 간 비율(엣지가 굵었나)</li>
<li><b>MFE중앙</b>: 진입가 기준 최고 도달의 중앙값</li>
</ul>
<p class=note>※ 이건 '행동(사실)'이라 usability 판정은 아님 — 판정은 Step2(비용+순차+복리 net/MDD).</p>
</div>
<div class=ctl><span class=lbl>진입</span><span id=versel></span><span class=lbl style="margin-left:10px">분봉</span><span id=tfsel></span></div>
<h2>연도별</h2>
<table id=yt></table>
<h2>최대 체결 깊이별 (전 기간 합산)</h2>
<table id=dt></table>
<script>
const D=__DATA__;
let ver='v1',tf='10m';
function mk(host,opts,cur,cb){const h=document.getElementById(host);h.innerHTML='';opts.forEach(o=>{const b=document.createElement('button');b.className='btn'+(o[0]===cur()?' on':'');b.textContent=o[1];b.onclick=()=>{cb(o[0]);render()};h.appendChild(b)})}
function render(){
 mk('versel',[['v1','v1 즉시'],['v2','v2 풀백']],()=>ver,v=>ver=v);
 mk('tfsel',[['2m','2분'],['5m','5분'],['10m','10분']],()=>tf,v=>tf=v);
 const dd=D[ver][tf];
 let h='<tr><th>연도</th><th>건수</th><th>손절%</th><th>진입가복귀%</th><th>강한반등%<br>(MFE≥1.5)</th><th>MFE중앙</th></tr>';
 dd.years.forEach(r=>{if(!r[1]){h+=`<tr><td>${r[0]}</td><td colspan=5 style="text-align:left;color:#7e8aa0">-</td></tr>`;return;}
  const sc=r[2]>10?'bad':(r[2]>6?'warn':'good');
  h+=`<tr><td>${r[0]}</td><td>${r[1].toLocaleString()}</td><td class=${sc}>${r[2]}%</td><td>${r[3]}%</td><td class=good>${r[4]}%</td><td>+${r[5]}</td></tr>`;});
 document.getElementById('yt').innerHTML=h;
 let h2='<tr><th>최대 깊이</th><th>건수</th><th>손절%</th><th>MFE중앙(진입가기준)</th></tr>';
 dd.depths.forEach(r=>{h2+=`<tr><td>${r[0]}</td><td>${r[1].toLocaleString()}</td><td class=${r[2]>10?'bad':''}>${r[2]}%</td><td>+${r[3]}</td></tr>`;});
 document.getElementById('dt').innerHTML=h2;
}
render();
</script>
</div></body></html>"""
with open("../result/stage_behavior.html","w",encoding="utf-8") as f:
    f.write(HTML.replace("__DATA__",json.dumps(DATA,ensure_ascii=False)))
print("\n-> ../result/stage_behavior.html")
