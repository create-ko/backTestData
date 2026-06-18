# -*- coding: utf-8 -*-
"""31 — 랏 사다리 연도별 분할 (v2, TP=1.5, 분봉별). 과최적화/안정성 검증.
연도별로 기대값R(3사다리)·풀스톱률·강후방 MC(MDD·파산) 산출 → 매년 일관된 우위인지 확인."""
import csv, math, random, sys
random.seed(42)
MULT=[0,1,2,3,4,4.5]; TP=float(sys.argv[1]) if len(sys.argv)>1 else 1.5; B6X=1.0; STOPM=5.0
N_TRADES=2000; M_RUNS=1200; RISK=0.02
LADDERS={"등량":[1,1,1,1,1,1],"후방":[1,1,2,2,3,4],"강후방":[1,1,2,3,5,8]}
YEARS=["2020","2021","2022","2023","2024","2025","2026"]

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
def pnl_tps(L,k):
    exitlv=MULT[k-1]-TP; return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6(L):
    exitlv=MULT[5]-B6X; return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(L):
    return sum(L[i]*(MULT[i]-STOPM) for i in range(6))
def outcome_pnl(L,k,kind):
    if kind=="STOP": return pnl_stop(L)
    if kind=="B6": return pnl_b6(L)
    return pnl_tps(L,k)
def mc(vec):
    if not vec: return 0,0
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
                    if k>0:
                        yr=ps[1][:4]
                        out.append((i+1,bars[i+1][1],pdir,k,yr)); pending=None
    return out

print(f"# TP={TP} / v2 / 6차반등탈출 X={B6X}\n")
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
    jobs=v2_jobs(tf,bars,idx)
    # 연도별 outcome 수집
    by_year={y:[] for y in YEARS}; allout=[]
    for si,a,d,k,yr in jobs:
        mf,kind=sim(bars,si,a,d,k)
        if kind in ("TPs","B6","STOP"):
            by_year.setdefault(yr,[]).append((mf,kind)); allout.append((mf,kind))
    print(f"{'='*86}\n=== {tf} v2 (전체 청산 {len(allout)}건) ===")
    print(f"{'연도':>6}{'건수':>6}{'풀스톱%':>8} | {'등량R':>7}{'후방R':>7}{'강후방R':>8} | {'강후방MDD':>9}{'강후방파산':>9}")
    for yr in YEARS+["전체"]:
        clo = allout if yr=="전체" else by_year.get(yr,[])
        n=len(clo)
        if n==0:
            print(f"{yr:>6}{0:>6}"); continue
        stop=sum(1 for mf,kd in clo if kd=="STOP")
        cells=[]
        for nm in ["등량","후방","강후방"]:
            L=LADDERS[nm]; sref=abs(pnl_stop(L))
            exp=sum(outcome_pnl(L,mf,kd) for mf,kd in clo)/n/sref
            cells.append(exp)
        Lg=LADDERS["강후방"]; sref=abs(pnl_stop(Lg))
        vec=[outcome_pnl(Lg,mf,kd)/sref for mf,kd in clo]
        md,ruin=mc(vec)
        print(f"{yr:>6}{n:>6}{100*stop/n:>7.2f}% | {cells[0]:>+7.3f}{cells[1]:>+7.3f}{cells[2]:>+8.3f} | {md:>8.1f}%{ruin:>8.1f}%")
    print()
