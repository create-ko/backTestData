# -*- coding: utf-8 -*-
"""68 - 더캔이지추격깨 풀 7요소 1H 방향게이트 + 66 1분봉 정직검증.
67(더/캔/지/추 4요소)를 확장: 이(20+120 정배역배/크로스)·격(이격도+다이버전스)·깨(레벨 몸통돌파) 신규,
추=ZigZag 스윙 피보 되돌림, 지=전일H/L/C+당일시가+첫시간레인지+ZigZag레벨+Dwell매물대.
매 1H 마감마다 가중투표(+ =LONG): 더3 지3 추2 캔1 이1 격1 깨1. net=bias, strength=|net|.
미래참조 차단(진행중 1H봉/미확정 피벗 미사용). 게이트: 하위봉 돌파 방향==bias 일 때만 진입.
해소=66 simB(1분봉). 방향일치 vs 반대 통제. data/에서 실행. 콘솔 ASCII만(규칙3).
ponytail: 격/깨/매물대-방향은 거친 근사(주석 표기). 세션박스는 '당일 첫1H 레인지'로 근사."""
import csv, math, time, bisect

MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0
SUM_L=sum(L); STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))
SPREAD=0.30; RISK=0.02; START_H=8; CAP1M=120*86400
W={"더":3,"지":3,"추":2,"캔":1,"이":1,"격":1,"깨":1}
ZK=3.0      # ZigZag 임계 = ZK*ATR
DW_WIN=300; DW_BINK=0.25; TOL_K=0.4   # dwell 윈도우/빈폭(*ATR)/지 근접오차(*ATR)

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
def kmonth(e,off): e=e//1000 if e>1e11 else e; return time.strftime("%m",time.gmtime(e+off*3600))
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

print("1H/4H 리샘플...")
HT,HO,HH,HL,HC=resample(3600); n=len(HT)
bbu,bbl=boll(HC,20,2.0); ma20=sma(HC,20); ma120=sma(HC,120)
# ATR14
atr=[None]*n; tr=[0.0]*n
for i in range(1,n): tr[i]=max(HH[i]-HL[i],abs(HH[i]-HC[i-1]),abs(HL[i]-HC[i-1]))
s=0.0
for i in range(1,n):
    s+=tr[i]
    if i>14: s-=tr[i-14]
    if i>=14: atr[i]=s/14
# 일/세션 구조 레벨 (KST 일 경계, 세션박스는 '당일 첫1H 레인지'로 근사)
KOFF=9*3600
pdh=[None]*n; pdl=[None]*n; pdc=[None]*n; dopen=[None]*n; fhh=[None]*n; fhl=[None]*n
cur_day=None; ph=pl=pc=None; ch=cl=co=None; f_h=f_l=None
for i in range(n):
    d=(HT[i]+KOFF)//86400
    if d!=cur_day:
        if cur_day is not None: ph,pl,pc=ch,cl,HC[i-1]   # 직전일 H/L/종가
        cur_day=d; ch=HH[i]; cl=HL[i]; co=HO[i]; f_h=HH[i]; f_l=HL[i]
    else:
        if HH[i]>ch: ch=HH[i]
        if HL[i]<cl: cl=HL[i]
    pdh[i]=ph; pdl[i]=pl; pdc[i]=pc; dopen[i]=co; fhh[i]=f_h; fhl[i]=f_l
# ZigZag (ATR 임계), 확정 idx 기록 -> 미래참조 차단
piv=[]  # (conf_idx, pivot_idx, price, kind)  kind:1 저점 -1 고점
trend=1; cur_hi=HH[0]; cur_hi_i=0; cur_lo=HL[0]; cur_lo_i=0
for i in range(1,n):
    th=ZK*(atr[i] or (HH[i]-HL[i]) or 1.0)
    if trend>=0:
        if HH[i]>=cur_hi: cur_hi=HH[i]; cur_hi_i=i
        if cur_hi-HL[i]>=th:
            piv.append((i,cur_hi_i,cur_hi,-1)); trend=-1; cur_lo=HL[i]; cur_lo_i=i
            continue
    if trend<=0:
        if HL[i]<=cur_lo: cur_lo=HL[i]; cur_lo_i=i
        if HH[i]-cur_lo>=th:
            piv.append((i,cur_lo_i,cur_lo,1)); trend=1; cur_hi=HH[i]; cur_hi_i=i
