#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03c_sim_tp2.py — sim(03b)과 동일하되 익절 = 깊은체결 + TPMULT*base (기본 2.0)
입력 : xauusd_{tf}_2020-..csv , signals_{tf}_2020-..csv
출력 : sim_tp2_{tf}_2020-01-01_2026-06-16.csv , sim_tp2_all_tf_...csv
끝에 손절률·체결분포·익절손익구조(등량 랏) 요약 출력.
"""
import csv
from collections import Counter

TPMULT = 2.0
MULT = [0, 1, 2, 3, 4, 4.5]

def load_bars(f):
    bars = []; idx = {}
    with open(f, encoding="utf-8-sig") as fp:
        rd = csv.reader(fp); next(rd)
        for r in rd:
            t = int(float(r[0])); idx[t] = len(bars)
            bars.append((t, float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    return bars, idx

def sim_one(bars, start_i, direction, bp, base):
    if direction == "LONG":
        E = [bp - base*m for m in MULT]; stop = bp - base*5
    else:
        E = [bp + base*m for m in MULT]; stop = bp + base*5
    filled = [False]*6; filled[0] = True
    deepest = E[0]; filledCount = 1; maxFilled = 1
    n = len(bars); sb = bars[start_i]
    maxR = max(0.0, (sb[2]-deepest)/base if direction == "LONG" else (deepest-sb[3])/base)
    for i in range(start_i+1, n):
        t, o, h, l, c = bars[i]
        for k in range(1, 6):
            if not filled[k] and ((direction == "LONG" and l <= E[k]) or (direction == "SHORT" and h >= E[k])):
                filled[k] = True
        fc = sum(filled)
        if fc != filledCount:
            filledCount = fc; maxFilled = max(maxFilled, fc)
            last = max(k for k in range(6) if filled[k]); deepest = E[last]
        tp = deepest + TPMULT*base if direction == "LONG" else deepest - TPMULT*base
        r = (h-deepest)/base if direction == "LONG" else (deepest-l)/base
        if r > maxR: maxR = r
        if direction == "LONG":
            if filledCount >= 6 and l <= stop: return maxFilled, maxR, "STOP", i-start_i
            if h >= tp: return maxFilled, maxR, "TP", i-start_i
        else:
            if filledCount >= 6 and h >= stop: return maxFilled, maxR, "STOP", i-start_i
            if l <= tp: return maxFilled, maxR, "TP", i-start_i
    return maxFilled, maxR, "OPEN", n-1-start_i

def bucket(r): return "<1R" if r < 1.0 else "1~2R" if r < 2.0 else "2~3R" if r < 3.0 else "3R+"
BARFILES = {tf: f"xauusd_{tf}_2020-01-01_2026-06-16.csv" for tf in ["2m","5m","10m"]}
HEADER = ["signal_id","datetime_kst","TF","방향","세션","꼬리비율","fresh","base종류","base값",
          "돌파가","maxFilledCount","maxReachedR","exitReason","stopHit","결과버킷","bars_held"]
combined = []
for tf in ["2m","5m","10m"]:
    bars, idx = load_bars(BARFILES[tf])
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv", encoding="utf-8-sig") as fp:
        rd = csv.reader(fp); next(rd); sigs = list(rd)
    out = []
    for s in sigs:
        ep = int(s[2]); si = idx.get(ep)
        if si is None: continue
        direction, bp = s[4], float(s[7]); ktr, rng = float(s[8]), float(s[9])
        for bk, bval in [("KTR", ktr), ("BREAKOUT", rng)]:
            if bval <= 0: continue
            mf, mr, ex, bh = sim_one(bars, si, direction, bp, bval)
            sh = "TRUE" if (mf >= 6 and ex == "STOP") else "FALSE"
            out.append([s[0], s[1], tf, direction, s[5], s[6], s[10], bk, round(bval,4),
                        bp, mf, round(mr,3), ex, sh, bucket(mr), bh])
    with open(f"sim_tp2_{tf}_2020-01-01_2026-06-16.csv","w",newline="",encoding="utf-8-sig") as fp:
        w = csv.writer(fp); w.writerow(HEADER); w.writerows(out)
    combined += out
with open("sim_tp2_all_tf_2020-01-01_2026-06-16.csv","w",newline="",encoding="utf-8-sig") as fp:
    w = csv.writer(fp); w.writerow(HEADER); w.writerows(combined)
print(f"[생성] sim_tp2_all_tf (TP={TPMULT}배수) {len(combined)}행")

# ---- 요약 (KTR) ----
def win_pnl(k):  # 등량 랏, TP=깊은체결+TPMULT*base
    return sum(MULT[i]-MULT[k-1]+TPMULT for i in range(k))
STOP_PNL = sum(MULT[i]-5 for i in range(6))
ktr = [r for r in combined if r[7] == "KTR"]
clo = [r for r in ktr if r[12] in ("TP","STOP")]
stop = sum(1 for r in clo if r[12] == "STOP")
six = [r for r in clo if r[10] == 6]
print(f"\n=== KTR / TP {TPMULT}배수 (청산 {len(clo)}건) ===")
print(f"전체 손절률: {100*stop/len(clo):.2f}% ({stop}/{len(clo)})")
print(f"6차 도달: {len(six)}건 ({100*len(six)/len(clo):.1f}%) → 손절 {sum(1 for r in six if r[12]=='STOP')}")
print("체결단계 분포: " + " ".join(f"{k}차={sum(1 for r in clo if r[10]==k)}" for k in range(1,7)))
print("익절손익(R, 등량): " + " ".join(f"{k}차={win_pnl(k):+g}" for k in range(1,7)) + f" / 손절={STOP_PNL:+g}")
# 기대값(등량, R=base 단위)
def pnl(r): return win_pnl(r[10]) if r[12]=="TP" else (STOP_PNL if r[12]=="STOP" else None)
ps = [pnl(r) for r in clo if pnl(r) is not None]
print(f"기대값(등량,R=base): {sum(ps)/len(ps):+.3f}R/건  승률 {100*sum(1 for p in ps if p>0)/len(ps):.1f}%")
