#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""02_signals.py 의 DST 로직을 그대로 떼어 2020~2026 전환일 검증."""
import datetime

def pine_dow(d): return (d.isoweekday() % 7) + 1

def is_us_dst(dt):
    m, d = dt.month, dt.day; wd = pine_dow(dt.date())
    return (3 < m < 11) or (m == 3 and (d - wd >= 7)) or (m == 11 and (d - wd < 0))

def is_euro_dst(dt):
    m, d, y = dt.month, dt.day, dt.year
    lsM = 31 - (pine_dow(datetime.date(y, 3, 31)) - 1)
    lsO = 31 - (pine_dow(datetime.date(y, 10, 31)) - 1)
    return (3 < m < 10) or (m == 3 and d >= lsM) or (m == 10 and d < lsO)

# 실제 달력 정답
US_TRUE = {2020:("03-08","11-01"),2021:("03-14","11-07"),2022:("03-13","11-06"),
           2023:("03-12","11-05"),2024:("03-10","11-03"),2025:("03-09","11-02"),2026:("03-08","11-01")}
EU_TRUE = {2020:("03-29","10-25"),2021:("03-28","10-31"),2022:("03-27","10-30"),
           2023:("03-26","10-29"),2024:("03-31","10-27"),2025:("03-30","10-26"),2026:("03-29","10-25")}

def transitions(fn, year):
    on = off = None; prev = False
    d = datetime.date(year, 1, 1)
    while d.year == year:
        cur = fn(datetime.datetime(d.year, d.month, d.day))
        if cur and not prev: on = d
        if not cur and prev: off = d            # 첫 비활성일
        prev = cur; d += datetime.timedelta(days=1)
    return on, off

print(f"{'연도':<6}{'US시작(계산/정답)':<26}{'US종료':<22}{'EU시작':<24}{'EU종료':<22}")
ok = True
for y in range(2020, 2027):
    uon, uoff = transitions(is_us_dst, y)
    eon, eoff = transitions(is_euro_dst, y)
    us_on_ok  = uon.strftime("%m-%d") == US_TRUE[y][0]
    us_off_ok = uoff.strftime("%m-%d") == US_TRUE[y][1]
    eu_on_ok  = eon.strftime("%m-%d") == EU_TRUE[y][0]
    eu_off_ok = eoff.strftime("%m-%d") == EU_TRUE[y][1]
    ok = ok and us_on_ok and us_off_ok and eu_on_ok and eu_off_ok
    m = lambda v,t: ("OK" if v else "✗")
    print(f"{y:<6}{uon.strftime('%m-%d')}/{US_TRUE[y][0]} {m(us_on_ok,0):<3}"
          f"  {uoff.strftime('%m-%d')}/{US_TRUE[y][1]} {m(us_off_ok,0):<3}"
          f"  {eon.strftime('%m-%d')}/{EU_TRUE[y][0]} {m(eu_on_ok,0):<3}"
          f"  {eoff.strftime('%m-%d')}/{EU_TRUE[y][1]} {m(eu_off_ok,0):<3}")
print("\n결과:", "전부 일치 ✅" if ok else "불일치 발견 ✗")
