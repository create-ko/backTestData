# -*- coding: utf-8 -*-
"""56 - 돌파 진입 '분출 도달' 최종 리포트 (신규, 이걸로만 분석).
사양:
 - 진입 v1(돌파 다음봉 시가)·v2(풀백 다음봉 시가). 진입가=다음봉 시가(=그리드 0차 앵커).
 - 시간필터: KST 08~24시 진입만.
 - base: KTR(s[8]) / 돌파봉(s[9]) 토글.
 - 슬리피지: 불리 0.3 포인트(진입+익절 각 0.3 -> 도달폭에서 0.6 차감). 토글(0/0.3).
 - (A) 성공/단계: 가장 깊은 체결서 +1.5KTR(슬리피지 반영) 도달=성공(단계=그때 깊이). -5=손절. 그 외 OPEN.
 - (B) 놓친수익: 성공 후 안 끊고 보유 시 가장 깊은 체결 기준 최대 도달(>=1.5..5KTR). 분출 끝=바닥 복귀/-5/끝.
 - 축: base x slip x v1/v2 x 분봉 x 세션(아/유/미) x 방향(L/S) x 연도. + 소요시간·연도별 손절률.
원천 카운트만 JSON에 저장, 화면(JS)에서 합산. data/에서 실행. 콘솔 ASCII만(규칙3).
출력: ../result/breakout_reach.html"""
import csv, math, json, time

MULT=[0,1,2,3,4,4.5]; STOPM=5.0; TPK=1.5; MAXSCAN=3000
BK=[1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0]   # 도달 버킷(가장 깊은 체결 기준 KTR)
TFMIN={"2m":2,"5m":5,"10m":10}
SLIPS=[0.0,0.3]

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
def khour(e,off): e=e//1000 if e>1e11 else e; return ((e//3600)+off)%24
def kyear(e,off): e=e//1000 if e>1e11 else e; return time.strftime("%Y",time.gmtime(e+off*3600))

def trace(bars,eb,anchor,d,base,slip):
    """(outcome, stage, reach_ktr, tbars). outcome WIN/FAIL/OPEN.
       성공=가장깊은체결서 +1.5(슬리피지반영) 도달. reach=놓친수익(보유시 최대도달, 슬리피지반영)."""
    n=len(bars); LONG=(d=="LONG")
    if eb>=n or base<=0: return ("OPEN",0,0.0,0)
    E=[anchor-base*m if LONG else anchor+base*m for m in MULT]
    stop=anchor-base*STOPM if LONG else anchor+base*STOPM
    slipK=2*slip   # 진입+익절 합산(가격)
    filled=[False]*6; filled[0]=True; maxd=0
    end=min(n,eb+MAXSCAN); succ=False; sd=None; tb=0; si=eb
    for i in range(eb,end):
        h=bars[i][2]; l=bars[i][3]
        for k in range(1,6):
            if not filled[k] and ((LONG and l<=E[k]) or ((not LONG) and h>=E[k])): filled[k]=True
        maxd=max(k for k in range(6) if filled[k]); deepest=E[maxd]
        if maxd>=5 and ((LONG and l<=stop) or ((not LONG) and h>=stop)): return ("FAIL",5,0.0,i-eb)
        # 성공: 슬리피지 반영 실현도달 >= 1.5  <=>  raw 유리폭 >= 1.5*base + slipK
        if LONG:
            if h-deepest >= TPK*base+slipK: succ=True; sd=maxd; tb=i-eb; si=i; break
        else:
            if deepest-l >= TPK*base+slipK: succ=True; sd=maxd; tb=i-eb; si=i; break
    if not succ: return ("OPEN",maxd,0.0,0)
    # (B) 놓친수익: 보유시 최대 도달(바닥 복귀/-5/끝 까지)
    deepest=E[sd]
    peak=bars[si][2] if LONG else bars[si][3]
    for j in range(si,min(n,si+MAXSCAN)):
        h=bars[j][2]; l=bars[j][3]
        if LONG:
            if h>peak: peak=h
            if l<=deepest or l<=stop: break
        else:
            if l<peak: peak=l
            if h>=deepest or h>=stop: break
    raw=(peak-deepest) if LONG else (deepest-peak)
    reach=(raw-slipK)/base
    return ("WIN",sd,reach,tb)

