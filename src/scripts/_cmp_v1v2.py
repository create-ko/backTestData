# -*- coding: utf-8 -*-
"""v1(즉시진입) vs v2(풀백진입) 비교 — KTR, 손절제외, 단계분포 & 평균 도달."""
import csv
from collections import Counter, defaultdict
LAB=["바로출발","1번눌림","2번눌림","3번눌림","4번눌림","6차"]
def load(f):
    return [r for r in csv.DictReader(open(f,encoding="utf-8-sig"))
            if r["base종류"]=="KTR" and r["손절여부"]=="No"]
def stoploadall(f):  # 손절포함 전체(손절률용)
    return [r for r in csv.DictReader(open(f,encoding="utf-8-sig")) if r["base종류"]=="KTR"]

for name,f in [("v1 즉시진입","ktr_takeprofit_N_all_tf_2020-01-01_2026-06-16.csv"),
               ("v2 풀백진입","ktr_takeprofit_N_v2_all_tf_2020-01-01_2026-06-16.csv")]:
    allr=stoploadall(f); nb=len(allr); stop=sum(1 for r in allr if r["손절여부"]=="Yes")
    rows=load(f); n=len(rows)
    cnt=Counter(r["단계라벨"] for r in rows)
    byl=defaultdict(list)
    for r in rows: byl[r["단계라벨"]].append(float(r["최대도달R_트레일1base"]))
    print(f"\n=== {name} (KTR 전체 {nb}건, 손절률 {100*stop/nb:.1f}%) ===")
    print(f"   {'단계':<8}{'비율':>8}{'평균도달':>9}")
    for lab in LAB:
        if cnt[lab]:
            v=byl[lab]
            print(f"   {lab:<8}{100*cnt[lab]/n:>7.1f}%{sum(v)/len(v):>8.2f}")
