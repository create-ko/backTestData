#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
11_tp_lot_optimize.py — TP배수 × 랏스킴 격자 최적화 (KTR base)
============================================================
TP배수별로 경로(체결깊이/손절)가 달라지므로 배수마다 재시뮬.
각 (TP배수, 랏스킴)에서 손절=-1R 정규화 기대값/승률 산출.
  win_units(k,T)=Σ_{i<k} w_i*(mult_i-mult_{k-1}+T) ,  stop_units=Σ w_i*(5-mult_i)
  pnl_R(TP,k)=win_units/stop_units , pnl_R(STOP)=-1
사용: $env:PYTHONIOENCODING='utf-8'; python scripts/11_tp_lot_optimize.py
"""
import csv
from collections import Counter

MULT = [0,1,2,3,4,4.5]
TPS = [1.5, 2.0, 2.5, 3.0, 4.0]
SCHEMES = {
    "등량":          [1,1,1,1,1,1],
    "동일손실":      [1/(5-MULT[i]) for i in range(6)],
    "1·1·1·2·3·4":   [1,1,1,2,3,4],
    "1·1·2·2·3·4":   [1,1,2,2,3,4],
}

def load_bars(f):
    bars=[]; idx={}
    with open(f, encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars)
            bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars, idx

def sim_one(bars, si, direction, bp, base, T):
    if direction=="LONG": E=[bp-base*m for m in MULT]; stop=bp-base*5
    else:                 E=[bp+base*m for m in MULT]; stop=bp+base*5
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(si+1, len(bars)):
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

# 신호+봉 로드 (KTR만)
bars_by={}; idx_by={}
for tf in ["2m","5m","10m"]:
    bars_by[tf], idx_by[tf] = load_bars(f"xauusd_{tf}_2020-01-01_2026-06-16.csv")
sigs=[]
for tf in ["2m","5m","10m"]:
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv", encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            si=idx_by[tf].get(int(s[2]))
            if si is None: continue
            ktr=float(s[8])
            if ktr<=0: continue
            sigs.append((tf,si,s[4],float(s[7]),ktr))
print(f"KTR 신호 {len(sigs)}건 × TP {len(TPS)}종 시뮬...\n")

def stop_units(w): return sum(w[i]*(5-MULT[i]) for i in range(6))
def win_units(w,k,T): return sum(w[i]*(MULT[i]-MULT[k-1]+T) for i in range(k))

# 헤더
print(f"{'TP배수':<8}{'손절%':>7}{'6차%':>7}  " + "".join(f"{n:>16}" for n in SCHEMES))
results={}
for T in TPS:
    outc=[sim_one(bars_by[tf],si,d,bp,ktr,T) for (tf,si,d,bp,ktr) in sigs]
    clo=[(mf,ex) for (mf,ex) in outc if ex in ("TP","STOP")]
    n=len(clo); stop=sum(1 for _,ex in clo if ex=="STOP")
    six=sum(1 for mf,_ in clo if mf==6)
    cells=""
    for name,w in SCHEMES.items():
        su=stop_units(w)
        ps=[(win_units(w,mf,T)/su if ex=="TP" else -1.0) for mf,ex in clo]
        exp=sum(ps)/len(ps); wr=100*sum(1 for p in ps if p>0)/len(ps)
        cells+=f"  {exp:+.4f}({wr:.0f}%)"
        results[(T,name)]=exp
    print(f"{T:<8.1f}{100*stop/n:>6.2f}%{100*six/n:>6.1f}%{cells}")

best=max(results,key=results.get)
print(f"\n최고 기대값 조합: TP {best[0]}배수 × {best[1]}  ({results[best]:+.4f}R/건)")
print("(R=1회 리스크=손절손실. 증거금×리스크%가 1R)")
