#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
생성된 신호 데이터에서 세션 경계가 DST에 따라 실제로 이동하는지 검증.
세션 시작(KST): 아시아 7/8(US-DST), 유로 16/17(EU-DST), 미장 22/23(US-DST)
"""
import csv, datetime
from datetime import timezone, timedelta
from collections import defaultdict

KST = timezone(timedelta(hours=9))
def pine_dow(d): return (d.isoweekday() % 7) + 1
def is_us_dst(dt):
    m, d = dt.month, dt.day; wd = pine_dow(dt.date())
    return (3 < m < 11) or (m == 3 and (d - wd >= 7)) or (m == 11 and (d - wd < 0))
def is_euro_dst(dt):
    m, d, y = dt.month, dt.day, dt.year
    lsM = 31 - (pine_dow(datetime.date(y, 3, 31)) - 1); lsO = 31 - (pine_dow(datetime.date(y, 10, 31)) - 1)
    return (3 < m < 10) or (m == 3 and d >= lsM) or (m == 10 and d < lsO)

rows = list(csv.DictReader(open("signals_all_tf_2010-01-01_2026-06-16.csv", encoding="utf-8-sig")))

# 세션별 × DST상태별 KST 시작시각(min hour) 관측
# 아시아/미장은 US-DST, 유로는 EU-DST 기준으로 분리
obs = defaultdict(set)          # (session, dst_label) -> set(hours)
mismatch = 0
for r in rows:
    dt = datetime.datetime.fromtimestamp(int(r["time_epoch"]), KST)
    h = dt.hour; mn = dt.minute; usM = 30   # 2/5/10분 TF: 미장 :30 개장
    uD, eD = is_us_dst(dt), is_euro_dst(dt)
    aH = 7 if uD else 8; eH = 16 if eD else 17; uH = 22 if uD else 23
    if aH <= h < eH: exp = "아시아"
    elif (eH <= h < uH) or (h == uH and mn < usM): exp = "유로"
    else: exp = "미장"
    if exp != r["세션"]: mismatch += 1
    if r["세션"] == "아시아": obs[("아시아", "US-DST" if uD else "US-STD")].add(h)
    elif r["세션"] == "유로":  obs[("유로",  "EU-DST" if eD else "EU-STD")].add(h)
    else:                      obs[("미장",  "US-DST" if uD else "US-STD")].add(h)

print(f"총 신호 {len(rows)}건")
print(f"세션 라벨 ↔ DST기반 재계산 불일치: {mismatch}건  {'✅ 완전 일치' if mismatch==0 else '✗'}\n")
print("세션별 실제 관측 KST 시작시각 (min) / 기대값:")
EXP = {("아시아","US-DST"):7,("아시아","US-STD"):8,("유로","EU-DST"):16,
       ("유로","EU-STD"):17,("미장","US-DST"):22,("미장","US-STD"):23}
for key in [("아시아","US-DST"),("아시아","US-STD"),("유로","EU-DST"),("유로","EU-STD"),("미장","US-DST"),("미장","US-STD")]:
    hrs = obs.get(key)
    if not hrs: continue
    # 미장은 자정 넘김 → 저녁 시작시각(오후 시간대 min)으로 판정
    start = min(h for h in hrs if h >= 12) if key[0] == "미장" else min(hrs)
    ok = "✅" if start == EXP[key] else "✗"
    print(f"   {key[0]:<4} {key[1]}: 저녁시작 {start}시 (기대 {EXP[key]}시) {ok}   관측 {sorted(hrs)}")
