# -*- coding: utf-8 -*-
"""49 — 2h 추세필터 검증. '2h 종가 > 2h SMA20이면 LONG만 / < 이면 SHORT만' (추세동행).
순차+시간(08~24)·후방·TP1.5·6차·비용$0.30·리스크2%. 2m·5m·10m × v1/v2.
필터없음 vs 추세필터: net R·CAGR·MDD·거래수 변화. 역추세 차단이 순이득인가?"""
import csv, math
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0
SUM_L=sum(L); STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))
SPREAD=0.30; RISK=0.02; YRS=6.46; START_H=8

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); t=t//1000 if t>1e11 else t
            idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
def resample(b10,p):
    out=[]; cur=None
    for t,o,h,l,c in b10:
        g=(t//p)*p
        if cur is None or cur[0]!=g:
            if cur: out.append(tuple(cur))
            cur=[g,o,h,l,c]
        else: cur[2]=max(cur[2],h);cur[3]=min(cur[3],l);cur[4]=c
    if cur: out.append(tuple(cur))
    return out
def sma(bars,n,si):
    out=[None]*len(bars); s=0.0
    for i in range(len(bars)):
        s+=bars[i][si]
        if i>=n: s-=bars[i-n][si]
        if i>=n-1: out[i]=s/n
    return out
def calib(tf):
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def khour(e,off): return ((e//3600)+off)%24
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
def nidx(bars,ep):
    lo,hi=0,len(bars)-1
    while lo<hi:
        m=(lo+hi)//2
        if bars[m][0]<ep: lo=m+1
        else: hi=m
    return lo
def sim(bars, eb, a, d, base):
    n=len(bars)
    if d=="LONG": E=[a-base*MULT[i] for i in range(6)]; stop=a-base*STOPM
    else:         E=[a+base*MULT[i] for i in range(6)]; stop=a+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(eb,n):
        t,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((d=="LONG" and l<=E[k]) or (d=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr=TP if fc<6 else B6X
        tp=deepest+thr*base if d=="LONG" else deepest-thr*base
        if d=="LONG":
            if fc>=6 and l<=stop: return maxF,"STOP",i
            if h>=tp: return maxF,("B6" if fc==6 else "TPs"),i
        else:
            if fc>=6 and h>=stop: return maxF,"STOP",i
            if l<=tp: return maxF,("B6" if fc==6 else "TPs"),i
    return maxF,"OPEN",n-1
def pnl_tps(k): exitlv=MULT[k-1]-TP; return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6():   exitlv=MULT[5]-B6X; return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(): return sum(L[i]*(MULT[i]-STOPM) for i in range(6))
def trade_R(mf,kind):
    if kind=="STOP": return pnl_stop()/STOP_R, SUM_L
    if kind=="B6":   return pnl_b6()/STOP_R, SUM_L
    return pnl_tps(mf)/STOP_R, sum(L[:mf])
def maxdd(eq):
    peak=eq[0]; m=0.0
    for v in eq:
        if v>peak: peak=v
        dd=(peak-v)/peak
        if dd>m: m=dd
    return 100*m

# 2h 추세 (10m 리샘플 기준, 모든 분봉 공통으로 같은 2h 추세 사용)
b10base,_=load("xauusd_10m_2020-01-01_2026-06-16.csv")
b2h=resample(b10base,7200); sma2h=sma(b2h,20,4)
def trend_up(ep):
    # 룩어헤드 방지: 진입 ep 시점에 '완전히 마감된' 마지막 2h 봉만 사용
    j=nidx(b2h,ep)-1
    while j>=0 and b2h[j][0]+7200>ep: j-=1   # 진행중(미마감) 봉 제외
    if j<0 or sma2h[j] is None: return None
    return b2h[j][4]>sma2h[j]

def run(stf,bars,idx,off,ver,mode):
    if ver=="v1":
        sigs=[]
        with open(f"signals_{stf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
            rd=csv.reader(fp); next(rd)
            for s in rd:
                bi=idx.get(int(s[2]))
                if bi is None or bi+1>=len(bars): continue
                k=float(s[8])
                if k>0: sigs.append((bi,float(s[7]),s[4],k))
        sigs.sort(key=lambda x:x[0]); jobs=[("v1",bi,a,d,k) for bi,a,d,k in sigs]
    else:
        u2,l2=boll([b[1] for b in bars],4,4.0); brk={}
        with open(f"signals_{stf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
            rd=csv.reader(fp); next(rd)
            for s in rd:
                bi=idx.get(int(s[2]))
                if bi is not None: brk[bi]=s
        jobs=("v2",brk,u2,l2)
    netR=[]; busy=-1
    def consider(eb,a,d,k):
        nonlocal busy
        if mode!="none":
            tu=trend_up(bars[eb][0])
            if tu is not None:
                if mode=="both":
                    if d=="LONG" and not tu: return
                    if d=="SHORT" and tu: return
                elif mode=="sonly":   # 역추세 숏만 차단(2h 상승 중 숏 금지)
                    if d=="SHORT" and tu: return
        mf,kind,exi=sim(bars,eb,a,d,k)
        if kind in ("TPs","B6","STOP"):
            gR,lots=trade_R(mf,kind); netR.append(gR-lots*(SPREAD/k)/STOP_R); busy=exi
    if ver=="v1":
        for _,bi,a,d,k in jobs:
            if bi<=busy: continue
            eb=bi+1
            if khour(bars[eb][0],off)<START_H: continue
            consider(eb,a,d,k)
    else:
        _,brk,u2,l2=jobs; pending=None
        for i in range(len(bars)):
            if i<=busy: pending=None; continue
            if i in brk: pending=(i,brk[i]); continue
            if pending:
                pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
                if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                    eb=i+1
                    if eb<len(bars):
                        k=float(ps[8])
                        if k>0 and khour(bars[eb][0],off)>=START_H: consider(eb,pdir,pdir,k) if False else consider(eb,bars[eb][1],pdir,k)
                        pending=None
    n=len(netR); eq=[1.0]
    for r in netR: eq.append(eq[-1]*(1+RISK*r))
    cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100
    return n,round(sum(netR),1),round(cagr,1),round(maxdd(eq),1)

for stf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{stf}_2020-01-01_2026-06-16.csv"); off=calib(stf)
    print(f"\n{'='*78}\n### {stf} (전체기간) ###")
    print(f"{'버전':>4}{'필터':>8}{'거래수':>8}{'net R':>9}{'CAGR':>8}{'MDD':>8}")
    for ver in ["v1","v2"]:
        for md,lab in [("none","없음"),("both","2h양방"),("sonly","숏만차단")]:
            n,R,cagr,mdd=run(stf,bars,idx,off,ver,md)
            print(f"{ver:>4}{lab:>8}{n:>8}{R:>+9.1f}{cagr:>+7.1f}%{mdd:>7.1f}%")
        print()
