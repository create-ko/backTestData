# -*- coding: utf-8 -*-
"""53 (Step2) - 출구 규칙 3종 실거래 비교. usability 판정용(net+MDD+복리, 39와 동일 틀).
규칙(공통: 후방 1·1·2·2·3·4 / -5 풀스톱 / 6차 반등+1.0 / 순차 1개씩 / KST08~24 진입 / 비용$0.30 / 리스크2% 복리):
  fixed  = 가장 깊은 체결 +1.5KTR 익절 (현 확정안)
  trail  = +1.5 도달(arm) 후 고점에서 1.0KTR 되밀리면 익절 (승자 더 태움)
  level0 = 눌렸으면(>=1차) 첫 진입가 복귀 시 익절 / 안 눌렸으면 +1.5 (본전 청산 가설)
출력: 분봉×v1/v2×규칙 연도별 net수익%·MDD + 전체 net R·CAGR·MDD·승률. 콘솔 ASCII만(규칙3).
검증: fixed가 39(10m v1 CAGR~2.6%/MDD63%)와 일치해야 함. 출력: ../result/exit_compare.html"""
import csv, math, json, time
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6=1.0; STOPM=5.0; TRAIL=1.0
SUM_L=sum(L); STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))  # 24
SPREAD=0.30; RISK=0.02; START_H=8
RULES=["fixed","trail","level0"]

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
def calib(tf,bars,idx):
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def khour(e,off): e=e//1000 if e>1e11 else e; return ((e//3600)+off)%24
def kyear(e,off): e=e//1000 if e>1e11 else e; return time.strftime("%Y",time.gmtime(e+off*3600))
def data_span_years(bars):
    e0=bars[0][0]; e1=bars[-1][0]
    if e1>1e11: e0/=1000; e1/=1000
    return (e1-e0)/(365.25*86400)
def maxdd(eq):
    peak=eq[0]; m=0.0
    for v in eq:
        if v>peak: peak=v
        d=(peak-v)/peak
        if d>m: m=d
    return 100*m

def sim_rule(bars, si, anchor, d, base, rule):
    n=len(bars); LONG=(d=="LONG")
    E=[anchor-base*m if LONG else anchor+base*m for m in MULT]
    stop=anchor-base*STOPM if LONG else anchor+base*STOPM
    filled=[False]*6; filled[0]=True
    peak=-1e18 if LONG else 1e18; armed=False
    for i in range(si,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((LONG and l<=E[k]) or ((not LONG) and h>=E[k])): filled[k]=True
        last=max(k for k in range(6) if filled[k]); lvls=last+1
        deepest=E[last]
        peak=max(peak,h) if LONG else min(peak,l)
        if (LONG and l<=stop) or ((not LONG) and h>=stop):
            return i,6,-STOPM,"STOP"
        if last==5:   # 6차: 반등 +1.0 탈출(공통)
            b6=deepest+B6*base if LONG else deepest-B6*base
            if (LONG and h>=b6) or ((not LONG) and l<=b6):
                e=(b6-anchor)/base if LONG else (anchor-b6)/base
                return i,6,e,"B6"
            continue
        tp=deepest+TP*base if LONG else deepest-TP*base
        reached=(LONG and h>=tp) or ((not LONG) and l<=tp)
        if rule=="fixed":
            if reached:
                e=(tp-anchor)/base if LONG else (anchor-tp)/base
                return i,lvls,e,"TP"
        elif rule=="level0":
            if last>=1:
                if (LONG and h>=anchor) or ((not LONG) and l<=anchor): return i,lvls,0.0,"L0"
            elif reached:
                e=(tp-anchor)/base if LONG else (anchor-tp)/base
                return i,lvls,e,"TP"
        elif rule=="trail":
            if reached: armed=True
            if armed:
                tr=peak-TRAIL*base if LONG else peak+TRAIL*base
                if (LONG and l<=tr) or ((not LONG) and h>=tr):
                    e=(tr-anchor)/base if LONG else (anchor-tr)/base
                    return i,lvls,e,"TR"
    last=max(k for k in range(6) if filled[k])
    return n-1,last+1,0.0,"OPEN"

def trade_R(lvls,e):
    pnl=sum(L[i]*(e+MULT[i]) for i in range(lvls)); lots=sum(L[:lvls])
    return pnl/STOP_R, lots

def entries_v1(tf,bars,idx):
    out=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8]) if s[8] else 0.0
            if k>0: out.append((bi,bi+1,float(s[7]),s[4],k))   # (sigbar, eb, anchor, dir, base)
    out.sort(key=lambda x:x[0]); return out
