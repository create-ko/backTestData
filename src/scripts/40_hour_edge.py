# -*- coding: utf-8 -*-
"""40 — 시간대(KST 시)별 진입 분포·엣지. 순차+시간(08~24) 확정설정에서 실제 잡힌 거래를 진입 시각별로 집계.
'어느 시간에 거래가 몰리고 어디가 net R이 좋은가' → 거래 가능 시간 선택 근거. 10m v1/v2."""
import csv, math
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0
SUM_L=sum(L); STOP_R=abs(sum(L[i]*(MULT[i]-STOPM) for i in range(6)))
SPREAD=0.30; START_H=8

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
def calib(tf):
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd); s=next(rd)
    ts=int(s[2]); ts=ts//1000 if ts>1e11 else ts
    return (int(s[1][11:13])-(ts//3600)%24)%24
def khour(e,off):
    e=e//1000 if e>1e11 else e; return ((e//3600)+off)%24
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
def seq_v1(tf,bars,idx,off):
    sigs=[]
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: sigs.append((bi,float(s[7]),s[4],k))
    sigs.sort(key=lambda x:x[0]); out=[]; busy=-1
    for bi,a,d,k in sigs:
        if bi<=busy: continue
        eb=bi+1; hh=khour(bars[eb][0],off)
        if hh<START_H: continue
        ex,mf,kind=sim(bars,eb,a,d,k)
        if kind in ("TPs","B6","STOP"): out.append((hh,mf,kind,k)); busy=ex
    return out
def seq_v2(tf,bars,idx,off):
    u2,l2=boll([b[1] for b in bars],4,4.0); brk={}
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
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
                    k=float(ps[8]); hh=khour(bars[eb][0],off)
                    if k>0:
                        if hh>=START_H:
                            ex,mf,kind=sim(bars,eb,bars[eb][1],pdir,k)
                            if kind in ("TPs","B6","STOP"): out.append((hh,mf,kind,k)); busy=ex
                        pending=None
    return out

for tf in ["10m"]:
    bars,idx=load(f"xauusd_{tf}_2020-01-01_2026-06-16.csv"); off=calib(tf)
    for ver,fn in [("v1",seq_v1),("v2",seq_v2)]:
        tr=fn(tf,bars,idx,off)
        hc={h:0 for h in range(8,24)}; hr={h:0.0 for h in range(8,24)}
        for hh,mf,kind,k in tr:
            gR,lots=trade_R(mf,kind); nR=gR-lots*(SPREAD/k)/STOP_R
            hc[hh]+=1; hr[hh]+=nR
        tot=len(tr); totR=sum(hr.values())
        print(f"\n{'='*70}\n=== {tf} {ver}  (총 {tot}건, net {totR:+.1f}R) ===")
        print(f"{'KST시':>6}{'건수':>7}{'비중%':>7}{'netR합':>9}{'평균netR':>10}{'R비중%':>8}")
        for h in range(8,24):
            print(f"{h:>4}시{hc[h]:>7}{100*hc[h]/tot:>6.1f}%{hr[h]:>+9.1f}{(hr[h]/hc[h] if hc[h] else 0):>+10.4f}{100*hr[h]/totR if totR else 0:>7.1f}%")
        # 세션 구간 합산
        def seg(a,b):
            c=sum(hc[h] for h in range(a,b)); r=sum(hr[h] for h in range(a,b))
            return c,r
        print("  --- 구간 ---")
        for nm,a,b in [("아시아 08-16",8,16),("런던 16-22",16,22),("미장초 22-24",22,24)]:
            c,r=seg(a,b)
            print(f"  {nm:<12} {c:>5}건 ({100*c/tot:>4.1f}%)  net {r:>+7.1f}R ({100*r/totR if totR else 0:>5.1f}%)  평균 {(r/c if c else 0):>+.4f}")
