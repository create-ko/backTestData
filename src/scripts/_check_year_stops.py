# -*- coding: utf-8 -*-
"""연도별 손절률/체결깊이/도달분포 — '평균의 함정' 검증 (sim_tp2, KTR)."""
import csv
from collections import defaultdict

MULT=[0,1,2,3,4,4.5]
def win_pnl(k): return sum(MULT[i]-MULT[k-1]+2.0 for i in range(k))  # 등량, TP2
STOP=sum(MULT[i]-5 for i in range(6))

rows=[r for r in csv.DictReader(open("sim_tp2_all_tf_2020-01-01_2026-06-16.csv",encoding="utf-8-sig"))
      if r["base종류"]=="KTR" and r["exitReason"] in ("TP","STOP")]
by=defaultdict(list)
for r in rows: by[r["datetime_kst"][:4]].append(r)

print("연도별 (TP 2배수, KTR, 등량 랏):")
print(f"{'연도':<6}{'n':>7}{'손절%':>8}{'6차%':>7}{'승률%':>7}{'기대값(R=base)':>16}")
for yr in sorted(by):
    sub=by[yr]; n=len(sub)
    stop=sum(1 for r in sub if r["exitReason"]=="STOP")
    six=sum(1 for r in sub if r["maxFilledCount"]=="6")
    def pnl(r): return STOP if r["exitReason"]=="STOP" else win_pnl(int(r["maxFilledCount"]))
    ps=[pnl(r) for r in sub]; exp=sum(ps)/n; win=100*sum(1 for p in ps if p>0)/n
    print(f"{yr:<6}{n:>7}{100*stop/n:>7.2f}%{100*six/n:>6.1f}%{win:>6.1f}%{exp:>+14.3f}R")

# 0차 도달 분포 연도별 (평균 vs 중앙 vs 95퍼센타일 vs 최대) — 트레일
tp=[r for r in csv.DictReader(open("ktr_takeprofit_N_all_tf_2020-01-01_2026-06-16.csv",encoding="utf-8-sig"))
    if r["base종류"]=="KTR" and r["손절여부"]=="No" and r["단계라벨"]=="바로출발"]
byy=defaultdict(list)
for r in tp: byy[r["datetime_kst"][:4]].append(float(r["최대도달R_트레일1base"]))
print("\n바로출발 도달KTR 연도별 분포 (평균 옆에 숨은 것):")
print(f"{'연도':<6}{'n':>7}{'평균':>7}{'중앙':>7}{'95%':>7}{'최대':>8}{'≥3KTR%':>9}")
for yr in sorted(byy):
    v=sorted(byy[yr]); n=len(v)
    print(f"{yr:<6}{n:>7}{sum(v)/n:>7.2f}{v[n//2]:>7.2f}{v[int(0.95*n)]:>7.2f}{max(v):>8.2f}{100*sum(1 for x in v if x>=3)/n:>8.1f}%")
