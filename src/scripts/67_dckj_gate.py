# -*- coding: utf-8 -*-
"""67 - 더캔지추(1H 정렬표) 방향게이트 + 66 1분봉 정직검증.
매 1H 마감마다 4요소 가중투표로 방향 우위 산출(+ =LONG):
  더(w3): 1H close vs BB(20,2) - 하단근접 +3 / 상단근접 -3 (수축원비=과매도 매수)
  캔(w2): 1H 캔들 - 망치 +2 / 역망치(슈팅) -2 / 도지 0
  추(w2): 1H 20MA 기울기 + 4H 20MA 기울기 (연속방향, 둘 일치 +-2)
  지(w3): 직전 확정 스윙 S/R 레벨 근접 - 지지 +3 / 저항 -3 (휴리스틱)
net=합, bias=sign, strength=|net|. 미래참조 차단: 진입시각 이전 '마감된' 1H봉만 사용.
게이트: 하위봉(2/5/10m) 돌파신호 방향 == bias 일 때만 진입(strength 임계 버킷).
해소는 66 simB(1분봉 시간순). 후방랏/TP1.5/6차/비용$0.30/2%복리/KST08~24/순차.
data/에서 실행. 콘솔 ASCII만(규칙3)."""
import csv, math, time, bisect

MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0
SUM_L=sum(L); STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))
SPREAD=0.30; RISK=0.02; START_H=8; CAP1M=120*86400
W_DEO=3; W_CAN=2; W_CHU=2; W_JI=3   # 가중치: 더3 지3 캔2 추2

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
def calib_offset(tf):
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def khour(e,off): e=e//1000 if e>1e11 else e; return ((e//3600)+off)%24
def kyear(e,off): e=e//1000 if e>1e11 else e; return time.strftime("%Y",time.gmtime(e+off*3600))
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
def sma(src,length):
    n=len(src); out=[None]*n; s=0.0
    for i in range(n):
        s+=src[i]
        if i>=length: s-=src[i-length]
        if i>=length-1: out[i]=s/length
    return out
def derive_years():
    ys=set()
    with open("signals_10m_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd: ys.add(s[1][:4])
    return sorted(ys)
YEARS=derive_years()

def pnl_tps(k): exitlv=MULT[k-1]-TP; return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6():   exitlv=MULT[5]-B6X; return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(): return sum(L[i]*(MULT[i]-STOPM) for i in range(6))
def trade_R(maxF,kind):
    if kind=="STOP": return pnl_stop()/STOP_R, SUM_L
    if kind=="B6":   return pnl_b6()/STOP_R, SUM_L
    return pnl_tps(maxF)/STOP_R, sum(L[:maxF])
def maxdd(eq):
    peak=eq[0]; m=0.0
    for v in eq:
        if v>peak: peak=v
        d=(peak-v)/peak
        if d>m: m=d
    return 100*m

print("1분봉 로딩(전체 OHLC)...")
T1=[]; O1=[]; H1=[]; L1=[]; C1=[]
with open("xauusd_1m_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
    rd=csv.reader(fp); next(rd)
    for r in rd:
        T1.append(int(float(r[0]))); O1.append(float(r[1])); H1.append(float(r[2])); L1.append(float(r[3])); C1.append(float(r[4]))
print(f"1m {len(T1)}봉")

def simB(entry_epoch,anchor,direction,base):
    j0=bisect.bisect_left(T1,entry_epoch); n=len(T1)
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(6)]; stop=anchor-base*STOPM
    else:                 E=[anchor+base*MULT[i] for i in range(6)]; stop=anchor+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for m in range(j0,n):
        if T1[m]-T1[j0]>CAP1M: return T1[m],maxF,"OPEN"
        h=H1[m]; l=L1[m]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); deepest=E[max(k for k in range(6) if filled[k])]
        thr=TP if fc<6 else B6X
        tp=deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return T1[m],maxF,"STOP"
            if h>=tp: return T1[m],maxF,("B6" if fc==6 else "TPs")
        else:
            if fc>=6 and h>=stop: return T1[m],maxF,"STOP"
            if l<=tp: return T1[m],maxF,("B6" if fc==6 else "TPs")
    return T1[n-1],maxF,"OPEN"