pconf=[p[0] for p in piv]
# 이격도 오실레이터(정규화 편차) + 피벗별 osc 기록
osc=[None]*n
for i in range(n):
    if ma20[i] and atr[i]: osc[i]=(HC[i]-ma20[i])/atr[i]
# Dwell 매물대: 24봉마다 스냅샷(슬로우-무빙이라 캐시). 고체류(>=0.6*max) 빈 중심 = 매물대 레벨.
DW_REFRESH=24; dw_idx=[]; dw_lv=[]
for i in range(0,n,DW_REFRESH):
    lo=max(0,i-DW_WIN); binw=DW_BINK*(atr[i] or 1.0); cnt={}
    for j in range(lo,i):
        a=int(HL[j]/binw); b=int(HH[j]/binw)
        for bb in range(a,b+1): cnt[bb]=cnt.get(bb,0)+1
    if cnt:
        mx=max(cnt.values()); lv=[(bb+0.5)*binw for bb,ct in cnt.items() if ct>=0.6*mx]
    else: lv=[]
    dw_idx.append(i); dw_lv.append(lv)
def dwell_levels(i):
    si=bisect.bisect_right(dw_idx,i)-1
    return dw_lv[si] if si>=0 else []

def divergence(i):
    # 직전 확정 동종 피벗 2개로 일반 다이버전스 (ponytail: 거친 근사)
    hi=bisect.bisect_right(pconf,i)
    highs=[]; lows=[]
    for t in range(hi-1,-1,-1):
        ci,pidx,pr,kind=piv[t]
        if kind==-1 and len(highs)<2 and osc[pidx] is not None: highs.append((pr,osc[pidx]))
        if kind==1 and len(lows)<2 and osc[pidx] is not None: lows.append((pr,osc[pidx]))
        if len(highs)>=2 and len(lows)>=2: break
    v=0
    if len(highs)==2:
        (p2,o2),(p1,o1)=highs[0],highs[1]
        if p2>p1 and o2<o1: v-=1     # 약세 다이버전스
    if len(lows)==2:
        (p2,o2),(p1,o1)=lows[0],lows[1]
        if p2<p1 and o2>o1: v+=1     # 강세 다이버전스
    return v

def zigzag_levels(i):
    hi=bisect.bisect_right(pconf,i); out=[]
    for t in range(hi-1,max(-1,hi-7),-1): out.append(piv[t][2])
    return out
def last_swing(i):
    hi=bisect.bisect_right(pconf,i)
    if hi<2: return None
    a=piv[hi-1]; b=piv[hi-2]  # 최근 2개 확정 피벗
    return b[2],a[2],a[3]      # (이전피벗가, 최근피벗가, 최근kind)

