# -*- coding: utf-8 -*-
"""33 — 몇 차에서 손절(그리드 cap)이 좋은가. 후방 사다리 [1,1,2,2,3,4]를 N차까지 잘라 비교.
cap N: 레벨=MULT[:N], 랏=후방[:N], 손절=MULT[N-1]+0.5, TP=1.5, N차 도달시 반등탈출(바닥+1.0).
각 cap을 자기 풀스톱으로 정규화. v2·분봉별. 지표: 도달률·풀스톱%·손실거래%·기대값R·MDD·파산%."""
import csv, math, random
random.seed(42)
MULT=[0,1,2,3,4,4.5]; FULL_LADDER=[1,1,2,2,3,4]; TP=1.5; B6X=1.0
CAPS=[3,4,5,6]
N_TRADES=2000; M_RUNS=1200; RISK=0.02

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

def sim(bars, start_i, anchor, direction, base, N):
    """cap N. 반환 (maxfill, kind)."""
    lv=MULT[:N]; stopd=MULT[N-1]+0.5
    if direction=="LONG": E=[anchor-base*lv[i] for i in range(N)]; stop=anchor-base*stopd
    else:                 E=[anchor+base*lv[i] for i in range(N)]; stop=anchor+base*stopd
    filled=[False]*N; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(start_i,len(bars)):
        _,o,h,l,c=bars[i]
        for k in range(1,N):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); last=max(k for k in range(N) if filled[k]); deepest=E[last]
        thr = TP if fc<N else B6X
        tp = deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=N and l<=stop: return maxF,"STOP"
            if h>=tp: return maxF,("BN" if fc==N else "TPs")
        else:
            if fc>=N and h>=stop: return maxF,"STOP"
            if l<=tp: return maxF,("BN" if fc==N else "TPs")
    return maxF,"OPEN"

def pnl_tps(L,lv,k):   exitlv=lv[k-1]-TP; return sum(L[i]*(lv[i]-exitlv) for i in range(k))
def pnl_bn(L,lv,N):    exitlv=lv[N-1]-B6X; return sum(L[i]*(lv[i]-exitlv) for i in range(N))
def pnl_stop(L,lv,N):  stopd=lv[N-1]+0.5; return sum(L[i]*(lv[i]-stopd) for i in range(N))
def outcome_pnl(L,lv,N,k,kind):
    if kind=="STOP": return pnl_stop(L,lv,N)
    if kind=="BN":   return pnl_bn(L,lv,N)
    return pnl_tps(L,lv,k)
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
                    if k>0: out.append((i+1,bars[i+1][1],pdir,k)); pending=None
    return out

for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
    jobs=v2_jobs(tf,bars,idx)
    print(f"\n{'='*82}\n=== {tf} v2 ({len(jobs)}건) / 후방 사다리 cap별 / TP=1.5 ===")
    print(f"{'cap':>4}{'사다리':>14}{'cap도달%':>9}{'풀스톱%':>8}{'손실거래%':>9}{'기대값R':>9}{'중앙MDD':>9}{'파산%':>7}")
    for N in CAPS:
        L=FULL_LADDER[:N]; lv=MULT[:N]; sref=abs(pnl_stop(L,lv,N))
        outs=[sim(bars,si,a,d,k,N) for si,a,d,k in jobs]
        clo=[(mf,kd) for mf,kd in outs if kd in ("TPs","BN","STOP")]; n=len(clo)
        reach=sum(1 for mf,kd in clo if kd in ("BN","STOP"))   # cap 도달(반등 or 풀스톱)
        stop=sum(1 for mf,kd in clo if kd=="STOP")
        ps=[outcome_pnl(L,lv,N,mf,kd) for mf,kd in clo]
        lose=sum(1 for p in ps if p<0)
        exp=sum(ps)/n/sref
        vec=[p/sref for p in ps]
        md,ruin=mc(vec)
        lad="·".join(map(str,L))
        print(f"{N:>4}{lad:>14}{100*reach/n:>8.1f}%{100*stop/n:>7.2f}%{100*lose/n:>8.1f}%{exp:>+8.3f}{md:>8.1f}%{ruin:>6.1f}%")
