# -*- coding: utf-8 -*-
"""16_mc_v1_v2.py — v1(즉시) vs v2(풀백) 몬테카를로 드로다운 비교 (TP2, KTR)."""
import csv, random
random.seed(42)
MULT=[0,1,2,3,4,4.5]; T=2.0
N_TRADES=2000; M_RUNS=2000; RISKS=[0.02,0.05,0.10]
SCHEMES={"등량":[1,1,1,1,1,1],"1·1·2·2·3·4":[1,1,2,2,3,4]}

def stop_units(w): return sum(w[i]*(5-MULT[i]) for i in range(6))
def win_units(w,k): return sum(w[i]*(MULT[i]-MULT[k-1]+T) for i in range(k))

def load_outcomes(f, isv2):
    rows=[]
    for r in csv.DictReader(open(f,encoding="utf-8-sig")):
        if r["base종류"]!="KTR": continue
        ex=r["exitReason"]
        if ex not in ("TP","STOP"): continue
        rows.append((int(r["maxFilledCount"]), ex))
    return rows

V1=load_outcomes("sim_tp2_all_tf_2010-01-01_2026-06-16.csv",False)
V2=load_outcomes("sim_v2_tp2_all_tf_2010-01-01_2026-06-16.csv",True)

def pnl_vec(rows,w):
    su=stop_units(w)
    return [(-1.0 if ex=="STOP" else win_units(w,mf)/su) for mf,ex in rows]

def mc(vec, r):
    mdds=[]; finals=[]
    for _ in range(M_RUNS):
        seq=random.choices(vec,k=N_TRADES)
        eq=1.0; peak=1.0; mdd=0.0
        for p in seq:
            eq*=(1.0+r*p)
            if eq>peak: peak=eq
            dd=(peak-eq)/peak
            if dd>mdd: mdd=dd
        mdds.append(mdd); finals.append(eq)
    mdds.sort(); finals.sort()
    return (mdds[len(mdds)//2], mdds[int(0.95*len(mdds))],
            100*sum(1 for m in mdds if m>=0.5)/len(mdds),
            100*sum(1 for m in mdds if m>=0.8)/len(mdds),
            finals[len(finals)//2], 100*sum(1 for f in finals if f<1)/len(finals))

for sname,w in SCHEMES.items():
    print(f"\n{'='*78}\n 랏={sname} / TP2 / 부트스트랩 {N_TRADES}거래×{M_RUNS}회\n{'='*78}")
    v1v=pnl_vec(V1,w); v2v=pnl_vec(V2,w)
    print(f"   건당기대(R): v1 {sum(v1v)/len(v1v):+.4f}  v2 {sum(v2v)/len(v2v):+.4f}")
    print(f"   {'리스크':>5} {'버전':>4}{'중앙MDD':>9}{'95%MDD':>9}{'P(>50%)':>9}{'P(>80%)':>9}{'중앙배수':>9}{'손실%':>8}")
    for r in RISKS:
        for name,vec in [("v1",v1v),("v2",v2v)]:
            m=mc(vec,r)
            print(f"   {int(r*100):>4}% {name:>4}{100*m[0]:>8.1f}%{100*m[1]:>8.1f}%{m[2]:>8.1f}%{m[3]:>8.1f}%{m[4]:>8.2f}x{m[5]:>7.1f}%")
