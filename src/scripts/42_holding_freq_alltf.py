# -*- coding: utf-8 -*-
"""42 — 보유시간 분포 + 무거래 빈도 + 정체(stuck) 확인. 2m·5m·10m 전부 × v1/v2.
순차+시간(08~24)·꼬리필터없음. 37일 무거래연속이 '한 포지션 장기보유'인지 확인.
보유시간은 epoch차(실시간, 주말갭 반영). 최장보유 vs 최장무거래연속 비교."""
import csv, math, time, json
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0; START_H=8
def data_span_years(bars):
    e0=bars[0][0]; e1=bars[-1][0]
    if e1>1e11: e0/=1000; e1/=1000
    return (e1-e0)/(365.25*86400)

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
def calib(tf):
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def es(e): return e//1000 if e>1e11 else e
def khour(e,off): return ((es(e)//3600)+off)%24
def kdate(e,off): return time.strftime("%Y-%m-%d",time.gmtime(es(e)+off*3600))
def boll(src,length,m):
    n=len(src); up=[None]*n; lo=[None]*n; s=ss=0.0
    for i in range(n):
        v=src[i]; s+=v; ss+=v*v
        if i>=length: rm=src[i-length]; s-=rm; ss-=rm*rm
        if i>=length-1:
            mean=s/length; var=ss/length-mean*mean
            if var<0: var=0.0
            d=m*math.sqrt(var); up[i]=mean+d; lo[i]=mean-d
    return up,lo
def sim(bars, si, anchor, direction, base):
    n=len(bars)
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(6)]; stop=anchor-base*STOPM
    else:                 E=[anchor+base*MULT[i] for i in range(6)]; stop=anchor+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1
    for i in range(si,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr=TP if fc<6 else B6X
        tp=deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return i,"STOP"
            if h>=tp: return i,"TP"
        else:
            if fc>=6 and h>=stop: return i,"STOP"
            if l<=tp: return i,"TP"
    return n-1,"OPEN"
def seq_v1(tf,bars,idx,off):
    sigs=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: sigs.append((bi,float(s[7]),s[4],k))
    sigs.sort(key=lambda x:x[0]); out=[]; busy=-1
    for bi,a,d,k in sigs:
        if bi<=busy: continue
        eb=bi+1
        if khour(bars[eb][0],off)<START_H: continue
        ex,kind=sim(bars,eb,a,d,k)
        if kind in ("TP","STOP"): out.append((eb,ex)); busy=ex
    return out
def seq_v2(tf,bars,idx,off):
    u2,l2=boll([b[1] for b in bars],4,4.0); brk={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    out=[]; pending=None; busy=-1
    for i in range(len(bars)):
        if i<=busy: pending=None; continue
        if i in brk: pending=(i,brk[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                eb=i+1
                if eb<len(bars):
                    k=float(ps[8])
                    if k>0:
                        if khour(bars[eb][0],off)>=START_H:
                            ex,kind=sim(bars,eb,bars[eb][1],pdir,k)
                            if kind in ("TP","STOP"): out.append((eb,ex)); busy=ex
                        pending=None
    return out

HOLD={}
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); off=calib(tf)
    YRS=data_span_years(bars)
    HOLD[tf]={}
    mdays=sorted(set(kdate(b[0],off) for b in bars)); nday=len(mdays)
    print(f"\n{'='*84}\n### {tf}  (시장일 {nday}, ~{nday/YRS:.0f}/년)")
    print(f"{'버전':>4}{'거래':>6}{'보유중앙h':>10}{'보유평균h':>10}{'95%h':>8}{'최대보유':>10}{'무거래일%':>9}{'최장무거래':>11}")
    for ver,fn in [("v1",seq_v1),("v2",seq_v2)]:
        tr=fn(tf,bars,idx,off)
        durs=[]   # 보유시간(시간)
        for eb,ex in tr:
            durs.append((es(bars[ex][0])-es(bars[eb][0]))/3600.0)
        durs_s=sorted(durs); n=len(durs)
        med=durs_s[n//2]; avg=sum(durs)/n; p95=durs_s[int(n*0.95)]; mx=durs_s[-1]
        # 무거래일 / 최장 무거래 연속
        dt=set(kdate(bars[eb][0],off) for eb,ex in tr)
        d0=sum(1 for d in mdays if d not in dt)
        streak=0; mxstreak=0
        for d in mdays:
            if d not in dt: streak+=1; mxstreak=max(mxstreak,streak)
            else: streak=0
        mxd=mx/24.0
        print(f"{ver:>4}{n:>6}{med:>9.1f}h{avg:>9.1f}h{p95:>7.1f}h{mxd:>8.1f}일{100*d0/nday:>8.1f}%{mxstreak:>9}일")
        HOLD[tf][ver]=[round(med,1),round(avg,1),round(p95,1),round(mxd,1)]
with open("holding_times.json","w",encoding="utf-8") as f: json.dump(HOLD,f,ensure_ascii=False)
print("\n→ holding_times.json")