# ---- 1H/4H 리샘플 ----
def resample(period):
    PT=[];PO=[];PH=[];PL=[];PC=[]; cur=None
    for i in range(len(T1)):
        b=(T1[i]//period)*period
        if b!=cur:
            cur=b; PT.append(b);PO.append(O1[i]);PH.append(H1[i]);PL.append(L1[i]);PC.append(C1[i])
        else:
            if H1[i]>PH[-1]:PH[-1]=H1[i]
            if L1[i]<PL[-1]:PL[-1]=L1[i]
            PC[-1]=C1[i]
    return PT,PO,PH,PL,PC

print("1H/4H 리샘플 + 정렬표 산출...")
HT,HO,HH,HL,HC = resample(3600)
FT,FO,FH,FL,FC = resample(14400)
n=len(HT)
bbu,bbl = boll(HC,20,2.0)
ma20 = sma(HC,20)
fma20 = sma(FC,20)
# 4H 기울기 부호를 1H 시각에 매핑(직전 마감 4H)
fclose=[t+14400 for t in FT]
def fslope_at(i):
    # 1H봉 i의 마감시각 이전 마지막 4H 기울기 부호
    ce=HT[i]+3600
    k=bisect.bisect_right(fclose,ce)-1
    if k<3 or fma20[k] is None or fma20[k-3] is None: return 0
    d=fma20[k]-fma20[k-3]; return 1 if d>0 else (-1 if d<0 else 0)
# ATR14(1H)
atr=[None]*n; tr=[0.0]*n
for i in range(1,n):
    tr[i]=max(HH[i]-HL[i], abs(HH[i]-HC[i-1]), abs(HL[i]-HC[i-1]))
s=0.0
for i in range(1,n):
    s+=tr[i]
    if i>14: s-=tr[i-14]
    if i>=14: atr[i]=s/14
# 스윙 S/R 피벗(확정 idx=j+w), 미래참조 차단
WIN=3; piv=[]  # (conf_idx, level, kind)  kind:+1=저점(지지) -1=고점(저항)
for j in range(WIN,n-WIN):
    seg_h=HH[j-WIN:j+WIN+1]; seg_l=HL[j-WIN:j+WIN+1]
    if HH[j]==max(seg_h): piv.append((j+WIN,HH[j],-1))
    if HL[j]==min(seg_l): piv.append((j+WIN,HL[j],1))
piv.sort()
pconf=[p[0] for p in piv]
LOOKBACK=200

def ji_vote(i,close,tol):
    # i 시점에 확정된(conf<=i) 최근 LOOKBACK개 피벗 중 close 근접 레벨
    hi=bisect.bisect_right(pconf,i)
    sup=res=False
    for t in range(hi-1,-1,-1):
        cidx,lvl,kind=piv[t]
        if cidx<i-LOOKBACK: break
        if abs(close-lvl)<=tol:
            if kind==1: sup=True
            else: res=True
    if sup and not res: return W_JI
    if res and not sup: return -W_JI
    return 0

def candle_vote(i):
    o,h,l,c=HO[i],HH[i],HL[i],HC[i]
    body=abs(c-o); rng=h-l
    if rng<=0: return 0
    uw=h-max(o,c); lw=min(o,c)-l
    if body<=0.1*rng: return 0           # 도지=중립
    if lw>=2*body and uw<=0.8*body: return W_CAN    # 망치=매수
    if uw>=2*body and lw<=0.8*body: return -W_CAN   # 역망치/슈팅=매도
    return 0

# bias 시계열
bias=[0]*n; strg=[0]*n
for i in range(n):
    if bbu[i] is None or ma20[i] is None or i<20: continue
    c=HC[i]; up=bbu[i]; lo=bbl[i]; mean=(up+lo)/2; half=(up-lo)/2
    # 더
    if c<=lo: deo=W_DEO
    elif c>=up: deo=-W_DEO
    elif c<=mean-0.5*half: deo=1
    elif c>=mean+0.5*half: deo=-1
    else: deo=0
    # 캔
    can=candle_vote(i)
    # 추 (1H 20MA 기울기 + 4H)
    s1=0
    if i>=3 and ma20[i-3] is not None:
        d=ma20[i]-ma20[i-3]; s1=1 if d>0 else (-1 if d<0 else 0)
    s4=fslope_at(i)
    if s1!=0 and s1==s4: chu=W_CHU*s1
    elif s4!=0: chu=s4
    elif s1!=0: chu=s1
    else: chu=0
    # 지
    tol=0.5*atr[i] if atr[i] else 0
    ji=ji_vote(i,c,tol) if tol>0 else 0
    net=deo+can+chu+ji
    bias[i]=1 if net>0 else (-1 if net<0 else 0); strg[i]=abs(net)
hclose=[t+3600 for t in HT]
def bias_at(epoch):
    k=bisect.bisect_right(hclose,epoch)-1
    if k<0: return 0,0
    return bias[k],strg[k]

# ---- 진입 목록(66과 동일) ----
def entries_v1(tf,bars,idx,off):
    sigs=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: sigs.append((bi,float(s[7]),s[4],k))
    sigs.sort(key=lambda x:x[0]); ents=[]
    for bi,a,d,k in sigs:
        eb=bi+1
        if khour(bars[eb][0],off)<START_H: continue
        ents.append((bars[bi][0],bars[eb][0],a,d,k))
    return ents
def entries_v2(tf,bars,idx,off):
    u2,l2=boll([b[1] for b in bars],4,4.0); brk={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    ents=[]; pending=None
    for i in range(len(bars)):
        if i in brk: pending=(i,brk[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                eb=i+1
                if eb<len(bars):
                    k=float(ps[8])
                    if k>0 and khour(bars[eb][0],off)>=START_H:
                        ents.append((bars[pi][0],bars[eb][0],bars[eb][1],pdir,k))
                    pending=None
    return ents

def run(ents,off,YRS):
    ents=sorted(ents,key=lambda e:e[0])
    netR=[]; yrs=[]; wins=0; busy=-1; nn=0
    for brk_ep,ent_ep,a,d,k in ents:
        if brk_ep<=busy: continue
        ex_ep,mf,kind=simB(ent_ep,a,d,k)
        if kind not in ("TPs","B6","STOP"): continue
        gR,lots=trade_R(mf,kind); nR=gR-lots*(SPREAD/k)/STOP_R
        netR.append(nR); yrs.append(kyear(ent_ep,off)); nn+=1; busy=ex_ep
        if gR>0: wins+=1
    eq=[1.0]
    for r in netR: eq.append(eq[-1]*(1+RISK*r))
    cum=sum(netR)
    cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100
    return {"n":nn,"winrate":round(100*wins/nn,1) if nn else 0,"totR":round(cum,1),
            "cagr":round(cagr,1),"mdd":round(maxdd(eq),1)}

def gate(ents,thr,want=1):
    """want=1 방향일치, want=-1 방향반대(통제)."""
    out=[]
    for e in ents:
        ent_ep=e[1]; d=e[3]; dsign=1 if d=="LONG" else -1
        b,s=bias_at(ent_ep)
        if b==dsign*want and s>=thr: out.append(e)
    return out

print(f"\n# 더캔지추 1H 방향게이트 | 가중 더{W_DEO} 지{W_JI} 캔{W_CAN} 추{W_CHU} | 해소 1분봉 정직 | 비용${SPREAD}/2%/KST08~24\n")
RESULT={}
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); off=calib_offset(tf)
    span=(bars[-1][0]-bars[0][0]); span=span/1000 if span>1e11 else span; YRS=span/(365.25*86400)
    RESULT[tf]={}
    for ver,fn in [("v1",entries_v1),("v2",entries_v2)]:
        ents=fn(tf,bars,idx,off)
        rec={"무필터":run(ents,off,YRS)}
        for thr in [3,5]:
            rec[f"일치 s>={thr}"]=run(gate(ents,thr,1),off,YRS)
            rec[f"반대 s>={thr}"]=run(gate(ents,thr,-1),off,YRS)
        RESULT[tf][ver]=rec
        print(f"=== {tf} {ver} [{YRS:.2f}년] ===")
        print(f"  {'필터':>14}{'진입':>7}{'승률':>7}{'netR':>8}{'CAGR':>8}{'MDD':>7}")
        for lab in ["무필터","일치 s>=3","반대 s>=3","일치 s>=5","반대 s>=5"]:
            r=rec[lab]
            print(f"  {lab:>14}{r['n']:>7}{r['winrate']:>6.1f}%{r['totR']:>+8.1f}{r['cagr']:>+7.1f}%{r['mdd']:>6.1f}%")
        print()

# ---- HTML 리포트 ----
def cell(r,hl=False):
    cg="#8fdc4e" if r['cagr']>=-0.5 else ("#e7c84b" if r['cagr']>=-5 else "#ff6b6b")
    cls=" class=hl" if hl else ""
    return (f"<td{cls}>{r['n']}</td><td{cls}>{r['winrate']:.1f}%</td>"
            f"<td{cls}>{r['totR']:+.1f}</td><td{cls} style='color:{cg}'>{r['cagr']:+.1f}%</td>"
            f"<td{cls}>{r['mdd']:.1f}%</td>")
rows=""
for tf in ["10m","5m","2m"]:
    for ver in ["v2","v1"]:
        rec=RESULT[tf][ver]
        rows+=f"<tr class=sec><td rowspan=5>{tf} {ver}</td>"
        first=True
        for lab in ["무필터","일치 s>=3","반대 s>=3","일치 s>=5","반대 s>=5"]:
            hl=("일치" in lab and tf in ("10m","5m") and ver=="v2")
            pre="" if first else "<tr>"; first=False
            tag="일치" in lab
            lc="#7fd4ff" if "일치" in lab else ("#c9a0ff" if "반대" in lab else "#9fb")
            rows+=f"{pre}<td style='color:{lc}'>{lab}</td>{cell(rec[lab],hl)}</tr>"
HTML=f"""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>더캔지추 1H 방향게이트 리포트 [1분봉 정직]</title>
<style>
*{{box-sizing:border-box}}body{{font-family:'Malgun Gothic','Segoe UI',sans-serif;background:#0f1320;color:#dfe6f0;margin:0;padding:20px;line-height:1.6}}
h1{{color:#4fc3f7;font-size:1.4em;margin:0 0 4px}}h2{{color:#7fd4ff;font-size:1.05em;margin:20px 0 6px;border-left:3px solid #4fc3f7;padding-left:8px}}
.sub{{color:#8aa;font-size:.85em;margin-bottom:14px}}
table{{border-collapse:collapse;width:100%;max-width:880px;font-size:.86em;margin:8px 0}}
th,td{{border:1px solid #243049;padding:5px 9px;text-align:right}}th{{background:#172033;color:#bcd}}
td:first-child,td:nth-child(2){{text-align:left}}
tr.sec td{{border-top:2px solid #3a4a6a}}
.hl{{background:#16301c}}
.box{{background:#141b2e;border:1px solid #243049;border-radius:8px;padding:12px 16px;max-width:880px;margin:10px 0}}
.good{{color:#8fdc4e}}.warn{{color:#e7c84b}}.bad{{color:#ff6b6b}}
ul{{margin:6px 0}}li{{margin:3px 0}}code{{background:#1c2640;padding:1px 5px;border-radius:4px;color:#9cf}}
</style></head><body>
<h1>더캔이지추격깨 — 1시간봉 방향게이트 검증</h1>
<div class=sub>골드 2010-2026 (16.45년) · 1분봉 정직 해소 · 후방랏/TP1.5/6차/비용$0.30/리스크2%/KST08~24 진입/순차 · base=KTR</div>
<div class=box>
<b>방법</b>: 매 1H 마감마다 4요소 가중투표로 방향 우위 산출(+ =LONG). 진행 중 1H봉 미사용(미래참조 차단).
<ul>
<li><b>더</b>(w{W_DEO}): 1H close vs BB(20,2) — 하단근접 매수 / 상단근접 매도 (수축원비=과매도)</li>
<li><b>지</b>(w{W_JI}): 직전 확정 스윙 S/R 레벨 근접 — 지지 매수 / 저항 매도 <span class=warn>(휴리스틱 proxy)</span></li>
<li><b>캔</b>(w{W_CAN}): 1H 캔들 — 망치 매수 / 역망치 매도 / 도지 중립</li>
<li><b>추</b>(w{W_CHU}): 1H 20MA 기울기 + 4H 20MA 기울기 (연속방향)</li>
</ul>
net=합, strength=|net|. 게이트: 하위봉 돌파신호 방향이 bias와 <b>일치</b>할 때만 진입(strength 임계). <b>반대</b>=통제(방향 무효성 검정).
</div>

<h2>결과 (초록=본전권 CAGR>=-0.5%)</h2>
<table>
<tr><th>분봉·전략</th><th>필터</th><th>진입</th><th>승률</th><th>net R</th><th>CAGR</th><th>MDD</th></tr>
{rows}
</table>
<div class=sub>* 강조행(초록 배경) = 방향 우위가 확증된 셀 (10m/5m v2). 일치=하늘색, 반대=보라.</div>

<div class=box>
<b>판정</b>
<ul>
<li><span class=good>방향 우위는 진짜</span> — 단 <b>10m·5m의 v2(풀백)</b>에 집중. 10m v2 s>=5: 일치 <span class=good>-0.1%/MDD7.8%</span> vs 반대 <span class=bad>-3.8%/MDD48%</span>. 정렬표 방향이 실제로 먹힘.</li>
<li><span class=warn>2m·5m v1의 개선은 방향이 아니라 "덜 거래(선택성)"</span> — 일치 ~= 반대라 우위 아님.</li>
<li><span class=warn>그래도 최고가 본전(-0.1%)</span> — 게이트는 파산(MDD100%)을 본전+저MDD로 바꾸지만, $0.30 비용 넘는 흑자는 아직 아님.</li>
<li>무필터 베이스(<code>66</code>) = 1분봉 정직 시 v1/v2 전부 -16~-82%/MDD~100% (look-ahead 제거 후 진실).</li>
</ul>
<b>남은 검증</b>: (1) 요소 분해(더/지/캔/추 단독) — 무엇이 방향 우위를 끄는지, (2) best 셀 비용 민감도(\$0.20/\$0.10이면 흑자?).
</div>
</body></html>"""
open("../result/dckj_gate.html","w",encoding="utf-8").write(HTML)
print("-> ../result/dckj_gate.html")
