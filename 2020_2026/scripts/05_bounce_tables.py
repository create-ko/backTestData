#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05_bounce_tables.py
===================
04b(takeprofit_N) + 03b(sim) 결과 -> 스크린샷 형식 통계 출력 (KTR base 기준)

A. 반등 위치 분포      (단계라벨별, 손절 제외)        ← 스크린샷1
B. 단계라벨별 MFE 분포 (바닥기준 몇 ktr까지, 누적)   ← 스크린샷2~4
C. 손절률 (sim 기준)   (전체 / 6차 코호트 / TF별)

입력: ktr_takeprofit_N_all_tf_2020-01-01_2026-06-16.csv , sim_all_tf_2020-01-01_2026-06-16.csv
사용: python scripts/05_bounce_tables.py [TF]   (TF 생략=전체합산, 또는 2m/5m/10m)
"""
import csv, sys
from collections import Counter, defaultdict

TF_FILTER = sys.argv[1] if len(sys.argv) > 1 else None
LAB_ORDER = ["바로출발", "1번눌림", "2번눌림", "3번눌림", "4번눌림", "6차"]
LAB_KTR = {"바로출발": "0ktr", "1번눌림": "-1ktr", "2번눌림": "-2ktr",
           "3번눌림": "-3ktr", "4번눌림": "-4ktr", "6차": "-4.5ktr"}
THRESH = [0.5, 1, 2, 3, 4, 5]

def load(f):
    with open(f, encoding="utf-8-sig") as fp:
        return list(csv.DictReader(fp))

def pct(a, b): return f"{100*a/b:4.0f}%" if b else "  -"

# ---------- 04: 반등/MFE ----------
tp = [r for r in load("ktr_takeprofit_N_all_tf_2020-01-01_2026-06-16.csv") if r["base종류"] == "KTR"]
if TF_FILTER: tp = [r for r in tp if r["TF"] == TF_FILTER]
scope = TF_FILTER or "전체 TF 합산"
print(f"\n{'='*60}\n KTR base / {scope} / fresh 신호  (총 {len(tp)}건)\n{'='*60}")

bounced = [r for r in tp if r["손절여부"] == "No"]
stopped = [r for r in tp if r["손절여부"] == "Yes"]

# A. 반등 위치 분포
print(f"\n[A] 어디서 반등하나 (손절 제외, n={len(bounced)})")
cA = Counter(r["단계라벨"] for r in bounced)
for lab in LAB_ORDER:
    if cA[lab]:
        print(f"   {LAB_KTR[lab]:>7} ({lab}): {pct(cA[lab], len(bounced))}  ({cA[lab]}회)")

# B. 단계라벨별 MFE(바닥기준) 누적 분포 — 두 정의 비교
def mfe_table(col, title):
    print(f"\n[B] 단계라벨별 '바닥에서 몇 ktr까지' (누적, 손절 제외) / {title}")
    byLab = defaultdict(list)
    for r in bounced:
        byLab[r["단계라벨"]].append(float(r[col]))
    for lab in LAB_ORDER:
        vals = byLab.get(lab, [])
        if not vals: continue
        n = len(vals)
        line = "  ".join(f"≥{t} {pct(sum(1 for v in vals if v >= t), n)}" for t in THRESH)
        print(f"   {lab}({LAB_KTR[lab]}, n={n}): {line}")
mfe_table("최대도달R_본전복귀", "A. 본전복귀 종료(보수)")
mfe_table("최대도달R_트레일1base", "B. 1base 트레일(결국 얼마나)")

# ---------- 03: 손절률 ----------
sim = [r for r in load("sim_all_tf_2020-01-01_2026-06-16.csv") if r["base종류"] == "KTR"]
if TF_FILTER: sim = [r for r in sim if r["TF"] == TF_FILTER]
print(f"\n[C] 손절률 (sim 기준, KTR, n={len(sim)})")
stop = sum(1 for r in sim if r["stopHit"] == "TRUE")
print(f"   전체 손절률: {pct(stop, len(sim))}  ({stop}/{len(sim)})")
c6 = [r for r in sim if r["maxFilledCount"] == "6"]
s6 = sum(1 for r in c6 if r["stopHit"] == "TRUE")
print(f"   6차 도달 코호트 손절률: {pct(s6, len(c6))}  ({s6}/{len(c6)})  ← 위험구간")
print(f"   exitReason: " + ", ".join(f"{k}={v}" for k, v in Counter(r['exitReason'] for r in sim).items()))
# TF별 손절률
if not TF_FILTER:
    print("   TF별 손절률:")
    for tf in ["2m", "5m", "10m"]:
        sub = [r for r in sim if r["TF"] == tf]
        st = sum(1 for r in sub if r["stopHit"] == "TRUE")
        print(f"      {tf}: {pct(st, len(sub))} ({st}/{len(sub)})")
print()
