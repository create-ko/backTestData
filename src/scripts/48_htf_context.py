# -*- coding: utf-8 -*-
"""48 — 실패 거래의 상위TF(1h·2h) 추세 정렬 정량화. 실패가 상위추세와 역행이었나?
추세: 해당TF 종가 vs SMA20. align = (LONG & 종가>SMA) or (SHORT & 종가<SMA). counter=역행.
실패의 counter% 를 전체 거래의 counter% 와 비교 → 추세필터 효용 가늠."""
import csv, math
MULT=[0,1,2,3,4,4.5]; STOPM=5.0; TP=1.5; B6X=1.0; START_H=8
def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); t=t//1000 if t>1e11 else t
            idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
def resample(b10,p):
    out=[]; cur=None
    for t,o,h,l,c in b10:
        g=(t//p)*p
        if cur is None or cur[0]!=g:
            if cur: out.append(tuple(cur))
            cur=[g,o,h,l,c]
        else: cur[2]=max(cur[2],h);cur[3]=min(cur[3],l);cur[4]=c
    if cur: out.append(tuple(cur))
    return out
def sma(bars,n,si):
    out=[None]*len(bars); s=0.0
    for i in range(len(bars)):
        s+=bars[i][si]
        if i>=n: s-=bars[i-n][si]
        if i>=n-1: out[i]=s/n
    return out
def calib(tf):
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def khour(e,off): return ((e//3600)+off)%24
def nidx(bars,ep):
    lo,hi=0,len(bars)-1
    while lo<hi:
        m=(lo+hi)//2
        if bars[m][0]<ep: lo=m+1
        else: hi=m
    return lo
def sim(bars, eb, a, d, base):
    n=len(bars)
    if d=="LONG": E=[a-base*MULT[i] for i in range(6)]; stop=a-base*STOPM
    else:         E=[a+base*MULT[i] for i in range(6)]; stop=a+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1
    for i in range(eb,n):
        t,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((d=="LONG" and l<=E[k]) or (d=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr=TP if fc<6 else B6X
        tp=deepest+thr*base if d=="LONG" else deepest-thr*base
        if d=="LONG":
            if fc>=6 and l<=stop: return i,"STOP"
            if h>=tp: return i,"WIN"
        else:
            if fc>=6 and h>=stop: return i,"STOP"
            if l<=tp: return i,"WIN"
    return n-1,"OPEN"

b10,i10=load("xauusd_10m_2020-01-01_2026-06-16.csv")
b1h=resample(b10,3600); b2h=resample(b10,7200)
sma1h=sma(b1h,20,4); sma2h=sma(b2h,20,4)
off=calib("10m")
sigs=[]
with open("signals_10m_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
    rd=csv.reader(fp); next(rd)
    for s in rd:
        bi=i10.get(int(s[2]))
        if bi is None or bi+1>=len(b10): continue
        k=float(s[8])
        if k>0: sigs.append((bi,float(s[7]),s[4],k,s[1]))
sigs.sort(key=lambda x:x[0])
def trend_align(ep,d):
    """1h, 2h 정렬 여부 (True=추세동행, False=역행, None=데이터부족)"""
    res=[]
    for bars,smaa in [(b1h,sma1h),(b2h,sma2h)]:
        j=nidx(bars,ep)
        if j>=len(bars) or smaa[j] is None: res.append(None); continue
        up=bars[j][4]>smaa[j]
        res.append((d=="LONG" and up) or (d=="SHORT" and not up))
    return res  # [1h_align, 2h_align]

busy=-1; allt=[]; fails=[]
for bi,a,d,k,dt in sigs:
    if bi<=busy: continue
    eb=bi+1
    if khour(b10[eb][0],off)<START_H: continue
    exi,kind=sim(b10,eb,a,d,k); busy=exi
    if dt[:4] not in ("2025","2026"): continue
    al=trend_align(b10[eb][0],d)
    rec={"d":d,"kind":kind,"a1":al[0],"a2":al[1]}
    allt.append(rec)
    if kind=="STOP": fails.append(rec)

def pct_counter(rows,key):
    valid=[r for r in rows if r[key] is not None]
    if not valid: return 0,0
    cnt=sum(1 for r in valid if not r[key])  # counter = not align
    return 100*cnt/len(valid), len(valid)

print(f"=== 10m v1  25·26  전체 {len(allt)}건 / 풀스톱 {len(fails)}건 ===\n")
for key,lab in [("a1","1시간봉"),("a2","2시간봉")]:
    fa,fn=pct_counter(fails,key); aa,an=pct_counter(allt,key)
    print(f" [{lab} 추세] 역행(counter) 비율")
    print(f"   풀스톱 거래: {fa:.1f}%  (n={fn})")
    print(f"   전체 거래 : {aa:.1f}%  (n={an})")
    print(f"   → 실패가 역행에 {'몰림' if fa>aa+8 else '비슷'} (차이 {fa-aa:+.1f}%p)\n")
# 방향+추세 교차표 (2h)
print(" [2시간봉 기준] 방향×결과")
for d in ["LONG","SHORT"]:
    sub=[r for r in allt if r["d"]==d and r["a2"] is not None]
    with_t=[r for r in sub if r["a2"]]; cnt_t=[r for r in sub if not r["a2"]]
    def stoprate(rows):
        return (100*sum(1 for r in rows if r["kind"]=="STOP")/len(rows)) if rows else 0
    print(f"   {d}: 동행 {len(with_t)}건(풀스톱 {stoprate(with_t):.1f}%) / 역행 {len(cnt_t)}건(풀스톱 {stoprate(cnt_t):.1f}%)")
