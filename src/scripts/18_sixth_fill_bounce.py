# -*- coding: utf-8 -*-
"""
18_sixth_fill_bounce.py
6차 도달 손절 트레이드를, 6차 바닥 기준 손절 전 최고반등(peak6)으로 분류.
'곧장 직행(peak6<0.5)' vs '반등 ≥1KTR 줬다 실패' 구분. v1(즉시)·v2(풀백) 둘 다.
TP=깊은체결+2*base, 손절 6차 -5*base.
"""
import csv, math
from collections import Counter
MULT=[0,1,2,3,4,4.5]; T=2.0

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars)
            bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
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

def sim6(bars, start_i, anchor, direction, base):
    n=len(bars)
    if direction=="LONG": E=[anchor-base*x for x in MULT]; stop=anchor-base*5
    else:                 E=[anchor+base*x for x in MULT]; stop=anchor+base*5
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    d6=None; peak6=0.0
    for i in range(start_i,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])):
                filled[k]=True
        nf=sum(filled)
        if nf!=fc:
            fc=nf; maxF=max(maxF,nf); last=max(k for k in range(6) if filled[k]); deepest=E[last]
            if fc==6 and d6 is None: d6=deepest
        if d6 is not None:
            r6=(h-d6)/base if direction=="LONG" else (d6-l)/base
            if r6>peak6: peak6=r6
        tp=deepest+T*base if direction=="LONG" else deepest-T*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return maxF,"STOP",peak6
            if h>=tp: return maxF,"TP",peak6
        else:
            if fc>=6 and h>=stop: return maxF,"STOP",peak6
            if l<=tp: return maxF,"TP",peak6
    return maxF,"OPEN",peak6

def find_v2_entries(bars,idx,tf):
    u2,l2=boll([b[1] for b in bars],4,4.0)
    brk={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    ent=[]; pending=None
    for i in range(len(bars)):
        if i in brk: pending=(i,brk[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                if i+1<len(bars): ent.append((i+1,ps)); pending=None
    return ent

def collect(version):
    six_stop=[]; six_tp=0; total6=0
    for tf in ["2m","5m","10m"]:
        bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
        if version=="v1":
            with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
                rd=csv.reader(fp); next(rd)
                items=[(idx.get(int(s[2])),s) for s in rd]
            items=[(bi,s) for bi,s in items if bi is not None]
            jobs=[(bi+1, float(s[7]), s[4], float(s[8])) for bi,s in items]  # start=si+1, anchor=bp(돌파가), KTR
        else:
            ent=find_v2_entries(bars,idx,tf)
            jobs=[(eb, bars[eb][1], ps[4], float(ps[8])) for eb,ps in ent]   # start=eb, anchor=open(eb), KTR
        for start_i,anchor,direction,base in jobs:
            if base<=0 or start_i>=len(bars): continue
            mf,ex,peak6=sim6(bars,start_i,anchor,direction,base)
            if mf==6:
                total6+=1
                if ex=="STOP": six_stop.append(peak6)
                elif ex=="TP": six_tp+=1
    return total6, six_tp, six_stop

for version in ["v1","v2"]:
    total6,six_tp,stops=collect(version)
    ns=len(stops)
    print(f"\n=== {version} : 6차 도달 {total6}건 (손절 {ns}, 익절 {six_tp}, 손절률 {100*ns/total6:.0f}%) ===")
    b=Counter()
    for p in stops:
        if p<0.5: b["<0.5 (곧장 직행)"]+=1
        elif p<1: b["0.5~1"]+=1
        elif p<1.5: b["1~1.5"]+=1
        else: b["1.5~2 (크게 반등후 실패)"]+=1
    print("  6차 손절의 '손절 전 최고반등(peak6, KTR)' 분포:")
    for k in ["<0.5 (곧장 직행)","0.5~1","1~1.5","1.5~2 (크게 반등후 실패)"]:
        if b[k]: print(f"    {k:<22}: {b[k]:>5} ({100*b[k]/ns:4.0f}%)")
    ge1=sum(1 for p in stops if p>=1)
    print(f"  → 손절 전 ≥1KTR 반등 준 비율: {100*ge1/ns:.0f}%  (즉 1KTR 반등 시 빠졌으면 살았을 케이스)")
