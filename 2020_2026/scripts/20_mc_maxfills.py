# -*- coding: utf-8 -*-
"""20_mc_maxfills.py — 4차 제한 vs 6차(현재) 몬테카를로 (v2 풀백, TP2, 등량).
각 변형을 손절=-1R로 정규화(동일 리스크 사이징) 후 MDD/파산/손실확률 비교."""
import csv, math, random
random.seed(42)
MULT=[0,1,2,3,4,4.5]; T=2.0
N_TRADES=2000; M_RUNS=2000; RISKS=[0.02,0.05]
CAPS=[4,6]

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
def sim_cap(bars, eb, direction, base, N):
    n=len(bars); entry=bars[eb][1]; sl=MULT[N-1]+0.5
    if direction=="LONG": E=[entry-base*MULT[i] for i in range(N)]; stop=entry-base*sl
    else:                 E=[entry+base*MULT[i] for i in range(N)]; stop=entry+base*sl
    filled=[False]*N; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(eb,n):
        _,o,h,l,c=bars[i]
        for k in range(1,N):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); last=max(k for k in range(N) if filled[k]); deepest=E[last]
        tp=deepest+T*base if direction=="LONG" else deepest-T*base
        if direction=="LONG":
            if fc>=N and l<=stop: return maxF,"STOP"
            if h>=tp: return maxF,"TP"
        else:
            if fc>=N and h>=stop: return maxF,"STOP"
            if l<=tp: return maxF,"TP"
    return maxF,"OPEN"

jobs=[]
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2020-01-01_2026-06-16.csv")
    u2,l2=boll([b[1] for b in bars],4,4.0)
    brk={}
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    pending=None
    for i in range(len(bars)):
        if i in brk: pending=(i,brk[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                if i+1<len(bars):
                    ktr=float(ps[8])
                    if ktr>0: jobs.append((i+1,pdir,ktr,bars))
                    pending=None

def win_pnl(k): return sum(MULT[i]-MULT[k-1]+T for i in range(k))
def stop_pnl(N): sl=MULT[N-1]+0.5; return sum(MULT[i]-sl for i in range(N))

def pnl_vec(N):
    sp=abs(stop_pnl(N)); v=[]
    for eb,pdir,ktr,bars in jobs:
        mf,ex=sim_cap(bars,eb,pdir,ktr,N)
        if ex=="STOP": v.append(-1.0)
        elif ex=="TP": v.append(win_pnl(mf)/sp)
    return v

def mc(vec,r):
    mdds=[]; finals=[]
    for _ in range(M_RUNS):
        seq=random.choices(vec,k=N_TRADES); eq=1.0; peak=1.0; mdd=0.0
        for p in seq:
            eq*=(1.0+r*p)
            if eq>peak: peak=eq
            dd=(peak-eq)/peak
            if dd>mdd: mdd=dd
        mdds.append(mdd); finals.append(eq)
    mdds.sort(); finals.sort()
    return (100*mdds[len(mdds)//2],100*mdds[int(0.95*len(mdds))],
            100*sum(1 for m in mdds if m>=0.5)/len(mdds),100*sum(1 for m in mdds if m>=0.8)/len(mdds),
            finals[len(finals)//2],100*sum(1 for f in finals if f<1)/len(finals))

vecs={N:pnl_vec(N) for N in CAPS}
print(f"v2 풀백 {len(jobs)}건 / 부트스트랩 {N_TRADES}거래×{M_RUNS}회 (손절=-1R 정규화)\n")
for N in CAPS:
    v=vecs[N]; st=100*sum(1 for p in v if p<=-0.999)/len(v)
    print(f"  N={N}차: 건당기대 {sum(v)/len(v):+.4f}R, 손절률 {st:.1f}%")
print(f"\n{'리스크':>5}{'제한':>5}{'중앙MDD':>9}{'95%MDD':>9}{'P(>50%)':>9}{'P(>80%)':>9}{'중앙배수':>9}{'손실%':>8}")
for r in RISKS:
    for N in CAPS:
        m=mc(vecs[N],r)
        print(f"{int(r*100):>4}%{N:>4}차{m[0]:>8.1f}%{m[1]:>8.1f}%{m[2]:>8.1f}%{m[3]:>8.1f}%{m[4]:>8.2f}x{m[5]:>7.1f}%")
