# -*- coding: utf-8 -*-
"""TF별 × 반등단계별 도달수익(KTR) 누적분포. (ktr_takeprofit_N, KTR base, 손절제외, 트레일)"""
import csv
from collections import defaultdict

SRC = "ktr_takeprofit_N_all_tf_2020-01-01_2026-06-16.csv"
COL = "최대도달R_트레일1base"
LEVELS = ["바로출발", "1번눌림", "2번눌림"]   # 표본 충분한 단계만
LAB_KTR = {"바로출발":"0차(0ktr)","1번눌림":"1차(-1ktr)","2번눌림":"2차(-2ktr)"}
THR = [0.5, 1, 1.5, 2, 2.5, 3]

rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8-sig"))
        if r["base종류"]=="KTR" and r["손절여부"]=="No"]

# (TF, 단계) -> [도달값들]
g = defaultdict(list)
for r in rows:
    if r["단계라벨"] in LEVELS:
        g[(r["TF"], r["단계라벨"])].append(float(r[COL]))

for lvl in LEVELS:
    print(f"\n{'='*70}\n {LAB_KTR[lvl]}에서 반등 — 바닥기준 몇 KTR까지 가는지 (누적%)\n{'='*70}")
    print(f"   {'TF':<5}{'n':>7}{'평균':>7}{'중앙':>7}" + "".join(f"{'≥'+str(t):>8}" for t in THR))
    for tf in ["2m","5m","10m"]:
        v = g.get((tf,lvl), [])
        if not v: continue
        n=len(v); avg=sum(v)/n; med=sorted(v)[n//2]
        cum="".join(f"{100*sum(1 for x in v if x>=t)/n:>7.0f}%" for t in THR)
        print(f"   {tf:<5}{n:>7}{avg:>7.2f}{med:>7.2f}{cum}")
