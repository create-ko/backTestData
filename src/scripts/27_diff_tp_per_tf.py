# -*- coding: utf-8 -*-
"""27 — 차등 익절 검증 (v2 풀백, 풀6차, KTR, 등량, 분봉별).
  Flat1.5 / Flat2.0(현재) / Diff(≤2차=1.5, ≥3차=2.0)
TP=깊은체결+X*base, X는 체결단계에 따라. 손절 6차 -5(-15.5R) 정규화.
지표: 손절률·기대값(R=base)·MC2%(MDD·손실%)."""
import csv, math, random
random.seed(42)
MULT=[0,1,2,3,4,4.5]; N_TRADES=2000; M_RUNS=1200; RISK=0.02
STOPpnl=sum(MULT[i]-5 for i in range(6))  # -15.5

def xmult(fc, mode):
    if mode=="flat15": return 1.5
    if mode=="flat20": return 2.0
    return 1.5 if fc<=2 else 2.0   # diff

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
def sim(bars, eb, direction, base, mode):
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
        X=xmult(fc,mode); tp=deepest+X*base if direction=="LONG" else deepest-X*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return maxF,"STOP"
            if h>=tp: return maxF,"TP"
        else:
            if fc>=6 and h>=stop: return maxF,"STOP"
            if l<=tp: return maxF,"TP"
    return maxF,"OPEN"
def win_pnl(k,mode): X=xmult(k,mode); return sum(MULT[i]-MULT[k-1]+X for i in range(k))
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
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
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

MODES=[("Flat 1.5","flat15"),("Flat 2.0(현재)","flat20"),("Diff ≤2:1.5/≥3:2.0","diff")]
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2020-01-01_2026-06-16.csv")
    jobs=v2_jobs(tf,bars,idx)
    print(f"\n=== {tf} (v2 {len(jobs)}건) ===")
    print(f"{'익절방식':<20}{'손절률':>8}{'기대값(R)':>10}{'중앙MDD':>9}{'손실%':>7}")
    for name,mode in MODES:
        out=[sim(bars,eb,d,k,mode) for eb,d,k in jobs]
        clo=[(mf,ex) for mf,ex in out if ex in ("TP","STOP")]; n=len(clo)
        stop=sum(1 for mf,ex in clo if ex=="STOP")
        ps=[STOPpnl if ex=="STOP" else win_pnl(mf,mode) for mf,ex in clo]; exp=sum(ps)/n
        vec=[(STOPpnl if ex=="STOP" else win_pnl(mf,mode))/abs(STOPpnl) for mf,ex in clo]
        md,loss=mc(vec)
        print(f"{name:<20}{100*stop/n:>7.2f}%{exp:>+9.3f}{md:>8.1f}%{loss:>6.1f}%")
