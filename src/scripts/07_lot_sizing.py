#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
07_lot_sizing.py — 랏 설계(분할매수 비중)별 손익 비교
============================================================
원리:
  - 랏 비중은 경로(체결시점/TP/손절)를 바꾸지 않고 각 체결의 가중치만 바꿈
    → 기존 sim 결과(maxFilledCount, exitReason)에 스킴을 덧씌워 손익 재계산
  - 리스크 정규화: 손절(6차 -5*base) 시 총손실 = 1R (증거금×리스크%)
    → 모든 스킴을 'stop = -1R'로 맞춰 공정 비교
그리드(전략 원본): 진입 mult=[0,1,2,3,4,4.5]*base, 손절 -5*base, TP=깊은체결+1*base

손익 공식(랏 가중 w, base 단위 무관 → R 단위):
  stop_units = Σ w_i*(5-mult_i)                 # 손절 시 손실 크기
  win_units(k) = Σ_{i<k} w_i*(mult_i-mult_{k-1}+1)  # k차까지 체결 후 TP
  pnl_R(TP,k) = win_units(k)/stop_units ,  pnl_R(STOP) = -1
사용: $env:PYTHONIOENCODING='utf-8'; python scripts/07_lot_sizing.py [2m|5m|10m]
"""
import csv, sys
from collections import Counter

TF = sys.argv[1] if len(sys.argv) > 1 else None
MULT = [0, 1, 2, 3, 4, 4.5]; STOPLVL = 5

SCHEMES = {
    "등량(현행)":      [1, 1, 1, 1, 1, 1],
    "동일손실":        [1/(STOPLVL-MULT[i]) for i in range(6)],   # ∝ 1/거리
    "1·1·1·2·3·4":     [1, 1, 1, 2, 3, 4],
    "1·1·2·2·3·4":     [1, 1, 2, 2, 3, 4],
    "1·2·3·4·5·6":     [1, 2, 3, 4, 5, 6],
}

def stop_units(w): return sum(w[i]*(STOPLVL-MULT[i]) for i in range(6))
def win_units(w, k): return sum(w[i]*(MULT[i]-MULT[k-1]+1) for i in range(k))

def pnl_R(w, su, row):
    ex = row["exitReason"]
    if ex == "STOP": return -1.0
    if ex == "TP":   return win_units(w, int(row["maxFilledCount"]))/su
    return None

rows = [r for r in csv.DictReader(open("sim_all_tf_2010-01-01_2026-06-16.csv", encoding="utf-8-sig"))
        if r["base종류"] == "KTR" and (TF is None or r["TF"] == TF)]
clo = [r for r in rows if r["exitReason"] in ("TP", "STOP")]
dist = Counter(int(r["maxFilledCount"]) for r in clo)

print(f"\n{'='*78}\n 랏 설계 비교 / KTR / {TF or '전체 TF'} / 청산 {len(clo)}건 (손절=-1R 정규화)\n{'='*78}")
print("체결단계 분포: " + " ".join(f"{k}차={dist.get(k,0)}" for k in range(1, 7)))

# 스킴별 체결단계별 TP 손익(R) 구조
print(f"\n[구조] 각 스킴에서 'k차까지 체결 후 TP' 시 손익(R)  (음수=익절인데 손실)")
print(f"   {'스킴':<14}{'1차':>7}{'2차':>7}{'3차':>7}{'4차':>7}{'5차':>7}{'6차TP':>8}")
for name, w in SCHEMES.items():
    su = stop_units(w)
    cells = "".join(f"{win_units(w,k)/su:>7.3f}" for k in range(1, 7))
    print(f"   {name:<14}{cells}")

# 스킴별 실제 분포 적용 기대값
print(f"\n[성과] 실제 분포 적용 (R = 1회 리스크 = 손절손실)")
print(f"   {'스킴':<14}{'기대값/건':>11}{'승률':>8}{'평균이익':>9}{'평균손실':>9}{'손익비':>9}")
res = []
for name, w in SCHEMES.items():
    su = stop_units(w)
    pnls = [pnl_R(w, su, r) for r in clo]
    pnls = [p for p in pnls if p is not None]
    n = len(pnls); exp = sum(pnls)/n
    wins = [p for p in pnls if p > 0]; loss = [p for p in pnls if p < 0]
    aw = sum(wins)/len(wins) if wins else 0; al = sum(loss)/len(loss) if loss else 0
    rr = abs(al)/aw if aw else 0
    res.append((name, exp))
    print(f"   {name:<14}{exp:>+10.4f}R{100*len(wins)/n:>7.1f}%{aw:>+8.3f}R{al:>+8.3f}R{('1:'+format(rr,'.1f')):>9}")

best = max(res, key=lambda x: x[1])
print(f"\n   → 기대값 최고: {best[0]} ({best[1]:+.4f}R/건)")
print(f"   (증거금 $100k·리스크 10% 가정 시 1R=$10,000 → 건당 ${best[1]*10000:,.0f})\n")
