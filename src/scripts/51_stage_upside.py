# -*- coding: utf-8 -*-
"""51 - 단계별 '진입가 기준 최대상승' + '익절선 초과(놓친 수익)' 분석. base KTR/BREAKOUT 비교.
트레이드를 익절(deepest+1.5*base)에 도달해 '이긴 단계(win_depth)'로 분류하고, 모두 진입가 기준 일관 측정:
  - 진입가 기준 최대상승(base단위): 첫 진입가 대비 실제 최고 도달(익절후에도 보유 가정, 트레일 1.0 되밀림/-5/끝).
  - 익절선 초과분 = (가장깊은체결 기준 최대도달) - 1.5 = mfe_entry + 깊이 - 1.5  (>=0, 단계간 비교 가능).
    '초과>=X' = 초과분이 X 이상인 누적 비율(딱 X가 아니라 X 이상 전부). 오른쪽 칸일수록 작아짐.
base: KTR(세션변동성) vs BREAKOUT(돌파봉 크기). 그리드 간격 기준만 바뀜. 도달값 단위도 그 base.
v1=전 신호 즉시진입, v2=돌파후 BB2 풀백(39동일). 손절(-5)/미청산 제외(이긴 것만). 콘솔 ASCII만(규칙3).
data/에서 실행. 출력: ../result/stage_upside.html"""
import csv, math, json

MULT=[0,1,2,3,4,4.5]; TP=1.5; B6=1.0; STOPM=5.0; TRAIL=1.0
LAB={0:"바로출발",1:"1번눌림",2:"2번눌림",3:"3번눌림",4:"4번눌림",5:"6차(풀)"}
EXC=[0.5,1.0,1.5,2.0]
BASES=["KTR","BREAKOUT"]   # 진입튜플: (eb, a, dir, KTR, BREAKOUT)

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

def trace(bars, eb, a, d, base):
    """(outcome, win_depth, mfe_entry, excess). mfe_entry=진입가 기준 최대유리도달(base단위).
       excess=(가장깊은체결 기준 최대도달)-1.5 = mfe_entry+깊이-1.5 (이긴 경우만,>=0)."""
    n=len(bars)
    if eb>=n or base<=0: return ("OPEN",0,0.0,None)
    if d=="LONG": E=[a-base*m for m in MULT]; stop=a-base*STOPM
    else:         E=[a+base*m for m in MULT]; stop=a+base*STOPM
    filled=[False]*6; filled[0]=True; maxd=0; mfeE=0.0; won=False; wd=None
    i=eb
    while i<n:
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((d=="LONG" and l<=E[k]) or (d=="SHORT" and h>=E[k])): filled[k]=True
        maxd=max(k for k in range(6) if filled[k])
        deepest=E[maxd]
        fav=(h-a)/base if d=="LONG" else (a-l)/base
        if fav>mfeE: mfeE=fav
        thr=TP if maxd<5 else B6
        tpx=deepest+thr*base if d=="LONG" else deepest-thr*base
        if d=="LONG":
            if maxd>=5 and l<=stop: return ("STOP",maxd,mfeE,None)
            if h>=tpx: won=True; wd=maxd; break
        else:
            if maxd>=5 and h>=stop: return ("STOP",maxd,mfeE,None)
            if l<=tpx: won=True; wd=maxd; break
        i+=1
    if not won: return ("OPEN",maxd,mfeE,None)
    j=i
    while j<n:
        _,o,h,l,c=bars[j]
        fav=(h-a)/base if d=="LONG" else (a-l)/base
        if fav>mfeE: mfeE=fav
        if d=="LONG":
            if l<=a+(mfeE-TRAIL)*base or l<=stop: break
        else:
            if h>=a-(mfeE-TRAIL)*base or h>=stop: break
        j+=1
    return ("WIN",wd,mfeE,mfeE+MULT[wd]-TP)

def v1_entries(tf,bars,idx):
    out=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            ktr=float(s[8]) if s[8] else 0.0; brk=float(s[9]) if s[9] else 0.0
            if ktr>0: out.append((bi+1,float(s[7]),s[4],ktr,brk))
    return out
def v2_entries(tf,bars,idx):
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
                    ktr=float(ps[8]) if ps[8] else 0.0; brk=float(ps[9]) if ps[9] else 0.0
                    if ktr>0: out.append((eb,bars[eb][1],pdir,ktr,brk))
                pending=None
    return out