def v1_entries(tf,bars,idx,off):
    out=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            eb=bi+1
            if khour(bars[eb][0],off)<8: continue
            ktr=float(s[8]) if s[8] else 0.0; brk=float(s[9]) if s[9] else 0.0
            if ktr<=0: continue
            out.append((eb,bars[eb][1],s[4],ktr,brk,s[5],kyear(bars[eb][0],off)))
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
            pi,ps=pending; pdir=ps[4]; h=bars[i][2]; l=bars[i][3]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                eb=i+1
                if eb<len(bars) and khour(bars[eb][0],off)>=8:
                    ktr=float(ps[8]) if ps[8] else 0.0; brk=float(ps[9]) if ps[9] else 0.0
                    if ktr>0: out.append((eb,bars[eb][1],pdir,ktr,brk,ps[5],kyear(bars[eb][0],off)))
                pending=None
    return out

def newleaf(): return {"st":[None]*6,"fail":0,"open":0}
def stcell(): return {"n":0,"t":0,"bc":[0]*len(BK)}

DATA={}
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); off=calib(tf)
    JOBS={"v1":v1_entries(tf,bars,idx,off),"v2":v2_entries(tf,bars,idx,off)}
    for ver in ["v1","v2"]:
        ents=JOBS[ver]
        for bn,bi in [("KTR",3),("BRK",4)]:
            for slip in SLIPS:
                top=f"{bn}|{slip}|{ver}|{tf}"; DATA[top]={}
                nw=nf=no=0
                for e in ents:
                    base=e[bi]
                    if base<=0: continue
                    oc,sd,reach,tb=trace(bars,e[0],e[1],e[2],base,slip)
                    lk=f"{e[5]}|{e[2]}|{e[6]}"   # sess|dir|year
                    leaf=DATA[top].get(lk)
                    if leaf is None: leaf=newleaf(); DATA[top][lk]=leaf
                    if oc=="WIN":
                        nw+=1
                        c=leaf["st"][sd]
                        if c is None: c=stcell(); leaf["st"][sd]=c
                        c["n"]+=1; c["t"]+=tb
                        for bidx,bv in enumerate(BK):
                            if reach>=bv: c["bc"][bidx]+=1
                    elif oc=="FAIL": leaf["fail"]+=1; nf+=1
                    else: leaf["open"]+=1; no+=1
                print(f"{top}: WIN {nw} / FAIL {nf} / OPEN {no}  (성공률 {100*nw/(nw+nf) if nw+nf else 0:.1f}%)")

META={"BK":BK,"TFMIN":TFMIN,"slips":SLIPS}
out={"meta":META,"data":DATA}
print("\nJSON 직렬화...")
js=json.dumps(out,ensure_ascii=False)
print(f"JSON 크기 {len(js)/1024:.0f} KB")