# ---- bias 시계열 ----
bias=[0]*n; strg=[0]*n
for i in range(n):
    if i<120 or bbu[i] is None or ma120[i] is None or atr[i] is None: continue
    c=HC[i]; up=bbu[i]; lo=bbl[i]; mean=(up+lo)/2; half=(up-lo)/2 or 1e-9
    binw=DW_BINK*atr[i]; tol=TOL_K*atr[i]
    # 더
    if c<=lo: deo=W["더"]
    elif c>=up: deo=-W["더"]
    elif c<=mean-0.5*half: deo=1
    elif c>=mean+0.5*half: deo=-1
    else: deo=0
    # 캔
    o,h,l=HO[i],HH[i],HL[i]; body=abs(c-o); rng=(h-l) or 1e-9
    uw=h-max(o,c); lw=min(o,c)-l
    if body<=0.1*rng: can=0
    elif lw>=2*body and uw<=0.8*body: can=W["캔"]
    elif uw>=2*body and lw<=0.8*body: can=-W["캔"]
    else: can=0
    # 이 (20 vs 120 정배/역배 = 골든/데드 상태)
    ev=W["이"] if ma20[i]>ma120[i] else (-W["이"] if ma20[i]<ma120[i] else 0)
    # 추 (ZigZag 피보 되돌림)
    sw=last_swing(i); chu=0
    if sw:
        p_prev,p_last,kind=sw
        leg=abs(p_last-p_prev) or 1e-9
        if kind==-1:   # 상승레그(저점->고점), 고점서 되돌림
            ret=(p_last-c)/leg
            if c<p_last and ret<=0.5: chu=W["추"]
            elif ret<=0.66: chu=1
            else: chu=0
        else:          # 하락레그(고점->저점)
            ret=(c-p_last)/leg
            if c>p_last and ret<=0.5: chu=-W["추"]
            elif ret<=0.66: chu=-1
            else: chu=0
    # 지 (구조레벨 + ZigZag + dwell -> 근접 지지/저항)
    levels=[x for x in [pdh[i],pdl[i],pdc[i],dopen[i],fhh[i],fhl[i]] if x] + zigzag_levels(i) + dwell_levels(i)
    sup=res=False
    for lv in levels:
        if abs(c-lv)<=tol:
            if c>=lv: sup=True
            else: res=True
    ji=W["지"] if (sup and not res) else (-W["지"] if (res and not sup) else 0)
    # 격 (다이버전스, 없으면 극단)
    dv=divergence(i)
    if dv==0:
        if osc[i] is not None and osc[i]<=-2: dv=1
        elif osc[i] is not None and osc[i]>=2: dv=-1
    gk=W["격"]*(1 if dv>0 else (-1 if dv<0 else 0))
    # 깨 (당일/스윙 고저 몸통종가 돌파) - sw 재사용
    shc=[pdh[i]]; slc=[pdl[i]]
    if sw:
        if sw[2]==-1: shc.append(sw[1])   # 최근 피벗이 고점
        else:         slc.append(sw[1])   # 최근 피벗이 저점
    sh=max([x for x in shc if x],default=None); sl=min([x for x in slc if x],default=None)
    kk=W["깨"] if (sh and c>sh) else (-W["깨"] if (sl and c<sl) else 0)
    net=deo+can+ev+chu+ji+gk+kk
    bias[i]=1 if net>0 else (-1 if net<0 else 0); strg[i]=abs(net)
hclose=[t+3600 for t in HT]
def bias_at(epoch):
    k=bisect.bisect_right(hclose,epoch)-1
    if k<0: return 0,0
    return bias[k],strg[k]

# ---- 진입 목록 (66/67 동일) ----
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
    netR=[]; wins=0; busy=-1; nn=0
    byY={}; byM={}
    for brk_ep,ent_ep,a,d,k in ents:
        if brk_ep<=busy: continue
        ex_ep,mf,kind=simB(ent_ep,a,d,k)
        if kind not in ("TPs","B6","STOP"): continue
        gR,lots=trade_R(mf,kind); nR=gR-lots*(SPREAD/k)/STOP_R
        netR.append(nR); nn+=1; busy=ex_ep
        if gR>0: wins+=1
        y=kyear(ent_ep,off); m=kmonth(ent_ep,off)
        a1=byY.setdefault(y,[0.0,0]); a1[0]+=nR; a1[1]+=1
        a2=byM.setdefault(m,[0.0,0]); a2[0]+=nR; a2[1]+=1
    eq=[1.0]
    for r in netR: eq.append(eq[-1]*(1+RISK*r))
    cum=sum(netR); cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100
    return {"n":nn,"winrate":round(100*wins/nn,1) if nn else 0,"totR":round(cum,1),"cagr":round(cagr,1),"mdd":round(maxdd(eq),1),"byY":byY,"byM":byM}
def gate(ents,thr,want=1):
    out=[]
    for e in ents:
        b,s=bias_at(e[1]); dsign=1 if e[3]=="LONG" else -1
        if b==dsign*want and s>=thr: out.append(e)
    return out

