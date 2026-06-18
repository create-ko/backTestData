#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
12_montecarlo.py — TP 2KTR 기준 드로다운/파산 몬테카를로 (KTR)
============================================================
sim_tp2(=익절 2배수) 결과로 건당 손익(R) 분포 생성 → 부트스트랩 N건 복원추출 ×M회
복리 운용(건당 리스크 r% = 손절 시 -r%). 랏스킴 × 리스크 비교.
지표: 최대낙폭(MDD) 분포, P(MDD>=30/50/80%), 기간말 손실확률, 중앙 수익배수.
"""
import csv, random
random.seed(42)

MULT = [0,1,2,3,4,4.5]; T = 2.0
N_TRADES = 2000     # 1회 시뮬 거래 수(기간)
M_RUNS   = 2000     # 시뮬 횟수
RISKS    = [0.02, 0.05, 0.10]
SCHEMES = {
    "등량":         [1,1,1,1,1,1],
    "동일손실":     [1/(5-MULT[i]) for i in range(6)],
    "1·1·2·2·3·4":  [1,1,2,2,3,4],
}

def stop_units(w): return sum(w[i]*(5-MULT[i]) for i in range(6))
def win_units(w,k): return sum(w[i]*(MULT[i]-MULT[k-1]+T) for i in range(k))

rows = [r for r in csv.DictReader(open("sim_tp2_all_tf_2010-01-01_2026-06-16.csv", encoding="utf-8-sig"))
        if r["base종류"]=="KTR" and r["exitReason"] in ("TP","STOP")]

def pnl_vector(w):
    su = stop_units(w)
    v=[]
    for r in rows:
        if r["exitReason"]=="STOP": v.append(-1.0)
        else: v.append(win_units(w,int(r["maxFilledCount"]))/su)
    return v

def pct(x): return sorted_runs[min(len(sorted_runs)-1, int(x*len(sorted_runs)))]

print(f"TP {T}배수 / KTR {len(rows)}건 / 부트스트랩 {N_TRADES}거래 ×{M_RUNS}회\n")
for name,w in SCHEMES.items():
    v = pnl_vector(w)
    exp = sum(v)/len(v)
    print(f"=== {name}  (건당기대 {exp:+.4f}R, 손절 {100*sum(1 for x in v if x<=-0.999)/len(v):.1f}%) ===")
    print(f"   {'리스크':>6}{'중앙MDD':>9}{'95%MDD':>9}{'최악MDD':>9}{'P(MDD>50%)':>12}{'P(MDD>80%)':>12}{'중앙배수':>9}{'손실확률':>9}")
    for r in RISKS:
        mdds=[]; finals=[]
        for _ in range(M_RUNS):
            seq = random.choices(v, k=N_TRADES)
            eq=1.0; peak=1.0; mdd=0.0
            for p in seq:
                eq *= (1.0 + r*p)
                if eq>peak: peak=eq
                dd=(peak-eq)/peak
                if dd>mdd: mdd=dd
                if eq<=1e-6: break
            mdds.append(mdd); finals.append(eq)
        mdds.sort(); finals.sort()
        med_mdd=mdds[len(mdds)//2]; p95=mdds[int(0.95*len(mdds))]; worst=mdds[-1]
        p50=100*sum(1 for m in mdds if m>=0.50)/len(mdds)
        p80=100*sum(1 for m in mdds if m>=0.80)/len(mdds)
        med_fin=finals[len(finals)//2]
        loss=100*sum(1 for f in finals if f<1.0)/len(finals)
        print(f"   {int(r*100):>5}%{100*med_mdd:>8.1f}%{100*p95:>8.1f}%{100*worst:>8.1f}%"
              f"{p50:>11.1f}%{p80:>11.1f}%{med_fin:>8.2f}x{loss:>8.1f}%")
    print()
