#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04b_takeprofit_N_2020.py  (= 04_takeprofit_N.py 로직 + 신규셋 + 편의컬럼)
입력 : xauusd_{tf}_2010-01-01_2026-06-16.csv , signals_{tf}_2010-01-01_2026-06-16.csv
출력 : ktr_takeprofit_N_all_tf_2010-01-01_2026-06-16.csv

추가 컬럼:
  엔트리기준_도달ktr = 최대도달R - depth(체결단계)
    depth = mult[체결단계-1]  (mult=[0,1,2,3,4,4.5])
    → 스크린샷의 "0ktr까지 / 1ktr까지 ..." (첫 진입가 기준 절대 ktr) 바로 사용
"""
import csv, math

mult = [0, 1, 2, 3, 4, 4.5]
LAB = {1: "바로출발", 2: "1번눌림", 3: "2번눌림", 4: "3번눌림", 5: "4번눌림", 6: "6차"}

def load(f):
    bars = []; idx = {}
    with open(f, encoding="utf-8-sig") as fp:
        rd = csv.reader(fp); next(rd)
        for r in rd:
            t = int(float(r[0])); idx[t] = len(bars)
            bars.append((t, float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    return bars, idx

TRAIL = 1.0   # 컬럼 B 트레일링 되밀림 (base 단위) — 조정 가능

def run(bars, n, si, direction, bp, base):
    """한 번의 전방 스캔으로 두 MFE를 동시에 산출.
       A(본전복귀): 진입가 복귀 시 측정 종료. fc/단계라벨도 이 시점 기준.
       B(트레일):  고점에서 TRAIL*base 되밀림(또는 6차 -5손절/데이터끝)까지 추적."""
    if si+1 >= n or base <= 0: return None
    E = [bp-base*m for m in mult] if direction == "LONG" else [bp+base*m for m in mult]
    stop = bp-base*5 if direction == "LONG" else bp+base*5
    e1 = bars[si+1][1]
    fpx = [None]*6; fpx[0] = e1; filled = [False]*6; filled[0] = True
    deepest = e1; peak = 0.0; wentPos = False; peakbar = 0
    # 컬럼 A 캡처(1회) + 컬럼 B 누적
    aDone = False; fcA = 1; peakA = 0.0; pbA = 0; stoppedA = False
    peakB = 0.0
    for j, i in enumerate(range(si+1, n)):
        _, o, h, l, c = bars[i]; newfill = False
        for k in range(1, 6):
            if not filled[k] and ((direction == "LONG" and l <= E[k]) or (direction == "SHORT" and h >= E[k])):
                filled[k] = True; fpx[k] = E[k]; newfill = True
        fc = sum(filled); last = max(k for k in range(6) if filled[k])
        if newfill:
            deepest = fpx[last]; peak = 0.0; wentPos = False   # 더 깊은 바닥 -> 기준 리셋(A·B 공통)
        r = (h-deepest)/base if direction == "LONG" else (deepest-l)/base
        if r > peak: peak = r; peakbar = j
        if r > peakB: peakB = r
        # 6차 -5 손절 = 둘 다 강제 종료
        if fc >= 6 and ((direction == "LONG" and l <= stop) or (direction == "SHORT" and h >= stop)):
            if not aDone: fcA, peakA, pbA, stoppedA, aDone = fc, peak, j, True, True
            return fcA, peakA, pbA, stoppedA, e1, peakB
        # 컬럼 A: 본전복귀 종료(캡처만, 스캔은 계속)
        if not aDone:
            if direction == "LONG":
                if h > deepest: wentPos = True
                if wentPos and l <= deepest: fcA, peakA, pbA, aDone = fc, peak, j, True
            else:
                if l < deepest: wentPos = True
                if wentPos and h >= deepest: fcA, peakA, pbA, aDone = fc, peak, j, True
        # 컬럼 B: 고점에서 TRAIL*base 되밀림 -> 종료
        if peak >= TRAIL and ((direction == "LONG" and l <= deepest + (peak-TRAIL)*base)
                              or (direction == "SHORT" and h >= deepest - (peak-TRAIL)*base)):
            if not aDone: fcA, peakA, pbA, aDone = fc, peak, j, True
            return fcA, peakA, pbA, stoppedA, e1, peakB
    if not aDone: fcA, peakA, pbA = sum(filled), peak, peakbar
    return fcA, peakA, pbA, stoppedA, e1, peakB

HEADER = ["signal_id", "datetime_kst", "TF", "방향", "세션", "꼬리비율", "진입가",
          "base종류", "base값", "체결단계", "단계라벨", "익절가능N",
          "최대도달R_본전복귀", "최대도달R_트레일1base", "엔트리기준_도달ktr", "손절여부", "도달봉수"]
out = []
for tf, bf in [("2m",  "xauusd_2m_2010-01-01_2026-06-16.csv"),
               ("5m",  "xauusd_5m_2010-01-01_2026-06-16.csv"),
               ("10m", "xauusd_10m_2010-01-01_2026-06-16.csv")]:
    bars, idx = load(bf); n = len(bars)
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv", encoding="utf-8-sig") as fp:
        rd = csv.reader(fp); next(rd)
        for s in rd:
            if s[10] != "TRUE": continue                  # fresh only
            si = idx.get(int(s[2]))
            if si is None: continue
            for bk, bval in [("KTR", float(s[8])), ("BREAKOUT", float(s[9]))]:
                res = run(bars, n, si, s[4], float(s[7]), bval)
                if res is None: continue
                fc, peak, pb, stopped, e1, peakB = res
                entry_rel = round(peak - mult[fc-1], 3)
                out.append([s[0], s[1], tf, s[4], s[5], s[6], round(e1, 4), bk, round(bval, 4),
                            fc, LAB[fc], math.floor(peak), round(peak, 3), round(peakB, 3), entry_rel,
                            "Yes" if stopped else "No", pb])
with open("ktr_takeprofit_N_all_tf_2010-01-01_2026-06-16.csv", "w", newline="", encoding="utf-8-sig") as fp:
    w = csv.writer(fp); w.writerow(HEADER); w.writerows(out)
k = sum(1 for r in out if r[7] == "KTR")
print(f"총 {len(out)}행 (KTR {k} / BREAKOUT {len(out)-k}) -> ktr_takeprofit_N_all_tf_2010-01-01_2026-06-16.csv")
