# -*- coding: utf-8 -*-
"""21_per_tf_summary.py — 분봉별 v1(즉시) vs v2(풀백) 종합 (TP2, KTR, 등량).
지표: 거래수·손절률·승률·기대값(R=base) + 몬테카를로 2% (중앙MDD·P(>50%)·손실확률)."""
import csv, random
random.seed(42)
MULT=[0,1,2,3,4,4.5]; T=2.0; STOP=sum(MULT[i]-5 for i in range(6))  # -15.5
def win_pnl(k): return sum(MULT[i]-MULT[k-1]+T for i in range(k))
N_TRADES=2000; M_RUNS=2000; RISK=0.02

def load(f, v2):
    rows=[]
    for r in csv.DictReader(open(f,encoding="utf-8-sig")):
        if r["base종류"]!="KTR": continue
        ex=r["exitReason"]
        if ex not in ("TP","STOP"): continue
        rows.append((r["TF"], int(r["maxFilledCount"]), ex))
    return rows

V={"v1 즉시":load("sim_tp2_all_tf_2010-01-01_2026-06-16.csv",False),
   "v2 풀백":load("sim_v2_tp2_all_tf_2010-01-01_2026-06-16.csv",True)}

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
    return 100*mdds[len(mdds)//2], 100*sum(1 for m in mdds if m>=0.5)/len(mdds), 100*sum(1 for f in finals if f<1)/len(finals)

print(f"분봉별 v1 vs v2 (TP2·등량·KTR) / 몬테카를로 2%리스크·{N_TRADES}거래\n")
print(f"{'TF':>4}{'버전':>7}{'거래수':>8}{'손절%':>8}{'승률%':>7}{'기대값(R)':>10}{'중앙MDD':>9}{'P(>50%)':>9}{'손실%':>7}")
for tf in ["2m","5m","10m"]:
    for vname,rows in V.items():
        sub=[(mf,ex) for t,mf,ex in rows if t==tf]
        n=len(sub); stop=sum(1 for mf,ex in sub if ex=="STOP")
        ps=[STOP if ex=="STOP" else win_pnl(mf) for mf,ex in sub]
        exp=sum(ps)/n; win=100*sum(1 for p in ps if p>0)/n
        vec=[(-1.0 if ex=="STOP" else win_pnl(mf)/abs(STOP)) for mf,ex in sub]
        md,p50,loss=mc(vec)
        print(f"{tf:>4}{vname:>7}{n:>8}{100*stop/n:>7.2f}%{win:>6.1f}%{exp:>+9.3f}{md:>8.1f}%{p50:>8.1f}%{loss:>6.1f}%")
    print()