def med(v): s=sorted(v); return s[len(s)//2] if s else 0.0

DATA={b:{} for b in BASES}
for ver,efn in [("v1",v1_entries),("v2",v2_entries)]:
    for b in BASES: DATA[b][ver]={}
    print(f"\n{'#'*64}\n## {ver}")
    for tf in ["2m","5m","10m"]:
        bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
        ents=efn(tf,bars,idx)
        for b,bidx in [("KTR",3),("BREAKOUT",4)]:
            buckets={wd:{"mfeE":[],"exc":[]} for wd in range(6)}
            nstop=nopen=0; tot=0
            for e in ents:
                base=e[bidx]
                if base<=0: continue
                tot+=1
                oc,wd,mfeE,exc=trace(bars,e[0],e[1],e[2],base)
                if oc=="WIN": buckets[wd]["mfeE"].append(mfeE); buckets[wd]["exc"].append(exc)
                elif oc=="STOP": nstop+=1
                else: nopen+=1
            DATA[b][ver][tf]={"_ctx":{"n":tot,"stop":nstop,"open":nopen,
                                      "stop_pct":round(100*nstop/tot,1) if tot else 0}}
            print(f"\n=== {tf} [{b}] (진입 {tot} / 손절 {nstop}={100*nstop/tot if tot else 0:.1f}% / 미청산 {nopen}) ===")
            print(f"{'이긴단계':<10}{'건수':>7}{'진입가기준 최대상승중앙':>24}{'익절선초과중앙':>16}  " + "  ".join(f">={e}" for e in EXC))
            for wd in range(6):
                bk=buckets[wd]; n=len(bk["mfeE"]); dd={"n":n}
                if n:
                    dd["mfeE_med"]=round(med(bk["mfeE"]),2); dd["exc_med"]=round(med(bk["exc"]),2)
                    for e in EXC: dd[f"exc{e}"]=round(100*sum(1 for x in bk["exc"] if x>=e)/n,1)
                    print(f"{LAB[wd]:<10}{n:>7}{dd['mfeE_med']:>21.2f}{dd['exc_med']:>16.2f}  " + "  ".join(f"{dd[f'exc{e}']:>5.1f}%" for e in EXC))
                else:
                    print(f"{LAB[wd]:<10}{n:>7}  (표본 없음)")
                DATA[b][ver][tf][LAB[wd]]=dd

HTML="""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>단계별 최대상승 & 놓친 수익 (KTR vs BREAKOUT)</title>
<style>
*{box-sizing:border-box}
body{font-family:'Malgun Gothic','Segoe UI',sans-serif;background:#0f1320;color:#dfe6f0;margin:0;line-height:1.6}
.wrap{max-width:980px;margin:0 auto;padding:24px}
h1{color:#4fc3f7;font-size:1.5em;margin:0 0 4px;text-align:center}
.date{text-align:center;color:#7e8aa0;font-size:.82em;margin-bottom:16px}
p,li{font-size:.92em;color:#c4cfde}
.box{background:#15203a;border:1px solid #2a3e63;border-radius:10px;padding:14px 18px;margin:12px 0}
.ctl{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0;align-items:center}
.ctl .lbl{color:#7e8aa0;font-size:.8em;margin-right:4px}
.btn{padding:6px 14px;border:1px solid #345;background:transparent;color:#9cf;border-radius:6px;cursor:pointer;font-size:.85em}
.btn.on{background:#4fc3f7;color:#0f1320;font-weight:bold}
table{width:100%;border-collapse:collapse;font-size:.85em;margin:8px 0}
th,td{padding:7px 8px;text-align:right;border-bottom:1px solid #243150}
th{color:#9cc4e8;background:#16203a}
td:first-child,th:first-child{text-align:left;font-weight:bold}
.hi{background:#13241a}
.note{font-size:.82em;color:#8493a8;font-style:italic;margin-top:6px}
.good{color:#5fd97e}.warn{color:#ffcf5c}b{color:#fff}
</style></head><body><div class=wrap>
<h1>단계별 "얼마나 올라갔나" & "더 먹을 수 있었나"</h1>
<div class=date>2010-2026 · 깨끗한 그리드 시뮬(이긴 트레이드) · 손절(-5)·미청산 제외 · base 토글: KTR vs 돌파봉</div>

<div class=box>
<p><b>이긴 단계</b> = 익절(가장 깊은 체결 +1.5)에 도달해 이긴 시점의 눌림 깊이.</p>
<ul>
<li><b>진입가 기준 최대상승</b>: 첫 진입가 대비 실제 최고 도달(익절 후에도 보유 가정). 단위 = 선택한 base(KTR 또는 돌파봉).</li>
<li><b class=good>익절선 초과분</b> = (가장 깊은 체결 기준 최대도달) − 1.5 = 1.5에서 안 끊었으면 더 먹을 수 있던 양.
<b>초과≥X = 초과분이 X "이상"인 누적 비율</b> (딱 X까지만 간 게 아니라 X 이상 전부 포함). 그래서 ≥0.5 > ≥1.0 > ≥2.0 순으로 작아짐.</li>
<li><b>base 비교</b>: KTR=세션 변동성 단위 / 돌파봉=돌파 캔들 크기 단위. 그리드 간격·도달값 모두 그 base 단위라, 두 base의 숫자는 <b>각자 단위 안에서</b> 해석.</li>
</ul>
</div>

<div class=ctl><span class=lbl>base</span><span id=basesel></span></div>
<div class=ctl><span class=lbl>진입</span><span id=versel></span></div>
<div class=ctl><span class=lbl>분봉</span><span id=tfsel></span></div>
<table id=tbl></table>
<p class=note id=ctx></p>

<div class=box>
<p class=note>※ <b>진입가 기준 최대상승</b>이 핵심: 깊게 눌릴수록 진입가 위로는 <b>덜</b> 올라감(바로출발 ~+2 → 3번눌림 ~+0.4). 깊은 단계의 '초과분'이 커 보이는 건 <b>깊은 바닥에서 본전 근처로 되돌아온 회복분(살아남은 소수)</b>이지 진입가 위 새 수익이 아님.</p>
<p class=warn>⚠ 생존편향: 이 표는 <b>이긴 트레이드</b>만. 같은 깊이까지 갔다 못 버틴 건 손절(-5)로 빠짐(위 손절% 참조). (50_pullback_outcome 참조)</p>
</div>

<script>
const D=__DATA__;const STG=["바로출발","1번눌림","2번눌림","3번눌림","4번눌림","6차(풀)"];const EXC=__EXC__;
let base='KTR',ver='v1',tf='10m';
function mk(host,opts,cur,cb){const h=document.getElementById(host);h.innerHTML='';opts.forEach(o=>{const b=document.createElement('button');b.className='btn'+(o[0]===cur()?' on':'');b.textContent=o[1];b.onclick=()=>{cb(o[0]);render()};h.appendChild(b)})}
function render(){
 mk('basesel',[['KTR','KTR'],['BREAKOUT','돌파봉']],()=>base,v=>base=v);
 mk('versel',[['v1','v1 즉시'],['v2','v2 풀백']],()=>ver,v=>ver=v);
 mk('tfsel',[['2m','2분'],['5m','5분'],['10m','10분']],()=>tf,v=>tf=v);
 const dd=D[base][ver][tf];const unit=base==='KTR'?'KTR':'돌파봉';
 let h=`<tr><th>이긴 단계</th><th>건수</th><th>진입가기준<br>최대상승(${unit})</th><th>익절선<br>초과분(중앙)</th>`
   +EXC.map(e=>`<th class=hi>초과≥${e.toFixed(1)}</th>`).join('')+'</tr>';
 STG.forEach(st=>{const d=dd[st];
  if(!d||!d.n){h+=`<tr><td>${st}</td><td colspan=9 style="text-align:left;color:#7e8aa0">표본 없음</td></tr>`;return;}
  h+=`<tr><td>${st}</td><td>${d.n.toLocaleString()}</td><td>+${d.mfeE_med}</td><td>+${d.exc_med}</td>`
   +EXC.map(e=>`<td class=hi>${d['exc'+e.toFixed(1)]}%</td>`).join('')+'</tr>';});
 document.getElementById('tbl').innerHTML=h;
 const c=dd._ctx;
 document.getElementById('ctx').innerHTML=`[${base}] 전체 진입 ${c.n.toLocaleString()}건 중 <b>손절(-5) ${c.stop.toLocaleString()}건(${c.stop_pct}%)</b>, 미청산 ${c.open.toLocaleString()}건은 제외(이긴 것만).`;
}
render();
</script>
</div></body></html>"""
out=HTML.replace("__DATA__",json.dumps(DATA,ensure_ascii=False)).replace("__EXC__",json.dumps(EXC))
with open("../result/stage_upside.html","w",encoding="utf-8") as f: f.write(out)
print("\n-> ../result/stage_upside.html")
