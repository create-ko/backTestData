# -*- coding: utf-8 -*-
"""23 — 분봉별 × v1/v2 × N차(4·5·6) 최대체결 비교 (TP2, KTR, 등량).
v1=즉시진입(앵커=돌파가, start=si+1) / v2=풀백진입(앵커=진입봉시가, start=eb).
지표: 손절률·기대값(R=base) + MC2%(중앙MDD·P(>50%)·손실%)."""
import csv, math, random
random.seed(42)
MULT=[0,1,2,3,4,4.5]; T=2.0; CAPS=[4,5,6]
N_TRADES=2000; M_RUNS=1500; RISK=0.02

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
def sim_cap(bars, start_i, anchor, direction, base, N):
    n=len(bars); sl=MULT[N-1]+0.5
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(N)]; stop=anchor-base*sl
    else:                 E=[anchor+base*MULT[i] for i in range(N)]; stop=anchor+base*sl
    filled=[False]*N; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(start_i,n):
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
def win_pnl(k): return sum(MULT[i]-MULT[k-1]+T for i in range(k))
def stop_pnl(N): sl=MULT[N-1]+0.5; return sum(MULT[i]-sl for i in range(N))
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
    return 100*mdds[len(mdds)//2],100*sum(1 for m in mdds if m>=0.5)/len(mdds),100*sum(1 for f in finals if f<1)/len(finals)

# 진입 jobs: (start_i, anchor, dir, ktr)
def v1_jobs(tf,bars,idx):
    out=[]
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: out.append((bi+1,float(s[7]),s[4],k))
    return out
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
                    if k>0: out.append((i+1,bars[i+1][1],pdir,k)); pending=None
    return out

for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2020-01-01_2026-06-16.csv")
    JOBS={"v1":v1_jobs(tf,bars,idx),"v2":v2_jobs(tf,bars,idx)}
    print(f"\n=== {tf} (v1 {len(JOBS['v1'])}건 / v2 {len(JOBS['v2'])}건) ===")
    print(f"{'버전':>4}{'N차':>4}{'손절%':>8}{'기대값(R)':>10}{'중앙MDD':>9}{'P(>50%)':>9}{'손실%':>7}")
    for ver in ["v1","v2"]:
        jobs=JOBS[ver]
        for N in CAPS:
            sp=stop_pnl(N); out=[sim_cap(bars,si,a,d,k,N) for si,a,d,k in jobs]
            clo=[(mf,ex) for mf,ex in out if ex in ("TP","STOP")]; n=len(clo)
            stop=sum(1 for mf,ex in clo if ex=="STOP")
            ps=[sp if ex=="STOP" else win_pnl(mf) for mf,ex in clo]; exp=sum(ps)/n
            vec=[(-1.0 if ex=="STOP" else win_pnl(mf)/abs(sp)) for mf,ex in clo]
            md,p50,loss=mc(vec)
            print(f"{ver:>4}{N:>4}{100*stop/n:>7.2f}%{exp:>+9.3f}{md:>8.1f}%{p50:>8.1f}%{loss:>6.1f}%")
        print()
