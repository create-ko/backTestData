# -*- coding: utf-8 -*-
"""26 — 익절배수(TP) 스윕 (v2 풀백, 풀 6차 그리드, KTR, 등량, 분봉별).
TP=깊은체결+X*base (X=1.0~3.0). 손절 6차 -5*base(-15.5R)로 정규화.
지표: 손절률·기대값(R=base)·MC2%(중앙MDD·손실%). '몇 KTR 익절이 최적인가'."""
import csv, math, random
random.seed(42)
MULT=[0,1,2,3,4,4.5]; TPS=[1.0,1.5,2.0,2.5,3.0]
N_TRADES=2000; M_RUNS=1200; RISK=0.02
STOPpnl=sum(MULT[i]-5 for i in range(6))  # -15.5

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
def sim(bars, eb, direction, base, X):
    n=len(bars); entry=bars[eb][1]
    if direction=="LONG": E=[entry-base*x for x in MULT]; stop=entry-base*5
    else:                 E=[entry+base*x for x in MULT]; stop=entry+base*5
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(eb,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); last=max(k for k in range(6) if filled[k]); deepest=E[last]
        tp=deepest+X*base if direction=="LONG" else deepest-X*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return maxF,"STOP"
            if h>=tp: return maxF,"TP"
        else:
            if fc>=6 and h>=stop: return maxF,"STOP"
            if l<=tp: return maxF,"TP"
    return maxF,"OPEN"
def win_pnl(k,X): return sum(MULT[i]-MULT[k-1]+X for i in range(k))
def mc(vec):
    mdds=[]; finals=[]
    for _ in range(M_RUNS):
        seq=random.choices(vec,k=N_TRADES); eq=1.0; peak=1.0; mdd=0.0
        for p in seq:
            eq*=(1.0+RISK*p)
            if eq>peak: peak=eq
            dd=(peak-eq)/peak
            if dd>mdd: mdd=dd
        mdds.append(mdd); finals.append(eq)
    mdds.sort(); finals.sort()
    return 100*mdds[len(mdds)//2],100*sum(1 for f in finals if f<1)/len(finals)
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
                    if k>0: out.append((i+1,pdir,k)); pending=None
    return out

for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
    jobs=v2_jobs(tf,bars,idx)
    print(f"\n=== {tf} (v2 {len(jobs)}건) ===")
    print(f"{'익절KTR':>7}{'손절률':>8}{'6차도달':>8}{'기대값(R)':>10}{'중앙MDD':>9}{'손실%':>7}")
    best=None
    for X in TPS:
        out=[sim(bars,eb,d,k,X) for eb,d,k in jobs]
        clo=[(mf,ex) for mf,ex in out if ex in ("TP","STOP")]; n=len(clo)
        stop=sum(1 for mf,ex in clo if ex=="STOP"); six=sum(1 for mf,ex in clo if mf==6)
        ps=[STOPpnl if ex=="STOP" else win_pnl(mf,X) for mf,ex in clo]; exp=sum(ps)/n
        vec=[(STOPpnl if ex=="STOP" else win_pnl(mf,X))/abs(STOPpnl) for mf,ex in clo]
        md,loss=mc(vec)
        tag=" (현재)" if X==2.0 else ""
        if best is None or md<best[1]: best=(X,md)
        print(f"{X:>6.1f}{tag}{100*stop/n:>7.2f}%{100*six/n:>7.1f}%{exp:>+9.3f}{md:>8.1f}%{loss:>6.1f}%")
    print(f"   → MDD 최저: {best[0]}KTR")
