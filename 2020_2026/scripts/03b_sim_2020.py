#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03b_sim_2020.py  (= 03_sim.py 로직 동일, 입출력만 2020~2026 신규셋)
입력 : xauusd_{2m|5m|10m}_2020-01-01_2026-06-16.csv , signals_{tf}_2020-01-01_2026-06-16.csv
출력 : sim_{tf}_2020-01-01_2026-06-16.csv , sim_all_tf_2020-01-01_2026-06-16.csv
손절률 분석용: maxFilledCount/maxReachedR(+1ktr 익절 캡)/exitReason/stopHit/결과버킷/bars_held
"""
import csv

def load_bars(f):
    bars = []; idx = {}
    with open(f, encoding="utf-8-sig") as fp:
        rd = csv.reader(fp); next(rd)
        for r in rd:
            t = int(float(r[0])); idx[t] = len(bars)
            bars.append((t, float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    return bars, idx

def sim_one(bars, start_i, direction, bp, base):
    mult = [0, 1, 2, 3, 4, 4.5]
    if direction == "LONG":
        E = [bp - base*m for m in mult]; stop = bp - base*5
    else:
        E = [bp + base*m for m in mult]; stop = bp + base*5
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
        tp = deepest + base if direction == "LONG" else deepest - base
        r = (h-deepest)/base if direction == "LONG" else (deepest-l)/base
        if r > maxR: maxR = r
        if direction == "LONG":
            if filledCount >= 6 and l <= stop: return maxFilled, maxR, "STOP", i-start_i
            if h >= tp: return maxFilled, maxR, "TP", i-start_i
        else:
            if filledCount >= 6 and h >= stop: return maxFilled, maxR, "STOP", i-start_i
            if l <= tp: return maxFilled, maxR, "TP", i-start_i
    return maxFilled, maxR, "OPEN", n-1-start_i

def bucket(r):
    return "<1R" if r < 1.0 else "1~2R" if r < 2.0 else "2~3R" if r < 3.0 else "3R+"

BARFILES = {"2m": "xauusd_2m_2020-01-01_2026-06-16.csv",
            "5m": "xauusd_5m_2020-01-01_2026-06-16.csv",
            "10m": "xauusd_10m_2020-01-01_2026-06-16.csv"}
HEADER = ["signal_id", "datetime_kst", "TF", "방향", "세션", "꼬리비율", "fresh",
          "base종류", "base값", "돌파가", "maxFilledCount", "maxReachedR",
          "exitReason", "stopHit", "결과버킷", "bars_held"]

combined = []
for tf in ["2m", "5m", "10m"]:
    bars, idx = load_bars(BARFILES[tf])
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv", encoding="utf-8-sig") as fp:
        rd = csv.reader(fp); next(rd); sigs = list(rd)
    out = []
    for s in sigs:
        sid, dttxt, ep, direction, sess = s[0], s[1], int(s[2]), s[4], s[5]
        wick, ktr, rng, fresh, bp = s[6], float(s[8]), float(s[9]), s[10], float(s[7])
        si = idx.get(ep)
        if si is None: continue
        for bk, bval in [("KTR", ktr), ("BREAKOUT", rng)]:
            if bval <= 0: continue
            mf, mr, ex, bh = sim_one(bars, si, direction, bp, bval)
            sh = "TRUE" if (mf >= 6 and mr < 1.0) else "FALSE"
            out.append([sid, dttxt, tf, direction, sess, wick, fresh, bk, round(bval, 4),
                        bp, mf, round(mr, 3), ex, sh, bucket(mr), bh])
    with open(f"sim_{tf}_2020-01-01_2026-06-16.csv", "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.writer(fp); w.writerow(HEADER); w.writerows(out)
    combined += out
    print(f"[{tf}] {len(out)}행")
with open("sim_all_tf_2020-01-01_2026-06-16.csv", "w", newline="", encoding="utf-8-sig") as fp:
    w = csv.writer(fp); w.writerow(HEADER); w.writerows(combined)
print(f"[all] {len(combined)}행 -> sim_all_tf_2020-01-01_2026-06-16.csv")
