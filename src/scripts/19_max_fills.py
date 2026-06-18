# -*- coding: utf-8 -*-
"""
19_max_fills.py — 최대 체결단계(N) 제한 비교 (v2 풀백진입, TP2, KTR, 등량)
N차까지만 펼치고 손절=마지막체결 +0.5KTR 아래. 얕게 끊을수록 손절 작지만 잦아짐.
지표: 손절손실(R), 손절률, 승률, 기대값(R=base), 기대값/리스크(정규화).
"""
import csv, math, random
random.seed(42)
MULT=[0,1,2,3,4,4.5]; T=2.0

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
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])):
                filled[k]=True
        nf=sum(filled)
        if nf!=fc:
            fc=nf; maxF=max(maxF,nf); last=max(k for k in range(N) if filled[k]); deepest=E[last]
        tp=deepest+T*base if direction=="LONG" else deepest-T*base
        if direction=="LONG":
            if fc>=N and l<=stop: return maxF,"STOP"
            if h>=tp: return maxF,"TP"
        else:
            if fc>=N and h>=stop: return maxF,"STOP"
            if l<=tp: return maxF,"TP"
    return maxF,"OPEN"

# v2 진입 탐색 (전 TF)
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
                    if ktr>0: jobs.append((tf,i+1,pdir,ktr,bars))
                    pending=None

def win_pnl(k): return sum(MULT[i]-MULT[k-1]+T for i in range(k))
def stop_pnl(N): sl=MULT[N-1]+0.5; return sum(MULT[i]-sl for i in range(N))

print(f"v2 풀백진입 {len(jobs)}건 / TP2 / 등량 랏\n")
print(f"{'N차':>4}{'손절손실(R)':>11}{'손절률':>8}{'6차도달x':>9}{'승률':>7}{'기대값(R)':>10}{'기대값/리스크':>13}")
results={}
for N in [3,4,5,6]:
    sp=stop_pnl(N); res=[]
    for tf,eb,pdir,ktr,bars in jobs:
        mf,ex=sim_cap(bars,eb,pdir,ktr,N)
        res.append((mf,ex))
    clo=[(mf,ex) for mf,ex in res if ex in ("TP","STOP")]; nn=len(clo)
    stop=sum(1 for mf,ex in clo if ex=="STOP")
    caphit=sum(1 for mf,ex in clo if mf==N)
    def pnl(mf,ex): return sp if ex=="STOP" else win_pnl(mf)
    ps=[pnl(mf,ex) for mf,ex in clo]; exp=sum(ps)/nn; win=100*sum(1 for p in ps if p>0)/nn
    norm=exp/abs(sp)
    results[N]=(exp,norm,100*stop/nn)
    print(f"{N:>4}{sp:>+10.1f}{100*stop/nn:>7.2f}%{100*caphit/nn:>8.1f}%{win:>6.1f}%{exp:>+9.3f}{norm:>+12.4f}")
print("\n(기대값=R base단위, 기대값/리스크=손절손실로 정규화→리스크당 효율, 클수록 좋음)")
best=max(results,key=lambda k:results[k][1])
print(f"리스크당 효율 최고: {best}차 제한 ({results[best][1]:+.4f})")
