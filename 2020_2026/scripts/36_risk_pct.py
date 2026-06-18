# -*- coding: utf-8 -*-
"""36 — 트레이드당 리스크%(=풀그리드손절을 자본 몇%로 잡나) 민감도. 10m·5m, v1/v2, net(비용$0.30).
우리 R은 이미 '풀스톱=-1R'로 정규화 → RISK=10%면 풀스톱 시 자본 -10%. 사용자 '10% 룰' 직접 모델.
지표: 실제(역사)순서 최종배수·MDD%, 부트스트랩(6.5년길이) 중앙MDD·95%MDD·파산(MDD>=50%)·순손실확률."""
import csv, math, random
random.seed(7)
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0
SUM_L=sum(L); STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))
SPREAD=0.30; RISKS=[0.02,0.05,0.10]; M_RUNS=3000

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
def pnl_tps(k): exitlv=MULT[k-1]-TP; return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6():   exitlv=MULT[5]-B6X; return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(): return sum(L[i]*(MULT[i]-STOPM) for i in range(6))
def trade(maxF,kind):
    if kind=="STOP": pnl=pnl_stop(); lots=SUM_L
    elif kind=="B6": pnl=pnl_b6();   lots=SUM_L
    else:            pnl=pnl_tps(maxF); lots=sum(L[:maxF])
    return pnl/STOP_R, lots
def v1_jobs(tf,bars,idx):
    out=[]
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: out.append((bi+1,float(s[7]),s[4],k))
    out.sort(key=lambda x:x[0]); return out
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
    out.sort(key=lambda x:x[0]); return out

def equity_path(netRs, f):
    eq=1.0; peak=1.0; mdd=0.0
    for r in netRs:
        eq*=(1+f*r)
        if eq<=0: return 0.0, 1.0
        if eq>peak: peak=eq
        d=(peak-eq)/peak
        if d>mdd: mdd=d
    return eq, mdd
def boot(netRs, f, ln):
    mdds=[]; ruin=0; under=0
    for _ in range(M_RUNS):
        seq=random.choices(netRs,k=ln); eq=1.0; peak=1.0; mdd=0.0
        for r in seq:
            eq*=(1+f*r)
            if eq>peak: peak=eq
            d=(peak-eq)/peak
            if d>mdd: mdd=d
        mdds.append(mdd)
        if mdd>=0.5: ruin+=1
        if eq<1: under+=1
    mdds.sort()
    return 100*mdds[len(mdds)//2], 100*mdds[int(len(mdds)*0.95)], 100*ruin/M_RUNS, 100*under/M_RUNS

for tf in ["10m","5m"]:
    bars,idx=load(f"xauusd_{tf}_2020-01-01_2026-06-16.csv")
    JOBS={"v1":v1_jobs(tf,bars,idx),"v2":v2_jobs(tf,bars,idx)}
    print(f"\n{'='*90}\n=== {tf} (net 비용 ${SPREAD}) ===")
    for ver in ["v1","v2"]:
        netRs=[]
        for si,a,d,k in JOBS[ver]:
            mf,kind=sim(bars,si,a,d,k)
            if kind not in ("TPs","B6","STOP"): continue
            gR,lots=trade(mf,kind); netRs.append(gR - lots*(SPREAD/k)/STOP_R)
        ln=len(netRs)
        print(f"\n [{ver}] {ln}건  (풀스톱 1회 = 자본 -리스크%)")
        print(f"  {'리스크%':>7}{'실제최종배수':>12}{'실제MDD%':>10} | {'부트중앙MDD':>11}{'95%MDD':>9}{'파산(MDD>=50%)':>14}{'순손실확률':>10}")
        for f in RISKS:
            fin,mdd=equity_path(netRs,f)
            bm,b95,ruin,under=boot(netRs,f,ln)
            finx=f"{fin:,.1f}x" if fin>0 else "0(파산)"
            print(f"  {f*100:>6.0f}%{finx:>12}{100*mdd:>9.1f}% | {bm:>10.1f}%{b95:>8.1f}%{ruin:>13.1f}%{under:>9.1f}%")
