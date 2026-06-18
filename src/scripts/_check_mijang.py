# -*- coding: utf-8 -*-
import csv, datetime
from datetime import timezone, timedelta
KST = timezone(timedelta(hours=9))
def pine_dow(d): return (d.isoweekday() % 7) + 1
def is_us_dst(dt):
    m, d = dt.month, dt.day; wd = pine_dow(dt.date())
    return (3 < m < 11) or (m == 3 and (d - wd >= 7)) or (m == 11 and (d - wd < 0))
rows = list(csv.DictReader(open("signals_all_tf_2020-01-01_2026-06-16.csv", encoding="utf-8-sig")))
early = 0; total = 0
for r in rows:
    dt = datetime.datetime.fromtimestamp(int(r["time_epoch"]), KST)
    if r["세션"] != "미장": continue
    total += 1
    usH = 22 if is_us_dst(dt) else 23
    if dt.hour == usH and dt.minute < 30:
        early += 1
print(f"미장 신호 총 {total}건")
print(f"그중 'usStart:00~:29'(실제 개장 30분 전) 구간: {early}건 ({100*early/total:.1f}%)")
print("→ 현재 이 구간은 라벨=미장 + 전일 US KTR(미갱신) 사용")
