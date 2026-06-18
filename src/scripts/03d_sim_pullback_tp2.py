#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03d_sim_pullback_tp2.py — 풀백 진입(v2) + TP 2배수 sim. v1(즉시진입)과 비교.
진입: 04c와 동일(돌파 후 BB2 반대편 첫 터치 다음 시가, 다음 돌파 시 기준 교체).
그리드: 새 진입가 앵커, base=원 돌파 KTR/BREAKOUT, TP=깊은체결+2*base, 손절 6차 -5*base.
출력: sim_v2_tp2_all_tf_2020-01-01_2026-06-16.csv + v1/v2 비교 콘솔.
"""
import csv, math
from collections import defaultdict
MULT=[0,1,2,3,4,4.5]; T=2.0
def win_pnl(k): return sum(MULT[i]-MULT[k-1]+T for i in range(k))
STOP_PNL=sum(MULT[i]-5 for i in range(6))   # -15.5

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

def sim(bars, eb, direction, base):
    n=len(bars); entry=bars[eb][1]
    if direction=="LONG": E=[entry-base*x for x in MULT]; stop=entry-base*5
    else:                 E=[entry+base*x for x in MULT]; stop=entry+base*5
    filled=[False]*6; filled[0]=True; deepest=entry; fc=1; maxF=1
    for i in range(eb,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])):
                filled[k]=True
        nf=sum(filled)
        if nf!=fc:
            fc=nf; maxF=max(maxF,nf); last=max(k for k in range(6) if filled[k]); deepest=E[last]
        tp=deepest+T*base if direction=="LONG" else deepest-T*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return maxF,"STOP"
            if h>=tp: return maxF,"TP"
        else:
            if fc>=6 and h>=stop: return maxF,"STOP"
            if l<=tp: return maxF,"TP"
    return maxF,"OPEN"

rows_out=[]
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2020-01-01_2026-06-16.csv"); n=len(bars)
    u2,l2=boll([b[1] for b in bars],4,4.0)
    brk={}
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    pending=None
    for i in range(n):
        if i in brk: pending=(i,brk[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                if i+1<n:
                    eb=i+1; ktr=float(ps[8]); brk_sz=float(ps[9])
                    yr=__import__("datetime").datetime.fromtimestamp(bars[eb][0],__import__("datetime").timezone(__import__("datetime").timedelta(hours=9))).year
                    for bk,bval in [("KTR",ktr),("BREAKOUT",brk_sz)]:
                        if bval<=0: continue
                        mf,ex=sim(bars,eb,pdir,bval)
                        rows_out.append([tf,str(yr),pdir,bk,mf,ex])
                    pending=None
with open("sim_v2_tp2_all_tf_2020-01-01_2026-06-16.csv","w",newline="",encoding="utf-8-sig") as fp:
    w=csv.writer(fp); w.writerow(["TF","연도","방향","base종류","maxFilledCount","exitReason"]); w.writerows(rows_out)

def summ(rows):
    clo=[r for r in rows if r[-1] in ("TP","STOP")]; n=len(clo)
    stop=sum(1 for r in clo if r[-1]=="STOP"); six=sum(1 for r in clo if r[-2]==6 or r[-2]=="6")
    def pnl(r):
        mf=int(r[-2]); return STOP_PNL if r[-1]=="STOP" else win_pnl(mf)
    ps=[pnl(r) for r in clo]; exp=sum(ps)/n; win=100*sum(1 for p in ps if p>0)/n
    return n,100*stop/n,100*six/n,win,exp

# v2 (KTR)
v2=[r for r in rows_out if r[3]=="KTR"]
# v1 (sim_tp2, KTR)
v1=[]
for r in csv.DictReader(open("sim_tp2_all_tf_2020-01-01_2026-06-16.csv",encoding="utf-8-sig")):
    if r["base종류"]=="KTR": v1.append([r["TF"],r["datetime_kst"][:4],r["방향"],"KTR",int(r["maxFilledCount"]),r["exitReason"]])

print("== 전체 (KTR, TP 2배수) ==")
print(f"{'':<14}{'n':>8}{'손절%':>8}{'6차%':>7}{'승률%':>7}{'기대값(R)':>11}")
for name,d in [("v1 즉시진입",v1),("v2 풀백진입",v2)]:
    n,st,si,wn,ex=summ(d); print(f"{name:<14}{n:>8}{st:>7.2f}%{si:>6.1f}%{wn:>6.1f}%{ex:>+10.3f}")
print("\n== 연도별 기대값(R) / 손절% ==")
print(f"{'연도':<6}{'v1 기대':>9}{'v1 손절':>9}{'v2 기대':>9}{'v2 손절':>9}")
for yr in ["2020","2021","2022","2023","2024","2025","2026"]:
    a=summ([r for r in v1 if r[1]==yr]); b=summ([r for r in v2 if r[1]==yr])
    print(f"{yr:<6}{a[4]:>+8.3f}{a[1]:>8.1f}%{b[4]:>+8.3f}{b[1]:>8.1f}%")