def entries_v2(tf,bars,idx):
    u2,l2=boll([b[1] for b in bars],4,4.0); brkd={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brkd[bi]=s
    out=[]; pending=None; busyguard=[]
    for i in range(len(bars)):
        if i in brkd: pending=(i,brkd[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                eb=i+1
                if eb<len(bars):
                    k=float(ps[8]) if ps[8] else 0.0
                    if k>0: out.append((i,eb,bars[eb][1],pdir,k))
                pending=None
    out.sort(key=lambda x:x[0]); return out

def run_seq(bars,off,ents,rule,YRS,YEARS):
    netR=[]; yrs=[]; wins=0; busy=-1
    for sb,eb,a,d,k in ents:
        if sb<=busy or eb>=len(bars): continue
        if khour(bars[eb][0],off)<START_H: continue
        ex,lvls,e,kind=sim_rule(bars,eb,a,d,k,rule)
        if kind=="OPEN": continue
        gR,lots=trade_R(lvls,e); nR=gR-lots*(SPREAD/k)/STOP_R
        netR.append(nR); yrs.append(kyear(bars[eb][0],off)); busy=ex
        if gR>0: wins+=1
    n=len(netR)
    if n==0: return None
    eq=[1.0]
    for r in netR: eq.append(eq[-1]*(1+RISK*r))
    cum=[0.0]
    for r in netR: cum.append(cum[-1]+r)
    iy={}
    for j,y in enumerate(yrs): iy.setdefault(y,[]).append(j+1)
    rows=[]
    for y in YEARS:
        js=iy.get(y,[])
        if not js: rows.append([y,0,0,0]); continue
        j0,j1=js[0]-1,js[-1]
        rows.append([y,len(js),round(100*(eq[j1]/eq[j0]-1),1),round(maxdd(eq[j0:j1+1]),1)])
    cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100
    return {"n":n,"win":round(100*wins/n,1),"netR":round(cum[-1],1),
            "cagr":round(cagr,1),"mdd":round(maxdd(eq),1),"rows":rows}

YEARS=[str(y) for y in range(2010,2027)]
DATA={}
for ver,efn in [("v1",entries_v1),("v2",entries_v2)]:
    DATA[ver]={}
    print(f"\n{'#'*70}\n## {ver}")
    for tf in ["2m","5m","10m"]:
        bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); off=calib(tf,bars,idx)
        YRS=data_span_years(bars); ents=efn(tf,bars,idx)
        DATA[ver][tf]={}
        print(f"\n=== {tf} (기간 {YRS:.2f}년) ===")
        print(f"{'규칙':<8}{'건수':>7}{'netR':>8}{'CAGR':>8}{'MDD':>8}{'승률':>8}")
        for rule in RULES:
            res=run_seq(bars,off,ents,rule,YRS,YEARS)
            DATA[ver][tf][rule]=res
            if res: print(f"{rule:<8}{res['n']:>7}{res['netR']:>+8.1f}{res['cagr']:>+7.1f}%{res['mdd']:>7.1f}%{res['win']:>7.1f}%")

HTML="""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Step2 - 출구규칙 3종 실거래 비교</title>
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
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
.kpi{flex:1;min-width:150px;background:#15203a;border:1px solid #28395c;border-radius:9px;padding:10px 12px}
.kpi .r{font-size:.8em;color:#9cf;font-weight:bold;margin-bottom:4px}
.kpi .v{font-size:.82em;color:#c4cfde}
table{width:100%;border-collapse:collapse;font-size:.84em;margin:6px 0}
th,td{padding:6px 8px;text-align:right;border-bottom:1px solid #243150}
th{color:#9cc4e8;background:#16203a}
td:first-child,th:first-child{text-align:left;font-weight:bold}
.pos{color:#5fd97e}.neg{color:#ff6f6f}.note{font-size:.8em;color:#8493a8;font-style:italic}
b{color:#fff}
</style></head><body><div class=wrap>
<h1>Step 2 · 출구규칙 3종 실거래 비교</h1>
<div class=date>2010-2026 · 순차+KST08~24+비용$0.30+2%복리 · net 기준(이게 usability 판정)</div>
<div class=box>
<p><b>fixed</b>=가장 깊은 체결 +1.5 익절(현 확정안) · <b>trail</b>=+1.5 도달 후 고점서 1.0 되밀림 익절(승자 더 태움) · <b>level0</b>=눌렸으면 첫 진입가 복귀 시 익절(본전 청산 가설).</p>
<p class=note>승률·평균이 아니라 <b>net CAGR·MDD</b>로 판정. level0는 승률↑이지만 비용·꼬리 때문에 net이 더 나은지가 핵심.</p>
</div>
<div class=ctl><span class=lbl>진입</span><span id=versel></span><span class=lbl style="margin-left:10px">분봉</span><span id=tfsel></span></div>
<div class=kpis id=kpi></div>
<h2>연도별 수익%(net) · 규칙 비교</h2>
<table id=yt></table>
<p class=note id=warn></p>
<script>
const D=__DATA__;const RULES=["fixed","trail","level0"];const RN={fixed:"고정1.5",trail:"트레일",level0:"본전(L0)"};
let ver='v1',tf='10m';
function mk(host,opts,cur,cb){const h=document.getElementById(host);h.innerHTML='';opts.forEach(o=>{const b=document.createElement('button');b.className='btn'+(o[0]===cur()?' on':'');b.textContent=o[1];b.onclick=()=>{cb(o[0]);render()};h.appendChild(b)})}
function render(){
 mk('versel',[['v1','v1 즉시'],['v2','v2 풀백']],()=>ver,v=>ver=v);
 mk('tfsel',[['2m','2분'],['5m','5분'],['10m','10분']],()=>tf,v=>tf=v);
 const dd=D[ver][tf];
 let k='';RULES.forEach(r=>{const x=dd[r];if(!x){k+=`<div class=kpi><div class=r>${RN[r]}</div><div class=v>표본없음</div></div>`;return;}
  const cc=x.cagr>=0?'pos':'neg';
  k+=`<div class=kpi><div class=r>${RN[r]}</div><div class=v>net <b class=${x.netR>=0?'pos':'neg'}>${x.netR>=0?'+':''}${x.netR}R</b> · CAGR <b class=${cc}>${x.cagr>=0?'+':''}${x.cagr}%</b><br>MDD ${x.mdd}% · 승률 ${x.win}% · ${x.n.toLocaleString()}건</div></div>`;});
 document.getElementById('kpi').innerHTML=k;
 const yrs=(dd.fixed||dd.trail||dd.level0).rows.map(r=>r[0]);
 let h='<tr><th>연도</th>'+RULES.map(r=>`<th>${RN[r]}</th>`).join('')+'</tr>';
 yrs.forEach((y,i)=>{h+=`<tr><td>${y}</td>`+RULES.map(r=>{const row=dd[r]&&dd[r].rows[i];if(!row||!row[1])return '<td style="color:#7e8aa0">-</td>';return `<td class=${row[2]>=0?'pos':'neg'}>${row[2]>=0?'+':''}${row[2]}%</td>`;}).join('')+'</tr>';});
 document.getElementById('yt').innerHTML=h;
 document.getElementById('warn').innerHTML='※ MDD가 큰 규칙은 연수익이 좋아도 부적합. level0가 승률 높아도 net CAGR이 fixed보다 낮으면 "본전청산이 낫다"는 착시.';
}
render();
</script>
</div></body></html>"""
with open("../result/exit_compare.html","w",encoding="utf-8") as f:
    f.write(HTML.replace("__DATA__",json.dumps(DATA,ensure_ascii=False)))
print("\n-> ../result/exit_compare.html")