print(f"\n# 더캔이지추격깨 풀7요소 게이트 | 가중 {W} | ZigZag {ZK}ATR | 해소 1분봉 정직 | 비용${SPREAD}/2%/KST08~24\n")
RESULT={}
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); off=calib_offset(tf)
    span=(bars[-1][0]-bars[0][0]); span=span/1000 if span>1e11 else span; YRS=span/(365.25*86400)
    RESULT[tf]={}
    for ver,fn in [("v1",entries_v1),("v2",entries_v2)]:
        ents=fn(tf,bars,idx,off)
        rec={"무필터":run(ents,off,YRS)}
        for thr in [5,7]:
            rec[f"일치 s>={thr}"]=run(gate(ents,thr,1),off,YRS)
            rec[f"반대 s>={thr}"]=run(gate(ents,thr,-1),off,YRS)
        RESULT[tf][ver]=rec
        print(f"=== {tf} {ver} [{YRS:.2f}년] ===")
        print(f"  {'필터':>14}{'진입':>7}{'승률':>7}{'netR':>8}{'CAGR':>8}{'MDD':>7}")
        for lab in ["무필터","일치 s>=5","반대 s>=5","일치 s>=7","반대 s>=7"]:
            r=rec[lab]; print(f"  {lab:>14}{r['n']:>7}{r['winrate']:>6.1f}%{r['totR']:>+8.1f}{r['cagr']:>+7.1f}%{r['mdd']:>6.1f}%")
        # 연도별/월별 분해 (일치 vs 반대 s>=5)
        g=rec["일치 s>=5"]; a=rec["반대 s>=5"]
        print(f"  -- 연도별 net R (일치 / 반대, 괄호=건수) --")
        for y in YEARS:
            gy=g["byY"].get(y,[0,0]); ay=a["byY"].get(y,[0,0])
            if gy[1]==0 and ay[1]==0: continue
            print(f"    {y}: 일치 {gy[0]:+6.1f}({gy[1]:>3})  반대 {ay[0]:+6.1f}({ay[1]:>3})")
        print(f"  -- 월별 net R (일치 / 반대) --")
        for m in [f"{x:02d}" for x in range(1,13)]:
            gm=g["byM"].get(m,[0,0]); am=a["byM"].get(m,[0,0])
            print(f"    {m}월: 일치 {gm[0]:+6.1f}({gm[1]:>3})  반대 {am[0]:+6.1f}({am[1]:>3})")
        print()

# HTML
def cell(r):
    cg="#8fdc4e" if r['cagr']>=-0.5 else ("#e7c84b" if r['cagr']>=-5 else "#ff6b6b")
    return f"<td>{r['n']}</td><td>{r['winrate']:.1f}%</td><td>{r['totR']:+.1f}</td><td style='color:{cg}'>{r['cagr']:+.1f}%</td><td>{r['mdd']:.1f}%</td>"
rows=""
for tf in ["10m","5m","2m"]:
    for ver in ["v2","v1"]:
        rec=RESULT[tf][ver]; first=True
        for lab in ["무필터","일치 s>=5","반대 s>=5","일치 s>=7","반대 s>=7"]:
            pre="<tr class=sec>" if first else "<tr>"
            cellfirst=f"<td rowspan=5>{tf} {ver}</td>" if first else ""
            first=False
            lc="#7fd4ff" if "일치" in lab else ("#c9a0ff" if "반대" in lab else "#9fb")
            rows+=f"{pre}{cellfirst}<td style='color:{lc}'>{lab}</td>{cell(rec[lab])}</tr>"
def edge_td(g,a,key):
    gv=g.get(key,[0,0]); av=a.get(key,[0,0])
    e=gv[0]-av[0]; col="#8fdc4e" if e>0.3 else ("#ff6b6b" if e<-0.3 else "#9aa")
    return (f"<td>{gv[0]:+.1f}<small style='color:#789'>({gv[1]})</small></td>"
            f"<td>{av[0]:+.1f}<small style='color:#789'>({av[1]})</small></td>"
            f"<td style='color:{col}'>{e:+.1f}</td>")
breaks=""
for tf in ["10m","5m","2m"]:
    for ver in ["v2","v1"]:
        rec=RESULT[tf][ver]; gY=rec["일치 s>=5"]["byY"]; aY=rec["반대 s>=5"]["byY"]
        gM=rec["일치 s>=5"]["byM"]; aM=rec["반대 s>=5"]["byM"]
        yr="".join(f"<tr><td>{y}</td>{edge_td(gY,aY,y)}</tr>" for y in YEARS if (gY.get(y,[0,0])[1] or aY.get(y,[0,0])[1]))
        mr="".join(f"<tr><td>{m}월</td>{edge_td(gM,aM,m)}</tr>" for m in [f'{x:02d}' for x in range(1,13)])
        breaks+=(f"<details><summary><b>{tf} {ver}</b> 연도별·월별 분해 (일치 s>=5 vs 반대 s>=5)</summary>"
                 f"<div class=split><table class=brk><tr><th>연도</th><th>일치</th><th>반대</th><th>격차</th></tr>{yr}</table>"
                 f"<table class=brk><tr><th>월</th><th>일치</th><th>반대</th><th>격차</th></tr>{mr}</table></div></details>")
