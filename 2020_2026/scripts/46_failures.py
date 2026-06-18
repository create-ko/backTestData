# -*- coding: utf-8 -*-
"""46 — 25·26년 실패 거래 분석. 확정 실거래룰(순차+시간+후방+TP1.5+6차). v1·v2.
실패 = STOP(풀스톱 -24) + B6(6차반등 -4.5). 방향·세션·월·반등여부(MFE)로 '왜 실패했나' 규명.
신호: 종가가 BB1·BB2 동시 돌파, 꼬리 무시(현 신호 정의 그대로)."""
import csv, math, time
MULT=[0,1,2,3,4,4.5]; L=[1,1,2,2,3,4]; TP=1.5; B6X=1.0; STOPM=5.0; START_H=8

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
def es(e): return e//1000 if e>1e11 else e
def khour(e,off): return ((es(e)//3600)+off)%24
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
    """exit_i, maxF, kind, mfe_ktr, mae_ktr."""
    n=len(bars)
    if direction=="LONG": E=[anchor-base*MULT[i] for i in range(6)]; stop=anchor-base*STOPM
    else:                 E=[anchor+base*MULT[i] for i in range(6)]; stop=anchor+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1; mfe=0.0; mae=0.0
    for i in range(si,n):
        _,o,h,l,c=bars[i]
        if direction=="LONG":
            mfe=max(mfe,(h-anchor)/base); mae=max(mae,(anchor-l)/base)
        else:
            mfe=max(mfe,(anchor-l)/base); mae=max(mae,(h-anchor)/base)
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr=TP if fc<6 else B6X
        tp=deepest+thr*base if direction=="LONG" else deepest-thr*base
        if direction=="LONG":
            if fc>=6 and l<=stop: return i,maxF,"STOP",mfe,mae
            if h>=tp: return i,maxF,("B6" if fc==6 else "TP"),mfe,mae
        else:
            if fc>=6 and h>=stop: return i,maxF,"STOP",mfe,mae
            if l<=tp: return i,maxF,("B6" if fc==6 else "TP"),mfe,mae
    return n-1,maxF,"OPEN",mfe,mae
def seq_v1(tf,bars,idx,off):
    sigs=[]
    with open(f"signals_{tf}_2020-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: sigs.append((bi,float(s[7]),s[4],k,s[1],s[5]))
    sigs.sort(key=lambda x:x[0]); out=[]; busy=-1
    for bi,a,d,k,dt,sess in sigs:
        if bi<=busy: continue
        eb=bi+1
        if khour(bars[eb][0],off)<START_H: continue
        ex,mf,kind,mfe,mae=sim(bars,eb,a,d,k)
        if kind in ("TP","B6","STOP"): out.append((dt,d,sess,k,mf,kind,mfe,mae)); busy=ex
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
                    k=float(ps[8])
                    if k>0:
                        if khour(bars[eb][0],off)>=START_H:
                            ex,mf,kind,mfe,mae=sim(bars,eb,bars[eb][1],pdir,k)
                            if kind in ("TP","B6","STOP"): out.append((ps[1],pdir,ps[5],k,mf,kind,mfe,mae)); busy=ex
                        pending=None
    return out

for tf in ["10m"]:
    bars,idx=load(f"xauusd_{tf}_2020-01-01_2026-06-16.csv"); off=calib(tf)
    for ver,fn in [("v1",seq_v1),("v2",seq_v2)]:
        tr=[t for t in fn(tf,bars,idx,off) if t[0][:4] in ("2025","2026")]
        n=len(tr)
        fails=[t for t in tr if t[5] in ("STOP","B6")]
        stops=[t for t in tr if t[5]=="STOP"]
        # 방향별 승/패
        def dstat(dr):
            sub=[t for t in tr if t[1]==dr]; f=[t for t in sub if t[5] in ("STOP","B6")]
            return len(sub), len(f), (100*len(f)/len(sub) if sub else 0)
        Ln,Lf,Lr=dstat("LONG"); Sn,Sf,Sr=dstat("SHORT")
        print(f"\n{'='*78}\n### {tf} {ver}  25·26년 {n}건 / 실패(STOP+B6) {len(fails)}건 (풀스톱 {len(stops)})")
        print(f"  방향별 실패율:  LONG {Lf}/{Ln} ({Lr:.1f}%)   SHORT {Sf}/{Sn} ({Sr:.1f}%)")
        # 세션별 실패
        sess={}
        for t in fails: sess[t[2]]=sess.get(t[2],0)+1
        print(f"  실패 세션: "+", ".join(f"{s} {c}" for s,c in sorted(sess.items(),key=lambda x:-x[1])))
        # 월별 실패
        mon={}
        for t in fails: mon[t[0][:7]]=mon.get(t[0][:7],0)+1
        print(f"  실패 월: "+", ".join(f"{m} {c}" for m,c in sorted(mon.items())))
        # 풀스톱 직전 반등(MFE) — 0에 가까우면 일방향 추세
        if stops:
            mfes=sorted(t[6] for t in stops)
            lowbounce=sum(1 for t in stops if t[6]<0.5)
            print(f"  풀스톱 반등(MFE) 중앙 {mfes[len(mfes)//2]:.2f}KTR / 0.5KTR미만(거의 일방향) {lowbounce}/{len(stops)}")
        # 풀스톱 개별 리스트
        print(f"  --- 풀스톱 거래 (날짜 방향 세션 KTR 반등MFE 최대역행MAE) ---")
        for dt,d,s,k,mf,kind,mfe,mae in stops:
            print(f"    {dt}  {d:5} {s:4} KTR{k:5.1f}  MFE{mfe:4.1f}  MAE{mae:4.1f}")
