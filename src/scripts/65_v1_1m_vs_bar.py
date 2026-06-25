# -*- coding: utf-8 -*-
"""65 - v1 고정TP를 (A)봉-OHLC vs (B)1분봉 해소로 나란히 돌려 look-ahead 차이 측정.
같은 전략(그리드 0/-1/-2/-3/-4/-4.5 KTR, 등량 랏, TP=깊은체결+1.5KTR, 6차서만 -5 손절),
같은 진입(돌파봉 종가=bp, base=KTR). 차이는 '해소 경로'뿐:
  A = 03c와 동일: 한 봉 안에서 저가로 그리드 채우고 같은 봉 고가로 TP 판정(같은봉 미래참조).
  B = 1분봉을 시간순으로 밟아 체결/TP/손절 판정(미래참조 제거).
둘 다 30일 캔들 캡, OPEN(미청산)은 승률/기대값서 제외(공정). 슬리피지 없음(버그만 분리).
data/에서 실행. 콘솔 ASCII만(규칙3)."""
import csv, math, bisect

MULT=[0,1,2,3,4,4.5]; TP=1.5; CAPD=30*86400

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx

def pnl_R(E,filledk,reason,bp,base,d):
    """등량 랏 R(=base단위). filledk=가장깊은 체결 인덱스."""
    deepest=E[filledk]
    if reason=="TP":  ex=deepest+TP*base if d=="LONG" else deepest-TP*base
    else:             ex=bp-5*base if d=="LONG" else bp+5*base   # STOP
    s=0.0
    for i in range(filledk+1):
        s+=(ex-E[i])/base if d=="LONG" else (E[i]-ex)/base
    return s

# ---- A: 봉-OHLC (03c와 동일 로직) ----
def simA(bars,si,d,bp,base):
    E=[bp-base*m if d=="LONG" else bp+base*m for m in MULT]
    filled=[False]*6; filled[0]=True; maxk=0; fc=1
    t0=bars[si][0]
    for i in range(si+1,len(bars)):
        t,o,h,l,c=bars[i]
        if t-t0>CAPD: return "OPEN",maxk
        for k in range(1,6):
            if not filled[k] and ((d=="LONG" and l<=E[k]) or (d=="SHORT" and h>=E[k])): filled[k]=True
        nfc=sum(filled)
        if nfc!=fc: fc=nfc; maxk=max(k for k in range(6) if filled[k])
        deepest=E[maxk]; tp=deepest+TP*base if d=="LONG" else deepest-TP*base
        stop=bp-5*base if d=="LONG" else bp+5*base
        if d=="LONG":
            if fc>=6 and l<=stop: return "STOP",maxk
            if h>=tp: return "TP",maxk
        else:
            if fc>=6 and h>=stop: return "STOP",maxk
            if l<=tp: return "TP",maxk
    return "OPEN",maxk

# ---- B: 1분봉 시간순 ----
def simB(T1,H1,L1,j0,d,bp,base):
    E=[bp-base*m if d=="LONG" else bp+base*m for m in MULT]
    filled=[False]*6; filled[0]=True; maxk=0; fc=1
    t0=T1[j0]
    for m in range(j0,len(T1)):
        if T1[m]-t0>CAPD: return "OPEN",maxk
        h=H1[m]; l=L1[m]
        for k in range(1,6):
            if not filled[k] and ((d=="LONG" and l<=E[k]) or (d=="SHORT" and h>=E[k])): filled[k]=True
        nfc=sum(filled)
        if nfc!=fc: fc=nfc; maxk=max(k for k in range(6) if filled[k])
        deepest=E[maxk]; tp=deepest+TP*base if d=="LONG" else deepest-TP*base
        stop=bp-5*base if d=="LONG" else bp+5*base
        if d=="LONG":
            if fc>=6 and l<=stop: return "STOP",maxk
            if h>=tp: return "TP",maxk
        else:
            if fc>=6 and h>=stop: return "STOP",maxk
            if l<=tp: return "TP",maxk
    return "OPEN",maxk

print("1분봉 로딩...")
T1=[]; H1=[]; L1=[]
with open("xauusd_1m_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
    rd=csv.reader(fp); next(rd)
    for r in rd:
        T1.append(int(float(r[0]))); H1.append(float(r[2])); L1.append(float(r[3]))
print(f"1m {len(T1)}봉\n")
def i1(e): return bisect.bisect_left(T1,e)

print("# v1 고정TP1.5 등량 | (A)봉-OHLC vs (B)1분봉 해소 | 30일캡 | 슬립0 | 청산건만 집계")
print(f"{'TF':>4} {'method':>7} {'청산':>6} {'승률':>7} {'기대R':>8} {'손절률':>7}")
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); tfsec=int(tf[:-1])*60
    sigs=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            ep=int(s[2]); si=idx.get(ep)
            if si is None: continue
            ktr=float(s[8]) if s[8] else 0.0
            if ktr<=0: continue
            sigs.append((si,ep,s[4],float(s[7]),ktr))
    for method,fn in [("A-bar",None),("B-1m",None)]:
        Rs=[]; stop=0
        for si,ep,d,bp,ktr in sigs:
            E=[bp-ktr*m if d=="LONG" else bp+ktr*m for m in MULT]
            if method=="A-bar":
                reason,maxk=simA(bars,si,d,bp,ktr)
            else:
                j0=i1(ep+tfsec)
                reason,maxk=simB(T1,H1,L1,j0,d,bp,ktr)
            if reason=="OPEN": continue
            Rs.append(pnl_R(E,maxk,reason,bp,ktr,d))
            if reason=="STOP": stop+=1
        n=len(Rs); w=sum(1 for r in Rs if r>0)
        print(f"{tf:>4} {method:>7} {n:>6} {100*w/n if n else 0:>6.1f}% {sum(Rs)/n if n else 0:>+8.3f} {100*stop/n if n else 0:>6.1f}%")
    print()
