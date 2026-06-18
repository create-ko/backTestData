#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
06_strategy_eval.py  — 전략 고도화 분석 (KTR base, sim 기준)
============================================================
입력: sim_all_tf_2010-01-01_2026-06-16.csv

전제(원본 Pine과 동일):
  - 등량 랏 (각 1랏, pyramiding 6)
  - TP = 가장 깊은 체결가 + 1*base (추적형)
  - 손절 = 6차 체결 시 -5*base
손익은 'base(R) 단위 총 포지션 손익'으로 표기 (랏=1 가정, 종목/시점 무관 비교).

[1] 꼬리비율별 성과   (어느 꼬리비율이 좋은가)
[2] 손절/깊은체결 예측 요인 (손절확률 낮추는 필터)
[3] 손익비/기대값     (등량 랏 구조의 R:R)
사용: $env:PYTHONIOENCODING='utf-8'; python scripts/06_strategy_eval.py [2m|5m|10m]
"""
import csv, sys
from collections import defaultdict

TF = sys.argv[1] if len(sys.argv) > 1 else None
MULT = [0, 1, 2, 3, 4, 4.5]

def win_pnl_R(mfc):                       # TP 청산 시 총손익(R)
    dpth = MULT[mfc-1]
    return sum(MULT[i] - dpth + 1 for i in range(mfc))
STOP_PNL_R = sum(MULT[i] - 5 for i in range(6))   # = -15.5
WIN = {m: round(win_pnl_R(m), 2) for m in range(1, 7)}

def pnl_R(row):
    ex = row["exitReason"]
    if ex == "TP":   return WIN[int(row["maxFilledCount"])]
    if ex == "STOP": return STOP_PNL_R
    return None                            # OPEN 제외

rows = [r for r in csv.DictReader(open("sim_all_tf_2010-01-01_2026-06-16.csv", encoding="utf-8-sig"))
        if r["base종류"] == "KTR" and (TF is None or r["TF"] == TF)]
for r in rows:
    r["_pnl"] = pnl_R(r)
    r["_wick"] = float(r["꼬리비율"])
    r["_mfc"] = int(r["maxFilledCount"])
    r["_stop"] = r["stopHit"] == "TRUE"
clo = [r for r in rows if r["_pnl"] is not None]   # 청산된 것

def stats(sub):
    n = len(sub)
    if not n: return None
    stop = sum(1 for r in sub if r["_stop"])
    deep = sum(1 for r in sub if r["_mfc"] >= 3)
    exp = sum(r["_pnl"] for r in sub) / n
    win = sum(1 for r in sub if r["_pnl"] > 0)
    return dict(n=n, stop=stop, deep=deep, exp=exp, winrate=win/n)

def line(label, s):
    print(f"   {label:<16} n={s['n']:>6}  손절{100*s['stop']/s['n']:5.2f}%  "
          f"3차+{100*s['deep']/s['n']:5.2f}%  승률{100*s['winrate']:5.1f}%  기대값{s['exp']:+.3f}R")

scope = TF or "전체 TF"
print(f"\n{'='*72}\n 전략평가 / KTR / {scope} / 청산 {len(clo)}건 (등량 랏, TP=깊은체결+1base)\n{'='*72}")

# [3] 손익 구조 (먼저 — 해석의 기준)
print(f"\n[3] 손익 구조 (등량 랏, R = base 배수)")
print(f"   최대체결별 익절손익(R): " + " ".join(f"{m}차={WIN[m]:+g}" for m in range(1, 7)))
print(f"   6차 손절손익: {STOP_PNL_R:+g}R")
alls = stats(clo)
print(f"   ── 전체: 기대값 {alls['exp']:+.3f}R/건, 승률 {100*alls['winrate']:.1f}%, 손절 {100*alls['stop']/alls['n']:.2f}%")
avgwin = sum(r["_pnl"] for r in clo if r["_pnl"] > 0) / max(1, sum(1 for r in clo if r["_pnl"] > 0))
avglos = sum(r["_pnl"] for r in clo if r["_pnl"] < 0) / max(1, sum(1 for r in clo if r["_pnl"] < 0))
print(f"   평균 이익 {avgwin:+.2f}R / 평균 손실 {avglos:+.2f}R  → 손익비 1:{abs(avglos)/avgwin:.1f}")

# [1] 꼬리비율별
print(f"\n[1] 꼬리비율별 성과 (낮을수록 강한 돌파)")
BINS = [(0,0.05),(0.05,0.10),(0.10,0.20),(0.20,0.35),(0.35,1.01)]
for lo, hi in BINS:
    sub = [r for r in clo if lo <= r["_wick"] < hi]
    s = stats(sub)
    if s: line(f"{lo:.2f}~{hi:.2f}", s)

# [2] 요인별 (손절/깊은체결 낮추기)
print(f"\n[2] 요인별 손절·깊은체결률")
for key in ["방향", "세션", "fresh", "TF"]:
    g = defaultdict(list)
    for r in clo: g[r[key]].append(r)
    print(f"  · {key}")
    for k in sorted(g):
        line("   "+str(k), stats(g[k]))

# 보너스: 꼬리<=0.10 필터 효과
f_on  = stats([r for r in clo if r["_wick"] <= 0.10])
f_off = stats([r for r in clo if r["_wick"] >  0.10])
print(f"\n[보너스] Pine 기본 필터(꼬리<=0.10) 효과")
line("꼬리<=0.10", f_on)
line("꼬리>0.10",  f_off)
print()
