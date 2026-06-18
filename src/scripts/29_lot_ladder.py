# -*- coding: utf-8 -*-
"""29 — 랏 사다리(lot ladder) 비교. 자금 무관, 각 사다리를 자기 풀스톱으로 정규화.
그리드 [0,1,2,3,4,4.5] / 1~5차 TP=깊은체결+1.5 / 6차 반등탈출(바닥+1.0) or 풀스톱(-5).
시뮬(체결·청산 타이밍)은 랏과 무관 → 신호당 1회 돌려 (k, 청산종류) 산출 후 사다리별 손익 적용.
지표: 풀스톱률 · 손실거래%(pnl<0) · 기대값(R) · MC2%(중앙MDD·파산%)."""
import csv, math, random
random.seed(42)
import sys
MULT=[0,1,2,3,4,4.5]; TP=float(sys.argv[1]) if len(sys.argv)>1 else 1.5; B6X=1.0; STOPM=5.0
N_TRADES=2000; M_RUNS=1500; RISK=0.02

LADDERS={
 "등량 1·1·1·1·1·1":   [1,1,1,1,1,1],
 "약후방 1·1·1·2·3·4":  [1,1,1,2,3,4],
 "후방 1·1·2·2·3·4":   [1,1,2,2,3,4],
 "강후방 1·1·2·3·5·8":  [1,1,2,3,5,8],
 "급후방 1·2·3·4·5·6":  [1,2,3,4,5,6],
 "전방 4·3·2·2·1·1":   [4,3,2,2,1,1],
}

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
    """(maxfill k, 청산종류) 반환. 랏 무관."""
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

# 사다리 L에 대한 손익(랏·KTR 단위) — LONG 기준(SHORT 대칭, 부호동일)
def pnl_tps(L,k):   # k차 체결(0..k-1), 청산레벨=MULT[k-1]-TP
    exitlv=MULT[k-1]-TP
    return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6(L):      # 6차, 청산레벨=4.5-B6X
    exitlv=MULT[5]-B6X
    return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(L):    # 6차, 청산레벨=STOPM
    return sum(L[i]*(MULT[i]-STOPM) for i in range(6))

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
    return 100*mdds[len(mdds)//2], 100*sum(1 for f in finals if f<1)/len(finals)

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

def outcome_pnl(L, k, kind):
    if kind=="STOP": return pnl_stop(L)
    if kind=="B6":   return pnl_b6(L)
    return pnl_tps(L,k)  # TPs

for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2020-01-01_2026-06-16.csv")
    JOBS={"v1":v1_jobs(tf,bars,idx),"v2":v2_jobs(tf,bars,idx)}
    print(f"\n{'='*78}\n=== {tf}  (v1 {len(JOBS['v1'])}건 / v2 {len(JOBS['v2'])}건) ===")
    for ver in ["v1","v2"]:
        jobs=JOBS[ver]
        outs=[sim(bars,si,a,d,k) for si,a,d,k in jobs]
        clo=[(mf,kd) for mf,kd in outs if kd in ("TPs","B6","STOP")]; n=len(clo)
        print(f"\n  [{ver}] 청산 {n}건")
        print(f"  {'사다리':<22}{'풀스톱%':>8}{'손실거래%':>9}{'기대값R':>9}{'중앙MDD':>9}{'파산%':>7}")
        for name,L in LADDERS.items():
            sref=abs(pnl_stop(L))
            ps=[outcome_pnl(L,mf,kd) for mf,kd in clo]
            stop_n=sum(1 for mf,kd in clo if kd=="STOP")
            lose_n=sum(1 for p in ps if p<0)
            exp=sum(ps)/n/sref           # R 단위 기대값
            vec=[p/sref for p in ps]
            md,ruin=mc(vec)
            print(f"  {name:<22}{100*stop_n/n:>7.2f}%{100*lose_n/n:>8.1f}%{exp:>+8.3f}{md:>8.1f}%{ruin:>6.1f}%")
