# -*- coding: utf-8 -*-
import csv
from collections import defaultdict
rows=[r for r in csv.DictReader(open("ktr_takeprofit_N_all_tf_2010-01-01_2026-06-16.csv",encoding="utf-8-sig"))
      if r["base종류"]=="KTR" and r["손절여부"]=="No" and r["TF"]=="2m"]
LAB=["바로출발","1번눌림","2번눌림","3번눌림","4번눌림","6차"]
KP={"바로출발":"0","1번눌림":"-1","2번눌림":"-2","3번눌림":"-3","4번눌림":"-4","6차":"-4.5"}
THR=[1,2,3,4,5,6,7,8]
g=defaultdict(list)
for r in rows: g[r["단계라벨"]].append(float(r["최대도달R_트레일1base"]))
print(f"2m / KTR / 트레일 — ≥N KTR 도달률(%)")
print(f"{'단계':<14}{'n':>7}"+"".join(f"{'≥'+str(t):>6}" for t in THR))
for lab in LAB:
    v=g.get(lab,[]); n=len(v)
    if not n: continue
    print(f"{lab+'('+KP[lab]+')':<14}{n:>7}"+"".join(f"{round(100*sum(1 for x in v if x>=t)/n):>5}%" for t in THR))
