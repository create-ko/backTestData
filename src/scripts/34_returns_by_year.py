# -*- coding: utf-8 -*-
"""34 — v1·v2 확정설정 연도별 실제 수익률 + 자산곡선 + 비용 전/후. 분봉별.
설정: 후방 [1,1,2,2,3,4] / 그리드 [0,1,2,3,4,4.5] / TP=1.5 / 6차 반등탈출(바닥+1.0) / 풀스톱 -5.
수익측정: 트레이드별 R = 손익/|풀스톱|. 시간순 복리(트레이드당 2% 리스크).
비용: 라운드턴 S=$0.30/랏, 비용R = 체결랏수*(S/KTR$)/|풀스톱|. net = gross - 비용.
주의: 복리%는 트레이드 순차진입 가정(겹침 미반영) → 2m/5m은 과대, 10m이 가장 현실적.
출력: 콘솔 연도별표 + returns_by_year.html (자산곡선·연R, 분봉/버전/gross-net 토글)."""
import csv, math, json
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0
RISK=0.02; SPREAD=0.30
YEARS=["2020","2021","2022","2023","2024","2025","2026"]
SUM_L=sum(L)  # 13
STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))  # 24

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

def sim(bars, start_i, anchor, direction, base):
    n=len(bars)
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(6)]; stop=anchor-base*STOPM
    else:                 E=[anchor+base*MULT[i] for i in range(6)]; stop=anchor+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(start_i,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr = TP if fc<6 else B6X
        tp = deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return maxF,"STOP"
            if h>=tp: return maxF,("B6" if fc==6 else "TPs")
        else:
            if fc>=6 and h>=stop: return maxF,"STOP"
            if l<=tp: return maxF,("B6" if fc==6 else "TPs")
    return maxF,"OPEN"

def pnl_tps(k): exitlv=MULT[k-1]-TP; return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6():   exitlv=MULT[5]-B6X; return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(): return sum(L[i]*(MULT[i]-STOPM) for i in range(6))

def trade_R(maxF,kind):
    if kind=="STOP": pnl=pnl_stop(); lots=SUM_L
    elif kind=="B6": pnl=pnl_b6();   lots=SUM_L
    else:            pnl=pnl_tps(maxF); lots=sum(L[:maxF])
    return pnl/STOP_R, lots

def v1_jobs(tf,bars,idx):
    out=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: out.append((bi+1,float(s[7]),s[4],k,s[1][:4]))
    out.sort(key=lambda x:x[0]); return out
def v2_jobs(tf,bars,idx):
    u2,l2=boll([b[1] for b in bars],4,4.0); brk={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    out=[]; pending=None
    for i in range(len(bars)):
        if i in brk: pending=(i,brk[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                if i+1<len(bars):
                    k=float(ps[8])
                    if k>0: out.append((i+1,bars[i+1][1],pdir,k,ps[1][:4])); pending=None
    out.sort(key=lambda x:x[0]); return out

def maxdd_pct(eq):
    peak=eq[0]; mdd=0.0
    for v in eq:
        if v>peak: peak=v
        dd=(peak-v)/peak
        if dd>mdd: mdd=dd
    return 100*mdd
def maxdd_R(cum):
    peak=cum[0]; mdd=0.0
    for v in cum:
        if v>peak: peak=v
        dd=peak-v
        if dd>mdd: mdd=dd
    return mdd

DATA={}
print(f"# 확정설정: 후방 {'·'.join(map(str,L))} / TP={TP} / 6차반등탈출 / 리스크 {RISK*100:.0f}%/트레이드 / 비용 ${SPREAD} 라운드턴")
print(f"# 풀스톱 정규화 = {STOP_R} (=-1R)\n")
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
    DATA[tf]={}
    JOBS={"v1":v1_jobs(tf,bars,idx),"v2":v2_jobs(tf,bars,idx)}
    for ver in ["v1","v2"]:
        jobs=JOBS[ver]
        trades=[]  # (year, gR, nR)
        for si,a,d,k,yr in jobs:
            mf,kind=sim(bars,si,a,d,k)
            if kind not in ("TPs","B6","STOP"): continue
            gR,lots=trade_R(mf,kind)
            costR=lots*(SPREAD/k)/STOP_R
            trades.append((yr,gR,gR-costR))
        n=len(trades)
        # 시간순 복리 + 누적R
        eqg=[1.0]; eqn=[1.0]; cumg=[0.0]; cumn=[0.0]
        for yr,g,nn in trades:
            eqg.append(eqg[-1]*(1+RISK*g)); eqn.append(eqn[-1]*(1+RISK*nn))
            cumg.append(cumg[-1]+g); cumn.append(cumn[-1]+nn)
        # 연도별
        ann={}
        # 연 경계 인덱스
        idx_year={}
        for j,(yr,g,nn) in enumerate(trades): idx_year.setdefault(yr,[]).append(j+1)  # eq index
        rows=[]
        for yr in YEARS:
            js=idx_year.get(yr,[])
            if not js: rows.append((yr,0,0,0,0,0,0,0)); continue
            j0,j1=js[0]-1,js[-1]
            rg=cumg[j1]-cumg[j0]; rn=cumn[j1]-cumn[j0]
            retg=100*(eqg[j1]/eqg[j0]-1); retn=100*(eqn[j1]/eqn[j0]-1)
            mddg=maxdd_pct(eqg[j0:j1+1]); mddn=maxdd_pct(eqn[j0:j1+1])
            stopn=sum(1 for jj in js if False)  # placeholder
            rows.append((yr,len(js),rg,rn,retg,retn,mddg,mddn))
        # 전체
        tot_rg=cumg[-1]; tot_rn=cumn[-1]
        tot_retg=100*(eqg[-1]-1); tot_retn=100*(eqn[-1]-1)
        yrs_span=6.46
        cagrg=100*(eqg[-1]**(1/yrs_span)-1) if eqg[-1]>0 else -100
        cagrn=100*(eqn[-1]**(1/yrs_span)-1) if eqn[-1]>0 else -100
        mddg=maxdd_pct(eqg); mddn=maxdd_pct(eqn)
        rmddg=maxdd_R(cumg); rmddn=maxdd_R(cumn)
        wins=sum(1 for _,g,_ in trades if g>0)
        # 콘솔
        print(f"{'='*92}\n=== {tf} {ver}  (트레이드 {n}건, 승률 {100*wins/n:.1f}%) ===")
        print(f"{'연도':>6}{'건수':>6} | {'연R(gross)':>11}{'연R(net)':>10} | {'연수익%g':>9}{'연수익%n':>9} | {'연MDD%g':>8}{'연MDD%n':>8}")
        for yr,c,rg,rn,rtg,rtn,mg,mn in rows:
            if c==0: print(f"{yr:>6}{0:>6}"); continue
            print(f"{yr:>6}{c:>6} | {rg:>+11.1f}{rn:>+10.1f} | {rtg:>+8.1f}%{rtn:>+8.1f}% | {mg:>7.1f}%{mn:>7.1f}%")
        print(f"{'전체':>6}{n:>6} | {tot_rg:>+11.1f}{tot_rn:>+10.1f} | 누적복리 gross {tot_retg:+.0f}% / net {tot_retn:+.0f}%")
        print(f"        CAGR gross {cagrg:+.1f}% / net {cagrn:+.1f}% | 최대MDD gross {mddg:.1f}% / net {mddn:.1f}% | 누적R MDD gross {rmddg:.1f} / net {rmddn:.1f}\n")
        # HTML 데이터(자산곡선 다운샘플 ~400점)
        step=max(1,len(cumn)//400)
        ds=list(range(0,len(cumn),step))
        if ds[-1]!=len(cumn)-1: ds.append(len(cumn)-1)
        DATA[tf][ver]={
            "n":n,"winrate":round(100*wins/n,1),
            "years":YEARS,
            "annR_g":[round(r[2],1) for r in rows],"annR_n":[round(r[3],1) for r in rows],
            "annRet_g":[round(r[4],1) for r in rows],"annRet_n":[round(r[5],1) for r in rows],
            "annMDD_g":[round(r[6],1) for r in rows],"annMDD_n":[round(r[7],1) for r in rows],
            "cnt":[r[1] for r in rows],
            "curve_x":ds,
            "curve_g":[round(cumg[j],2) for j in ds],"curve_n":[round(cumn[j],2) for j in ds],
            "tot_Rg":round(tot_rg,1),"tot_Rn":round(tot_rn,1),
            "tot_retg":round(tot_retg,0),"tot_retn":round(tot_retn,0),
            "cagrg":round(cagrg,1),"cagrn":round(cagrn,1),
            "mddg":round(mddg,1),"mddn":round(mddn,1),
            "rmddg":round(rmddg,1),"rmddn":round(rmddn,1),
        }

# ---------- HTML ----------
HTML="""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>
<title>연도별 수익률 — 확정전략</title>
<style>
body{font-family:'Malgun Gothic',sans-serif;background:#12121f;color:#e0e0e0;margin:0;padding:18px}
h1{color:#4fc3f7;text-align:center;font-size:1.25em;margin:4px}
.sub{text-align:center;color:#8aa;font-size:.78em;margin-bottom:14px}
.ctl{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-bottom:16px}
.ctl .g{display:flex;gap:4px;background:#1c1c2e;padding:5px;border-radius:8px}
.btn{padding:6px 13px;border:1px solid #345;background:transparent;color:#9cf;border-radius:5px;cursor:pointer;font-size:.8em}
.btn.on{background:#4fc3f7;color:#12121f;font-weight:bold;border-color:#4fc3f7}
.kpi{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-bottom:14px}
.card{background:#1a1a2c;border:1px solid #2a3a55;border-radius:9px;padding:10px 16px;text-align:center;min-width:96px}
.card .v{font-size:1.2em;font-weight:bold;color:#fff}.card .l{font-size:.7em;color:#89a;margin-top:2px}
.pos{color:#5fd97e}.neg{color:#ff6b6b}
.wrap{max-width:1000px;margin:0 auto}
canvas{background:#15151f;border-radius:8px;width:100%}
.tbl{width:100%;border-collapse:collapse;font-size:.8em;margin-top:14px}
.tbl th,.tbl td{padding:5px 8px;text-align:right;border-bottom:1px solid #263}
.tbl th{color:#9cf;background:#1a1a2c}.tbl td:first-child,.tbl th:first-child{text-align:center}
</style></head><body><div class=wrap>
<h1>확정 전략 연도별 수익률 · 자산곡선</h1>
<div class=sub>후방 1·1·2·2·3·4 · TP=1.5 · 6차 반등탈출 · 트레이드당 2% 리스크 · 비용 $0.30 라운드턴<br>
※ 복리%는 트레이드 순차진입 가정(겹침 미반영) — 2m/5m 과대, <b>10m이 가장 현실적</b>. 누적R은 사이징 무관 견고지표.</div>
<div class=ctl>
 <div class=g id=tf></div><div class=g id=ver></div><div class=g id=cost></div>
</div>
<div class=kpi id=kpi></div>
<canvas id=cv width=960 height=340></canvas>
<table class=tbl id=tbl></table>
</div>
<script>
const DATA=__DATA__;
let tf='10m',ver='v2',cost='n';
function mk(host,opts,cur,cb){const h=document.getElementById(host);h.innerHTML='';opts.forEach(o=>{const b=document.createElement('button');b.className='btn'+(o[0]===cur()?' on':'');b.textContent=o[1];b.onclick=()=>{cb(o[0]);render()};h.appendChild(b)})}
function ctrls(){
 mk('tf',[['2m','2분'],['5m','5분'],['10m','10분']],()=>tf,v=>tf=v);
 mk('ver',[['v1','v1 즉시'],['v2','v2 풀백']],()=>ver,v=>ver=v);
 mk('cost',[['g','비용 전(gross)'],['n','비용 후(net)']],()=>cost,v=>cost=v);
}
function kpi(d){
 const C=cost;
 const ret=C=='g'?d.tot_retg:d.tot_retn, cagr=C=='g'?d.cagrg:d.cagrn,
       mdd=C=='g'?d.mddg:d.mddn, R=C=='g'?d.tot_Rg:d.tot_Rn, rmdd=C=='g'?d.rmddg:d.rmddn;
 const cls=v=>v>=0?'pos':'neg';
 document.getElementById('kpi').innerHTML=
  `<div class=card><div class="v ${cls(R)}">${R>=0?'+':''}${R}R</div><div class=l>누적 R</div></div>
   <div class=card><div class="v ${cls(rmdd)}">-${rmdd}R</div><div class=l>누적R 최대낙폭</div></div>
   <div class=card><div class="v ${cls(cagr)}">${cagr>=0?'+':''}${cagr}%</div><div class=l>CAGR(복리)</div></div>
   <div class=card><div class="v neg">${mdd}%</div><div class=l>최대 MDD</div></div>
   <div class=card><div class="v">${d.winrate}%</div><div class=l>승률 (${d.n}건)</div></div>`;
}
function draw(d){
 const cv=document.getElementById('cv'),x=cv.getContext('2d');const W=cv.width,H=cv.height;
 x.clearRect(0,0,W,H);const pad=46;
 const yg=d.curve_g,yn=d.curve_n,xs=d.curve_x;
 const ya=cost=='g'?yg:yn;
 const mn=Math.min(0,...ya),mx=Math.max(...ya,1);
 const X=i=>pad+(W-pad-12)*(xs[i]/xs[xs.length-1]);
 const Y=v=>H-pad-(H-pad-14)*((v-mn)/(mx-mn||1));
 // grid + zero line
 x.strokeStyle='#243';x.lineWidth=1;x.beginPath();x.moveTo(pad,Y(0));x.lineTo(W-12,Y(0));x.stroke();
 x.fillStyle='#678';x.font='10px sans-serif';
 for(let g=0;g<=4;g++){const v=mn+(mx-mn)*g/4;const yy=Y(v);x.strokeStyle='#1e2a3a';x.beginPath();x.moveTo(pad,yy);x.lineTo(W-12,yy);x.stroke();x.fillText(v.toFixed(0)+'R',6,yy+3);}
 // both faint, active bold
 function line(arr,col,wd){x.strokeStyle=col;x.lineWidth=wd;x.beginPath();arr.forEach((v,i)=>{const xx=X(i),yy=Y(v);i?x.lineTo(xx,yy):x.moveTo(xx,yy)});x.stroke();}
 line(cost=='g'?yn:yg,'#2e4a55',1.2);
 line(ya,cost=='g'?'#ffd54f':'#5fd97e',2.2);
 // year ticks (approx by trade index→year via table cnt)
 x.fillStyle='#789';
 x.fillText('트레이드 순서 →',W-150,H-6);
 x.fillText('누적 R',pad-4,12);
}
function table(d){
 const C=cost;const aR=C=='g'?d.annR_g:d.annR_n,aRet=C=='g'?d.annRet_g:d.annRet_n,aM=C=='g'?d.annMDD_g:d.annMDD_n;
 let h='<tr><th>연도</th><th>건수</th><th>연 R</th><th>연 수익%</th><th>연 MDD%</th></tr>';
 d.years.forEach((y,i)=>{if(!d.cnt[i])return;const cl=aR[i]>=0?'pos':'neg';
  h+=`<tr><td>${y}</td><td>${d.cnt[i]}</td><td class=${cl}>${aR[i]>=0?'+':''}${aR[i]}</td><td class=${aRet[i]>=0?'pos':'neg'}>${aRet[i]>=0?'+':''}${aRet[i]}%</td><td class=neg>${aM[i]}%</td></tr>`;});
 document.getElementById('tbl').innerHTML=h;
}
function render(){const d=DATA[tf][ver];ctrls();kpi(d);draw(d);table(d);}
ctrls();render();
</script></body></html>"""
out="../result/returns_by_year.html"
with open(out,"w",encoding="utf-8") as f: f.write(HTML.replace("__DATA__",json.dumps(DATA)))
print(f"→ {out}")