HTML=f"""<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>더캔이지추격깨 풀7요소 게이트 [1분봉]</title>
<style>*{{box-sizing:border-box}}body{{font-family:'Malgun Gothic','Segoe UI',sans-serif;background:#0f1320;color:#dfe6f0;margin:0;padding:20px;line-height:1.6}}
h1{{color:#4fc3f7;font-size:1.35em;margin:0 0 4px}}.sub{{color:#8aa;font-size:.85em;margin-bottom:14px}}
table{{border-collapse:collapse;width:100%;max-width:900px;font-size:.86em;margin:8px 0}}th,td{{border:1px solid #243049;padding:5px 9px;text-align:right}}
th{{background:#172033;color:#bcd}}td:first-child,td:nth-child(2){{text-align:left}}tr.sec td{{border-top:2px solid #3a4a6a}}
.box{{background:#141b2e;border:1px solid #243049;border-radius:8px;padding:12px 16px;max-width:900px;margin:10px 0}}ul{{margin:6px 0}}li{{margin:3px 0}}
details{{max-width:900px;margin:6px 0;background:#121a2e;border:1px solid #243049;border-radius:6px;padding:4px 10px}}
summary{{cursor:pointer;color:#9cf;font-size:.9em;padding:4px 0}}
.split{{display:flex;gap:16px;flex-wrap:wrap}}table.brk{{width:auto;font-size:.8em}}table.brk td,table.brk th{{padding:3px 7px}}small{{font-size:.8em}}</style></head><body>
<h1>더캔이지추격깨 — 풀 7요소 1H 방향게이트</h1>
<div class=sub>골드 2010-2026 · 1분봉 정직 해소 · 후방랏/TP1.5/6차/비용$0.30/2%/KST08~24/순차 · 가중 더3 지3 추2 캔1 이1 격1 깨1</div>
<div class=box><b>7요소(1H 마감, 미래참조 차단)</b>: 더=BB(20,2/4,4) 위치 · 캔=망치/역망치/도지 · 이=20vs120 정배역배(골든/데드) · 지=전일H/L/C+당일시가+첫1H레인지+ZigZag레벨+Dwell매물대 · 추=ZigZag 스윙 피보 되돌림(50% 위/아래) · 격=이격도 다이버전스 · 깨=당일/스윙 고저 몸통종가 돌파. <br>⚠️ 추(ZigZag)·지(매물대 dwell)·격/깨는 거친 기계 근사 — 진짜 재량법 아님.</div>
<table><tr><th>분봉·전략</th><th>필터</th><th>진입</th><th>승률</th><th>net R</th><th>CAGR</th><th>MDD</th></tr>{rows}</table>
<div class=sub>일치=하늘색(bias와 돌파 방향 같음), 반대=보라(통제). 일치≫반대면 방향 우위 진짜, 비슷하면 선택성 효과.</div>
<div class=box><b>연도/월 분해 — 방향 우위의 지속성</b><br>
아래 펼치면 일치 s>=5 vs 반대 s>=5의 연도별·월별 net R. <b>격차(=일치−반대)</b> 색: <span style="color:#8fdc4e">초록=일치 우세</span> / <span style="color:#ff6b6b">빨강=반대 우세</span>.<br>
<b>발견</b>: 방향 우위는 <b>2014~2019(약세·횡보)에 집중</b>(반대가 −4~−12로 폭락하는 걸 회피). <b>2020~2026(불장)에선 소멸·역전</b>(2020·2022·2024는 반대가 더 나음). 즉 우위 정체 = 영구 알파가 아니라 <b>나쁜 국면 손실 회피(regime-dependent)</b>. 어느 해도 확실한 흑자는 없음(일치 net R 매년 0 근처 진동).</div>
{breaks}
</body></html>"""
open("../result/dckj_full.html","w",encoding="utf-8").write(HTML)
print("-> ../result/dckj_full.html")
