# -*- coding: utf-8 -*-
"""50 - '-1 눌림 이후 손실 없나?' 검증. 전 신호 v1 그리드 시뮬, 깊이별 최종결과.
차트의 '1번 눌림 칸'은 깊이가 정확히 -1에서 끝난 것만(생존편향) → 100% 승.
진짜 리스크 = '-1을 찍은(깊이≥1) 모든 트레이드 중 풀그리드까지 가서 손실난 비율'.
data/에서 실행: cd data && python ../src/scripts/50_pullback_outcome.py"""
import csv, math
MULT=[0,1,2,3,4,4.5]; TP=1.5; B6X=1.0; STOPM=5.0

def load(f):
    bars=[]; idx={}
    with open(f,encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for r in rd:
            t=int(float(r[0])); idx[t]=len(bars); bars.append((t,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
    return bars,idx
def sim(bars, eb, a, d, base):
    n=len(bars)
    if d=="LONG": E=[a-base*MULT[i] for i in range(6)]; stop=a-base*STOPM
    else:         E=[a+base*MULT[i] for i in range(6)]; stop=a+base*STOPM
    filled=[False]*6; filled[0]=True; deepest=E[0]; fc=1; maxF=1
    for i in range(eb,n):
        _,o,h,l,c=bars[i]
        for k in range(1,6):
            if not filled[k] and ((d=="LONG" and l<=E[k]) or (d=="SHORT" and h>=E[k])): filled[k]=True
        nf=sum(filled)
        if nf!=fc: fc=nf; maxF=max(maxF,nf); last=max(k for k in range(6) if filled[k]); deepest=E[last]
        thr=TP if fc<6 else B6X
        tp=deepest+thr*base if d=="LONG" else deepest-thr*base
        if d=="LONG":
            if fc>=6 and l<=stop: return maxF,"STOP"
            if h>=tp: return maxF,("B6" if fc==6 else "TP")
        else:
            if fc>=6 and h>=stop: return maxF,"STOP"
            if l<=tp: return maxF,("B6" if fc==6 else "TP")
    return maxF,"OPEN"

LAB={1:"바로출발(0눌림)",2:"1번눌림",3:"2번눌림",4:"3번눌림",5:"4번눌림",6:"5번눌림(6차)"}
for tf in ["2m","5m","10m"]:
    bars,idx=load(f"xauusd_{tf}_2010-01-01_2026-06-16.csv")
    rows=[]
    with open(f"signals_{tf}_2010-01-01_2026-06-16.csv",encoding="utf-8-sig") as fp:
        rd=csv.reader(fp); next(rd)
        for s in rd:
            bi=idx.get(int(s[2]))
            if bi is None or bi+1>=len(bars): continue
            k=float(s[8])
            if k>0: rows.append((bi+1,float(s[7]),s[4],k))
    out=[sim(bars,eb,a,d,k) for eb,a,d,k in rows]
    clo=[(mf,kd) for mf,kd in out if kd!="OPEN"]; n=len(clo)
    # 깊이별 분포 + 결과
    from collections import Counter
    depth=Counter(mf for mf,kd in clo)
    print(f"\n{'='*70}\n### {tf}  (청산 {n}건) - v1 전 신호")
    print(f"{'최대깊이':<16}{'건수':>8}{'비중':>8}{'결과'}")
    for mf in range(1,7):
        c=depth[mf]
        res = "전부 승(TP)" if mf<6 else "전부 손실(반등/풀스톱)"
        print(f"  {LAB[mf]:<14}{c:>8}{100*c/n:>7.1f}%  {res}")
    # 핵심: -1 찍은(깊이>=2) 트레이드의 최종 결과
    touch1=[(mf,kd) for mf,kd in clo if mf>=2]; nt=len(touch1)
    loss=sum(1 for mf,kd in touch1 if mf==6)
    print(f"\n  >> '-1 찍은(1번이상 눌린)' 트레이드 {nt}건 ({100*nt/n:.1f}%):")
    print(f"      이김(2~5번에서 회복·TP): {nt-loss}건 ({100*(nt-loss)/nt:.1f}%)")
    print(f"      손실(끝까지 가서 6차 손절): {loss}건 ({100*loss/nt:.1f}%)  <- '눌리면 손실없다'의 반례")
    # 비교: 차트의 '1번눌림 칸' = 깊이 정확히 2
    e2=depth[2]
    print(f"  > 참고: 차트 '1번눌림 칸'(깊이 정확히 -1) {e2}건 = 전부 승 (생존편향: 더 깊이 간 건 다른 칸으로 빠짐)")
