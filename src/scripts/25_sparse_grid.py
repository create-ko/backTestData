# -*- coding: utf-8 -*-
"""25 — 띄엄띄엄(sparse) 그리드 비교 (v2 풀백, TP2, KTR, 등량, 분봉별).
Full: [0,1,2,3,4,4.5] stop5 / A{1,3,5}: [0,2,4] stop4.5 / B{1,2,4,6}: [0,1,3,4.5] stop5
손절=각 구성 손실로 정규화(동일 리스크). 지표: 손절률·기대값(R=base)·MC2%(MDD·손실%)."""
import csv, math, random
random.seed(42)
T=2.0; N_TRADES=2000; M_RUNS=1200; RISK=0.02
CONFIGS={"Full(현재)":([0,1,2,3,4,4.5],5.0),
         "A{1,3,5}":([0,2,4],4.5),
         "B{1,2,4,6}":([0,1,3,4.5],5.0)}

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
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

def sim_levels(bars, start_i, anchor, direction, base, lv, stopm):
    n=len(bars); NL=len(lv)
    if direction=="LONG": E=[anchor-base*x for x in lv]; stop=anchor-base*stopm
    else:                 E=[anchor+base*x for x in lv]; stop=anchor+base*stopm
    filled=[False]*NL; filled[0]=True; dj=0; fc=1; maxJ=0
    for i in range(start_i,n):
        _,o,h,l,c=bars[i]
        for k in range(1,NL):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc:
            fc=nf; last=max(k for k in range(NL) if filled[k]); dj=last; maxJ=max(maxJ,last)
        deep=lv[dj]
        tp=anchor-base*deep+T*base if direction=="LONG" else anchor+base*deep-T*base
        if direction=="LONG":
            if fc>=NL and l<=stop: return maxJ,"STOP"
            if h>=tp: return maxJ,"TP"
        else:
            if fc>=NL and h>=stop: return maxJ,"STOP"
            if l<=tp: return maxJ,"TP"
    return maxJ,"OPEN"

def win_pnl(lv,j): return sum(lv[i]-lv[j]+T for i in range(j+1))   # j까지 체결 후 TP
def stop_pnl(lv,stopm): return sum(x-stopm for x in lv)
def mc(vec):
    mdds=[]; finals=[]
    for _ in range(M_RUNS):
        seq=random.choices(vec,k=N_TRADES); eq=1.0; peak=1.0; mdd=0.0
        for p in seq:
            eq*=(1.0+RISK*p)
            if eq>peak: peak=eq
            dd=(peak-eq)/peak
            if dd>mdd: mdd=dd
        mdds.append(mdd); finals.append(eq)
    mdds.sort(); finals.sort()
    return 100*mdds[len(mdds)//2],100*sum(1 for f in finals if f<1)/len(finals)

def v2_jobs(tf,bars,idx):
    u2,l2=boll([b[1] for b in bars],4,4.0); brk={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    out=[]; pending=None
    for i in range(len(bars)):
        if i in brk: pending=(i,brk[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                if i+1<len(bars):
                    k=float(ps[8])
                    if k>0: out.append((i+1,bars[i+1][1],pdir,k)); pending=None
    return out

for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
    jobs=v2_jobs(tf,bars,idx)
    print(f"\n=== {tf} (v2 {len(jobs)}건) ===")
    print(f"{'구성':<12}{'랏수':>5}{'손절손실':>9}{'손절률':>8}{'기대값(R)':>10}{'중앙MDD':>9}{'손실%':>7}")
    for name,(lv,stopm) in CONFIGS.items():
        sp=stop_pnl(lv,stopm)
        out=[sim_levels(bars,si,a,d,k,lv,stopm) for si,a,d,k in jobs]
        clo=[(j,ex) for j,ex in out if ex in ("TP","STOP")]; n=len(clo)
        stop=sum(1 for j,ex in clo if ex=="STOP")
        ps=[sp if ex=="STOP" else win_pnl(lv,j) for j,ex in clo]; exp=sum(ps)/n
        vec=[(sp if ex=="STOP" else win_pnl(lv,j))/abs(sp) for j,ex in clo]
        md,loss=mc(vec)
        print(f"{name:<12}{len(lv):>5}{sp:>+8.1f}{100*stop/n:>7.2f}%{exp:>+9.3f}{md:>8.1f}%{loss:>6.1f}%")
