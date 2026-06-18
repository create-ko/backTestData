# -*- coding: utf-8 -*-
"""43 — 데이터 공백 점검. 각 분봉에서 연속 바 사이 최대 시간격차 top, 정상 주말갭(~2일) 초과분."""
import csv, time
def es(e): return e//1000 if e>1e11 else e
for tf in ["2m","5m","10m"]:
    ts=[]
    with open(f"xauusd_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd: ts.append(es(int(float(r[0]))))
    gaps=[]
    for i in range(1,len(ts)):
        d=ts[i]-ts[i-1]
        if d>3*86400:  # 3일 초과만
            gaps.append((d/86400.0, ts[i-1], ts[i]))
    gaps.sort(reverse=True)
    print(f"\n=== {tf}  (바 {len(ts)}개, 3일 초과 갭 {len(gaps)}개) ===")
    for d,a,b in gaps[:8]:
        print(f"  {d:6.1f}일 공백: {time.strftime('%Y-%m-%d %H:%M',time.gmtime(a+9*3600))} -> {time.strftime('%Y-%m-%d %H:%M',time.gmtime(b+9*3600))} (KST)")
