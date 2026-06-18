#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04c_takeprofit_pullback.py — 풀백 진입 버전
진입규칙: 돌파 발생 후, BB2(시가4·4σ) 반대편 밴드를 처음 터치한 봉의 '다음 시가'에 진입.
  LONG 돌파 → 저가 < BB2하단 첫 터치 → 다음 시가 롱
  SHORT 돌파 → 고가 > BB2상단 첫 터치 → 다음 시가 숏
  대기 중 새 돌파 발생 시 그 돌파를 새 기준으로 교체(방향도 갱신).
그리드: 새 진입가 앵커, base=원 돌파의 KTR/돌파캔들크기. 나머지(MFE 측정)는 04b와 동일.
출력: ktr_takeprofit_N_v2_all_tf_2010-01-01_2026-06-16.csv  (04b와 동일 스키마)
"""
import csv, math, datetime
from datetime import timezone, timedelta
KST = timezone(timedelta(hours=9))
mult=[0,1,2,3,4,4.5]; TRAIL=1.0
LAB={1:"바로출발",2:"1번눌림",3:"2번눌림",4:"3번눌림",5:"4번눌림",6:"6차"}

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars)
            bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars, idx

def boll(src,length,m):
    n=len(src); up=[None]*n; lo=[None]*n; s=ss=0.0
    for i in range(n):
        v=src[i]; s+=v; ss+=v*v
        if i>=length: rm=src[i-length]; s-=rm; ss-=rm*rm
        if i>=length-1:
            mean=s/length; var=ss/length-mean*mean
            if var<0: var=0.0
            d=m*math.sqrt(var); up[i]=mean+d; lo[i]=mean-d
    return up, lo

def run_pullback(bars, eb, direction, base):
    n=len(bars); entry=bars[eb][1]
    if direction=="LONG": E=[entry-base*x for x in mult]; stop=entry-base*5
    else:                 E=[entry+base*x for x in mult]; stop=entry+base*5
    fp=[None]*6; fp[0]=entry; filled=[False]*6; filled[0]=True
    deepest=entry; peak=0.0; wentPos=False
    aDone=False; fcA=1; peakA=0.0; pbA=0; stoppedA=False; peakB=0.0
    for j,i in enumerate(range(eb,n)):
        _,o,h,l,c=bars[i]; nf=False
        for k in range(1,6):
            if not filled[k] and ((direction=="LONG" and l<=E[k]) or (direction=="SHORT" and h>=E[k])):
                filled[k]=True; fp[k]=E[k]; nf=True
        fc=sum(filled); last=max(k for k in range(6) if filled[k])
        if nf: deepest=fp[last]; peak=0.0; wentPos=False
        r=(h-deepest)/base if direction=="LONG" else (deepest-l)/base
        if r>peak: peak=r; pk=j
        if r>peakB: peakB=r
        if fc>=6 and ((direction=="LONG" and l<=stop) or (direction=="SHORT" and h>=stop)):
            if not aDone: fcA,peakA,pbA,stoppedA,aDone=fc,peak,j,True,True
            return fcA,peakA,pbA,stoppedA,entry,peakB
        if not aDone:
            if direction=="LONG":
                if h>deepest: wentPos=True
                if wentPos and l<=deepest: fcA,peakA,pbA,aDone=fc,peak,j,True
            else:
                if l<deepest: wentPos=True
                if wentPos and h>=deepest: fcA,peakA,pbA,aDone=fc,peak,j,True
        if peak>=TRAIL and ((direction=="LONG" and l<=deepest+(peak-TRAIL)*base)
                            or (direction=="SHORT" and h>=deepest-(peak-TRAIL)*base)):
            if not aDone: fcA,peakA,pbA,aDone=fc,peak,j,True
            return fcA,peakA,pbA,stoppedA,entry,peakB
    if not aDone: fcA,peakA,pbA=sum(filled),peak,j
    return fcA,peakA,pbA,stoppedA,entry,peakB

HEADER=["signal_id","datetime_kst","TF","방향","세션","꼬리비율","진입가","base종류","base값",
        "체결단계","단계라벨","익절가능N","최대도달R_본전복귀","최대도달R_트레일1base","엔트리기준_도달ktr","손절여부","도달봉수"]
out=[]; stat={}
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv"); n=len(bars)
    u2,l2=boll([b[1] for b in bars],4,4.0)
    brk={}
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is not None: brk[bi]=s
    # 진입 탐색
    entries=[]; pending=None
    for i in range(n):
        if i in brk: pending=(i,brk[i]); continue
        if pending:
            pi,ps=pending; pdir=ps[4]; _,o,h,l,c=bars[i]
            if (pdir=="LONG" and l<l2[i]) or (pdir=="SHORT" and h>u2[i]):
                if i+1<n: entries.append((i+1,ps)); pending=None
    cnt=0
    for eb,ps in entries:
        pdir=ps[4]; ktr=float(ps[8]); brk_sz=float(ps[9])
        dt=datetime.datetime.fromtimestamp(bars[eb][0],KST).strftime("%Y-%m-%d %H:%M")
        for bk,bval in [("KTR",ktr),("BREAKOUT",brk_sz)]:
            if bval<=0: continue
            fc,peakA,pbA,stopped,entry,peakB=run_pullback(bars,eb,pdir,bval)
            out.append([ps[0],dt,tf,pdir,ps[5],ps[6],round(entry,4),bk,round(bval,4),
                        fc,LAB[fc],math.floor(peakA),round(peakA,3),round(peakB,3),
                        round(peakA-mult[fc-1],3),"Yes" if stopped else "No",pbA])
        cnt+=1
    stat[tf]=(len(brk),cnt)
with open("ktr_takeprofit_N_v2_all_tf_2010-01-01_2026-06-16.csv","w",newline="",encoding="utf-8-sig") as fp:
    w=csv.writer(fp); w.writerow(HEADER); w.writerows(out)
print(f"총 {len(out)}행 (KTR {sum(1 for r in out if r[7]=='KTR')}) -> ktr_takeprofit_N_v2_all_tf_...csv")
for tf,(nb,ne) in stat.items():
    print(f"  [{tf}] 돌파 {nb}건 → 풀백 진입 {ne}건 ({100*ne/nb:.0f}%)")
