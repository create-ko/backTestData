# -*- coding: utf-8 -*-
"""06-15 09:00~11:30 10m 봉의 BB 돌파 조건 재계산 (왜 10:30 신호 없는지)."""
import csv, math, datetime
from datetime import timezone, timedelta
KST = timezone(timedelta(hours=9))

data = []
with open("xauusd_10m_2010-01-01_2026-06-16.csv", encoding="utf-8-sig") as fp:
    rd = csv.reader(fp); next(rd)
    for r in rd:
        data.append((float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])))
n = len(data); closes=[d[4] for d in data]; opens=[d[1] for d in data]

def boll(src, length, mult):
    up=[None]*n; lo=[None]*n; s=ss=0.0
    for i in range(n):
        v=src[i]; s+=v; ss+=v*v
        if i>=length: rm=src[i-length]; s-=rm; ss-=rm*rm
        if i>=length-1:
            mean=s/length; var=ss/length-mean*mean
            if var<0: var=0.0
            dev=mult*math.sqrt(var); up[i]=mean+dev; lo[i]=mean-dev
    return up, lo
u1,l1=boll(closes,20,2.0); u2,l2=boll(opens,4,4.0)

print("06-15 09:00~11:30 KST 10분봉 / BB 돌파 평가")
print(f"{'시각':<6}{'시가':>9}{'고가':>9}{'저가':>9}{'종가':>9}{'BB1상':>9}{'BB2상':>9}{'BB1하':>9}{'BB2하':>9}  판정")
for i in range(n):
    t,o,h,l,c=data[i]
    dt=datetime.datetime.fromtimestamp(t,KST)
    if dt.year==2026 and dt.month==6 and dt.day==15 and 9<=dt.hour<=11:
        bull = c>o and u1[i] is not None and c>u1[i] and u2[i] is not None and c>u2[i]
        bear = c<o and l1[i] is not None and c<l1[i] and l2[i] is not None and c<l2[i]
        tag = "LONG돌파" if bull else "SHORT돌파" if bear else ("양봉" if c>o else "음봉")
        # 돌파 실패 이유
        if not bull and not bear:
            reasons=[]
            if c>o:
                if not(u1[i] and c>u1[i]): reasons.append("종가<BB1상")
                if not(u2[i] and c>u2[i]): reasons.append("종가<BB2상")
            else:
                if not(l1[i] and c<l1[i]): reasons.append("종가>BB1하")
                if not(l2[i] and c<l2[i]): reasons.append("종가>BB2하")
            tag += " ("+",".join(reasons)+")" if reasons else ""
        f=lambda x: f"{x:.2f}" if x is not None else "-"
        print(f"{dt.strftime('%H:%M'):<6}{o:>9.2f}{h:>9.2f}{l:>9.2f}{c:>9.2f}{f(u1[i]):>9}{f(u2[i]):>9}{f(l1[i]):>9}{f(l2[i]):>9}  {tag}")
