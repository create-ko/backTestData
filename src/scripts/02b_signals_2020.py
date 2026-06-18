#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02b_signals_2020.py
===================
02_signals.py 와 로직 동일. 입력/출력만 신규 2020~2026 데이터셋으로 교체한 버전.
(원본 02_signals.py 및 기존 signals_*.csv 는 그대로 보존)

입력 : xauusd_{2m|5m|10m}_2020-01-01_2026-06-16.csv   (Dukascopy MID, 1m도 동봉)
출력 : signals_{2m|5m|10m}_2020-01-01_2026-06-16.csv , signals_all_tf_2020-01-01_2026-06-16.csv
"""
import csv, math, datetime
from datetime import timezone, timedelta

KST = timezone(timedelta(hours=9))

def pine_dow(d):
    return (d.isoweekday() % 7) + 1

def is_us_dst(dt):
    m, d = dt.month, dt.day
    wd = pine_dow(dt.date())
    # DST 시작=3월 둘째 일요일(>=7), 종료=11월 첫째 일요일(<0). 2020/2026 경계 보정.
    return (3 < m < 11) or (m == 3 and (d - wd >= 7)) or (m == 11 and (d - wd < 0))

def is_euro_dst(dt):
    m, d, y = dt.month, dt.day, dt.year
    lsM = 31 - (pine_dow(datetime.date(y, 3, 31)) - 1)
    lsO = 31 - (pine_dow(datetime.date(y, 10, 31)) - 1)
    return (3 < m < 10) or (m == 3 and d >= lsM) or (m == 10 and d < lsO)

def process(tf, infile, multiplier):
    data = []
    with open(infile, encoding="utf-8-sig") as fp:
        rd = csv.reader(fp); next(rd)
        for r in rd:
            data.append((float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    n = len(data); closes = [d[4] for d in data]; opens = [d[1] for d in data]

    def boll(src, length, mult):
        up = [None]*n; lo = [None]*n; s = ss = 0.0
        for i in range(n):
            v = src[i]; s += v; ss += v*v
            if i >= length:
                rm = src[i-length]; s -= rm; ss -= rm*rm
            if i >= length-1:
                mean = s/length; var = ss/length - mean*mean
                if var < 0: var = 0.0
                dev = mult*math.sqrt(var); up[i] = mean+dev; lo[i] = mean-dev
        return up, lo

    upper1, lower1 = boll(closes, 20, 2.0)
    upper2, lower2 = boll(opens, 4, 4.0)
    usStartM = 0 if multiplier >= 60 else 30
    asiaKtr = euroKtr = usKtr = None; prevHour = None
    out = []; sid = 0; prev_bull = prev_bear = False
    for i in range(n):
        t, o, h, l, c = data[i]
        dt = datetime.datetime.fromtimestamp(t, KST); nowH = dt.hour; nowM = dt.minute
        uDst = is_us_dst(dt); eDst = is_euro_dst(dt)
        asiaStartH = 7 if uDst else 8
        euroStartH = 16 if eDst else 17
        usStartH   = 22 if uDst else 23
        isNewHour = (prevHour is not None and nowH != prevHour)
        if nowH == asiaStartH and isNewHour:
            ph = data[i-1][2] if i > 0 else h; pl = data[i-1][3] if i > 0 else l
            asiaKtr = max(h, ph) - min(l, pl)
        if nowH == euroStartH and isNewHour: euroKtr = h - l
        if nowH == usStartH and nowM == usStartM: usKtr = h - l
        # 미장 시작 = usStartH:usStartM (실제 뉴욕 개장, 2/5/10분TF는 :30). 그 전 30분은 유로(개장 전).
        if   asiaStartH <= nowH < euroStartH: sess = "아시아"; aktr = asiaKtr
        elif euroStartH <= nowH < usStartH or (nowH == usStartH and nowM < usStartM):
            sess = "유로"; aktr = euroKtr
        else:                                 sess = "미장";   aktr = usKtr
        prevHour = nowH
        rng = h - l
        bull = c > o and upper1[i] is not None and c > upper1[i] and upper2[i] is not None and c > upper2[i]
        bear = c < o and lower1[i] is not None and c < lower1[i] and lower2[i] is not None and c < lower2[i]
        if bull or bear:
            sid += 1; direction = "LONG" if bull else "SHORT"
            wick = ((h-c) if bull else (c-l))/rng if rng > 0 else 1.0
            fresh = (bull and not prev_bull) or (bear and not prev_bear)
            out.append([f"{tf}-{sid:06d}", dt.strftime("%Y-%m-%d %H:%M"), int(t), tf,
                        direction, sess, round(wick, 4), c,
                        round(aktr, 4) if aktr is not None else "", round(rng, 4),
                        "TRUE" if fresh else "FALSE", o, h, l, c])
        prev_bull = bull; prev_bear = bear
    return out

HEADER = ["signal_id", "datetime_kst", "time_epoch", "TF", "방향", "세션", "꼬리비율",
          "돌파가", "KTR", "돌파캔들크기", "fresh", "open", "high", "low", "close"]

combined = []
for tf, f, mult in [("2m",  "xauusd_2m_2020-01-01_2026-06-16.csv",  2),
                    ("5m",  "xauusd_5m_2020-01-01_2026-06-16.csv",  5),
                    ("10m", "xauusd_10m_2020-01-01_2026-06-16.csv", 10)]:
    out = process(tf, f, mult)
    kept = [r for r in out if r[8] != ""]
    for i, r in enumerate(kept, 1):
        r[0] = f"{tf}-{i:06d}"
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv", "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.writer(fp); w.writerow(HEADER); w.writerows(kept)
    combined += kept
    print(f"[{tf}] 돌파봉 {len(out)} -> KTR유효 {len(kept)} (제외 {len(out)-len(kept)})")
with open("signals_all_tf_2020-01-01_2026-06-16.csv", "w", newline="", encoding="utf-8-sig") as fp:
    w = csv.writer(fp); w.writerow(HEADER); w.writerows(combined)
print(f"[all] {len(combined)}건 -> signals_all_tf_2020-01-01_2026-06-16.csv")
