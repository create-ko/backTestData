# -*- coding: utf-8 -*-
"""41 — 하루 거래수 분포 + 무거래일 + 최장 무거래 연속, 꼬리필터별. 10m v1/v2, 순차+시간(08~24).
꼬리비율(s[6]) <= thr 만 진입. 꼬리필터가 빈도뿐 아니라 net R(품질)에 도움 되는지도 확인."""
import csv, math, time
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0
SUM_L=sum(L); STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))
SPREAD=0.30; RISK=0.02; YRS=6.46; START_H=8
WICKS=[1.0,0.3,0.2,0.1]  # 1.0=필터없음

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
def khour(e,off):
    e=e//1000 if e>1e11 else e; return ((e//3600)+off)%24
def kdate(e,off):
    e=e//1000 if e>1e11 else e; return time.strftime("%Y-%m-%d",time.gmtime(e+off*3600))
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
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(si,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr=TP if fc<6 else B6X
        tp=deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return i,maxF,"STOP"
            if h>=tp: return i,maxF,("B6" if fc==6 else "TPs")
        else:
            if fc>=6 and h>=stop: return i,maxF,"STOP"
            if l<=tp: return i,maxF,("B6" if fc==6 else "TPs")
    return n-1,maxF,"OPEN"
def pnl_tps(k): exitlv=MULT[k-1]-TP; return sum(L[i]*(MULT[i]-exitlv) for i in range(k))
def pnl_b6():   exitlv=MULT[5]-B6X; return sum(L[i]*(MULT[i]-exitlv) for i in range(6))
def pnl_stop(): return sum(L[i]*(MULT[i]-STOPM) for i in range(6))
def trade_R(maxF,kind):
    if kind=="STOP": return pnl_stop()/STOP_R, SUM_L
    if kind=="B6":   return pnl_b6()/STOP_R, SUM_L
    return pnl_tps(maxF)/STOP_R, sum(L[:maxF])
def seq_v1(tf,bars,idx,off,wthr):
    sigs=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k<=0: continue
            if float(s[6])>wthr: continue
            sigs.append((bi,float(s[7]),s[4],k))
    sigs.sort(key=lambda x:x[0]); out=[]; busy=-1
    for bi,a,d,k in sigs:
        if bi<=busy: continue
        eb=bi+1
        if khour(bars[eb][0],off)<START_H: continue
        ex,mf,kind=sim(bars,eb,a,d,k)
        if kind in ("TPs","B6","STOP"): out.append((eb,mf,kind,k)); busy=ex
    return out
def seq_v2(tf,bars,idx,off,wthr):
    u2,l2=boll([b[1] for b in bars],4,4.0); brk={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None and float(s[6])<=wthr: brk[bi]=s
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
                            ex,mf,kind=sim(bars,eb,bars[eb][1],pdir,k)
                            if kind in ("TPs","B6","STOP"): out.append((eb,mf,kind,k)); busy=ex
                        pending=None
    return out
def maxdd(eq):
    peak=eq[0]; m=0.0
    for v in eq:
        if v>peak: peak=v
        d=(peak-v)/peak
        if d>m: m=d
    return 100*m

for tf in ["10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); off=calib(tf)
    # 시장일(데이터에 바가 있는 KST 날짜) 정렬 리스트
    mdays=sorted(set(kdate(b[0],off) for b in bars))
    nday=len(mdays); dpos={d:i for i,d in enumerate(mdays)}
    for ver,fn in [("v1",seq_v1),("v2",seq_v2)]:
        print(f"\n{'='*82}\n### {tf} {ver}  (시장일 {nday}일, ~{nday/YRS:.0f}일/년)")
        print(f"{'꼬리':>6}{'거래수':>7}{'netR':>8}{'CAGR':>8}{'MDD':>7} | {'거래/년':>7}{'무거래일%':>9}{'1건일%':>7}{'2+일%':>7}{'최장무거래(연속거래일)':>20}")
        for w in WICKS:
            tr=fn(tf,bars,idx,off,w)
            netR=[]; dates=[]
            for eb,mf,kind,k in tr:
                gR,lots=trade_R(mf,kind); netR.append(gR-lots*(SPREAD/k)/STOP_R); dates.append(kdate(bars[eb][0],off))
            n=len(tr)
            eq=[1.0]
            for r in netR: eq.append(eq[-1]*(1+RISK*r))
            cagr=100*(eq[-1]**(1/YRS)-1) if eq[-1]>0 else -100; mdd=maxdd(eq); totR=sum(netR)
            # 일별 카운트
            cnt={}
            for d in dates: cnt[d]=cnt.get(d,0)+1
            d0=sum(1 for d in mdays if d not in cnt)
            d1=sum(1 for d in mdays if cnt.get(d,0)==1)
            d2=sum(1 for d in mdays if cnt.get(d,0)>=2)
            # 최장 무거래 연속(시장일 기준)
            streak=0; mx=0
            for d in mdays:
                if cnt.get(d,0)==0: streak+=1; mx=max(mx,streak)
                else: streak=0
            wlab="없음" if w==1.0 else f"<={w}"
            print(f"{wlab:>6}{n:>7}{totR:>+8.1f}{cagr:>+7.1f}%{mdd:>6.1f}% | {n/YRS:>7.0f}{100*d0/nday:>8.1f}%{100*d1/nday:>6.1f}%{100*d2/nday:>6.1f}%{mx:>15}일")
