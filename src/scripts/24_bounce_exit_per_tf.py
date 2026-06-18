# -*- coding: utf-8 -*-
"""24 — 6차 반등 탈출 검증 (분봉별 × v1/v2). 6차 도달 시 바닥+X KTR 탈출 vs -5 풀스톱.
X=2.0=현재(익절-0.5R), X<2=반등에서 손실축소 탈출. 손절=-15.5R로 정규화(동일 리스크).
지표: 풀스톱률·기대값(R=base) + MC2%(중앙MDD·손실%)."""
import csv, math, random
random.seed(42)
MULT=[0,1,2,3,4,4.5]; T=2.0; XS=[1.0,1.5,2.0]
N_TRADES=2000; M_RUNS=1200; RISK=0.02
STOPpnl=sum(MULT[i]-5 for i in range(6))  # -15.5
def win_pnl(k): return sum(MULT[i]-MULT[k-1]+T for i in range(k))     # 얕은 TP
def b6_pnl(X): return sum(MULT[i]-(4.5+ (0.5 - 0))  for i in range(6)) if False else (-12.5+6*X)  # 6차 바닥+X 탈출

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
def sim(bars, start_i, anchor, direction, base, X):
    n=len(bars)
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(6)]; stop=anchor-base*5
    else:                 E=[anchor+base*MULT[i] for i in range(6)]; stop=anchor+base*5
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(start_i,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr=T if fc<6 else X
        tp=deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return maxF,"STOP"
            if h>=tp: return maxF,("B6" if fc==6 else "TPs")
        else:
            if fc>=6 and h>=stop: return maxF,"STOP"
            if l<=tp: return maxF,("B6" if fc==6 else "TPs")
    return maxF,"OPEN"
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

def v1_jobs(tf,bars,idx):
    out=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: out.append((bi+1,float(s[7]),s[4],k))
    return out
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
                    if k>0: out.append((i+1,bars[i+1][1],pdir,k)); pending=None
    return out

def pnl_base(mf,kind,X):
    if kind=="STOP": return STOPpnl
    if kind=="B6": return -12.5+6*X
    return win_pnl(mf)  # TPs

for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
    JOBS={"v1":v1_jobs(tf,bars,idx),"v2":v2_jobs(tf,bars,idx)}
    print(f"\n=== {tf} ===")
    print(f"{'버전':>4}{'X(탈출)':>8}{'풀스톱%':>9}{'기대값(R)':>10}{'중앙MDD':>9}{'손실%':>7}")
    for ver in ["v1","v2"]:
        jobs=JOBS[ver]
        for X in XS:
            out=[sim(bars,si,a,d,k,X) for si,a,d,k in jobs]
            clo=[(mf,kd) for mf,kd in out if kd in ("TPs","B6","STOP")]; n=len(clo)
            fstop=sum(1 for mf,kd in clo if kd=="STOP")
            ps=[pnl_base(mf,kd,X) for mf,kd in clo]; exp=sum(ps)/n
            vec=[pnl_base(mf,kd,X)/abs(STOPpnl) for mf,kd in clo]
            md,p50,loss=mc(vec)
            tag=" (현재)" if X==2.0 else ""
            print(f"{ver:>4}{X:>7.1f}{tag}{100*fstop/n:>8.2f}%{exp:>+9.3f}{md:>8.1f}%{loss:>6.1f}%")
        print()