HTML="""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>돌파 분출 도달 리포트 (최종)</title>
<style>
*{box-sizing:border-box}
body{font-family:'Malgun Gothic','Segoe UI',sans-serif;background:#0f1320;color:#dfe6f0;margin:0;line-height:1.55}
.wrap{max-width:1040px;margin:0 auto;padding:22px}
h1{color:#4fc3f7;font-size:1.4em;margin:0 0 2px;text-align:center}
.date{text-align:center;color:#7e8aa0;font-size:.8em;margin-bottom:12px}
h2{color:#7fd4ff;font-size:1.05em;margin:20px 0 6px;padding-bottom:4px;border-bottom:1px solid #25324d}
p,li{font-size:.88em;color:#c4cfde}
.box{background:#15203a;border:1px solid #2a3e63;border-radius:9px;padding:11px 15px;margin:10px 0}
.ctl{display:flex;gap:5px;flex-wrap:wrap;align-items:center;margin:6px 0}
.ctl .lbl{color:#7e8aa0;font-size:.76em;width:42px}
.btn{padding:5px 11px;border:1px solid #345;background:transparent;color:#9cf;border-radius:6px;cursor:pointer;font-size:.8em}
.btn.on{background:#4fc3f7;color:#0f1320;font-weight:bold}
select{background:#16203a;color:#cfe;border:1px solid #345;border-radius:6px;padding:5px 8px;font-size:.8em}
.kpis{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.kpi{flex:1;min-width:90px;background:#15203a;border:1px solid #28395c;border-radius:8px;padding:8px;text-align:center}
.kpi .v{font-size:1.2em;font-weight:bold;color:#fff}.kpi .l{font-size:.7em;color:#8aa;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:.82em;margin:6px 0}
th,td{padding:5px 7px;text-align:right;border-bottom:1px solid #243150}
th{color:#9cc4e8;background:#16203a}td:first-child,th:first-child{text-align:left;font-weight:bold}
.bar{height:11px;background:#2b6cb0;border-radius:2px;display:inline-block;vertical-align:middle}
.note{font-size:.78em;color:#8493a8;font-style:italic;margin-top:5px}
.bad{color:#ff6f6f}.good{color:#5fd97e}.warn{color:#ffcf5c}b{color:#fff}
.two{display:grid;grid-template-columns:1.3fr 1fr;gap:14px}@media(max-width:760px){.two{grid-template-columns:1fr}}
</style></head><body><div class=wrap>
<h1>돌파 진입 · 분출 도달 리포트</h1>
<div class=date>골드 2010-2026 · KST 08~24시 진입 · 진입가=다음봉 시가 · (A)+1.5KTR 성공/단계 · (B)놓친수익(보유시 최대도달) · 슬리피지 불리</div>
<div class=box><p class=note>분출 도달은 <b>가장 깊은 체결 기준 KTR</b>. (A)성공=가장깊은체결서 +1.5 도달, 손절=−5. (B)도달버킷=익절 안 끊고 보유 시 최대 도달(≥1.5~5). <b>슬리피지 토글</b>: 0.3은 도달폭엔 작지만 <b>성공률엔 크게 작용</b>(10m 95→91%, 2m 94→86%) — +1.5 TP를 못 넘겨 −5로 흘러가는 게 늘기 때문(작은 KTR=2분일수록 타격 큼). 단계 통계는 <b>성공(분출)난 것만</b>(생존편향).</p></div>

<div class=ctl><span class=lbl>base</span><span id=t_base></span><span class=lbl style="margin-left:8px">슬리피지</span><span id=t_slip></span></div>
<div class=ctl><span class=lbl>진입</span><span id=t_ver></span><span class=lbl style="margin-left:8px">분봉</span><span id=t_tf></span></div>
<div class=ctl><span class=lbl>세션</span><select id=s_sess></select><span class=lbl style="margin-left:8px">방향</span><select id=s_dir></select><span class=lbl style="margin-left:8px">연도</span><select id=s_year></select></div>

<div class=kpis id=kpi></div>
<div class=two>
<div>
<h2>단계별 분포 · 도달 · 소요</h2>
<table id=stage></table>
<p class=note>비중=성공 중 단계 비율 · 도달≥X=보유시 X KTR 이상 간 비율(가장깊은체결 기준) · 소요=진입→+1.5 평균(시간).</p>
</div>
<div>
<h2>연도별 손절률</h2>
<div id=yearloss></div>
<p class=note>−5 손절 / (성공+손절). 현재 base·슬리피지·진입·분봉·세션·방향 기준.</p>
</div>
</div>
<div class=note style="margin-top:18px;text-align:center">과거 데이터 백테스트. 미래수익 보장 아님. 골드 단독.</div>
<script>
const O=__OUT__;const D=O.data, BK=O.meta.BK, TFMIN=O.meta.TFMIN;
const YEARS=[];for(let y=2010;y<=2026;y++)YEARS.push(''+y);
const SESS=['아시아','유로','미장'], DIRS=['LONG','SHORT'];
let base='KTR',slip='0.3',ver='v1',tf='10m';
function mkbtn(host,opts,cur,cb){const h=document.getElementById(host);h.innerHTML='';opts.forEach(o=>{const b=document.createElement('button');b.className='btn'+(o[0]===cur()?' on':'');b.textContent=o[1];b.onclick=()=>{cb(o[0]);render()};h.appendChild(b)})}
function fillsel(id,opts){const s=document.getElementById(id);s.innerHTML='';opts.forEach(o=>s.add(new Option(o[1],o[0])));s.onchange=render;}
function topkey(){return base+'|'+slip+'|'+ver+'|'+tf;}
function agg(leaves,fsess,fdir,fyear){
 const st=[]; for(let i=0;i<6;i++)st.push({n:0,t:0,bc:BK.map(_=>0)}); let fail=0;
 for(const k in leaves){const p=k.split('|');
  if(fsess!=='ALL'&&p[0]!==fsess)continue;
  if(fdir!=='ALL'&&p[1]!==fdir)continue;
  if(fyear!=='ALL'&&p[2]!==fyear)continue;
  const lf=leaves[k]; fail+=lf.fail;
  for(let i=0;i<6;i++){const c=lf.st[i];if(!c)continue;st[i].n+=c.n;st[i].t+=c.t;for(let b=0;b<BK.length;b++)st[i].bc[b]+=c.bc[b];}}
 return {st:st,fail:fail};
}
function render(){
 mkbtn('t_base',[['KTR','KTR'],['BRK','돌파봉']],()=>base,v=>base=v);
 mkbtn('t_slip',[['0.0','없음'],['0.3','0.3 불리']],()=>slip,v=>slip=v);
 mkbtn('t_ver',[['v1','v1 즉시'],['v2','v2 풀백']],()=>ver,v=>ver=v);
 mkbtn('t_tf',[['2m','2분'],['5m','5분'],['10m','10분']],()=>tf,v=>tf=v);
 const leaves=D[topkey()]||{};
 const fs=document.getElementById('s_sess').value, fd=document.getElementById('s_dir').value, fy=document.getElementById('s_year').value;
 const A=agg(leaves,fs,fd,fy);
 const totS=A.st.reduce((a,c)=>a+c.n,0), fail=A.fail, tot=totS+fail;
 const wr= tot? (100*totS/tot):0;
 document.getElementById('kpi').innerHTML=
  `<div class=kpi><div class=v>${tot.toLocaleString()}</div><div class=l>진입(성공+손절)</div></div>
   <div class=kpi><div class="v good">${totS.toLocaleString()}</div><div class=l>분출 성공</div></div>
   <div class=kpi><div class="v bad">${fail.toLocaleString()}</div><div class=l>−5 손절</div></div>
   <div class=kpi><div class=v>${wr.toFixed(1)}%</div><div class=l>성공률</div></div>`;
 const LAB=['0차(바로출발)','1차눌림','2차눌림','3차눌림','4차눌림','5차(6체결)'];
 const showB=[2.0,3.0,4.0,5.0];
 let h='<tr><th>단계</th><th>비중</th><th>건수</th>'+showB.map(b=>`<th>≥${b}</th>`).join('')+'<th>소요h</th></tr>';
 A.st.forEach((c,i)=>{if(!c.n){h+=`<tr><td>${LAB[i]}</td><td>-</td><td>0</td><td colspan=${showB.length+1}></td></tr>`;return;}
  const pct=100*c.n/totS; const hrs=(c.t/c.n)*TFMIN[tf]/60;
  let row=`<tr><td>${LAB[i]}</td><td>${pct.toFixed(1)}%</td><td>${c.n.toLocaleString()}</td>`;
  showB.forEach(b=>{const bi=BK.indexOf(b);const v=bi>=0?100*c.bc[bi]/c.n:0;row+=`<td>${v.toFixed(1)}%</td>`;});
  row+=`<td>${hrs.toFixed(1)}</td></tr>`; h+=row;});
 document.getElementById('stage').innerHTML=h;
 // 연도별 손절률
 let maxlr=1; const yr=[];
 YEARS.forEach(y=>{const a=agg(leaves,fs,fd,y);const t=a.st.reduce((x,c)=>x+c.n,0)+a.fail;const lr=t?100*a.fail/t:0;yr.push([y,t,lr]);if(lr>maxlr)maxlr=lr;});
 let yh='';yr.forEach(r=>{if(!r[1]){return;}const w=Math.round(r[2]/maxlr*180);
  yh+=`<div style="display:flex;align-items:center;gap:7px;margin:2px 0;font-size:.78em"><span style="width:34px;color:#8aa">${r[0]}</span><span class=bar style="background:#a33;width:${w}px"></span><span class=bad>${r[2].toFixed(1)}%</span><span style="color:#566">n=${r[1]}</span></div>`;});
 document.getElementById('yearloss').innerHTML=yh||'<p class=note>표본 없음</p>';
}
fillsel('s_sess',[['ALL','전체']].concat(SESS.map(s=>[s,s])));
fillsel('s_dir',[['ALL','전체'],['LONG','매수(L)'],['SHORT','매도(S)']]);
fillsel('s_year',[['ALL','전체']].concat(YEARS.map(y=>[y,y])));
render();
</script>
</div></body></html>"""
with open("../result/breakout_reach.html","w",encoding="utf-8") as f:
    f.write(HTML.replace("__OUT__",js))
print("-> ../result/breakout_reach.html")
