# -*- coding: utf-8 -*-
"""TF별 돌파 꼬리비율 분포 (signals_all_tf 2020-2026)."""
import csv
from collections import defaultdict

BINS = [(0.00,0.05),(0.05,0.10),(0.10,0.15),(0.15,0.20),
        (0.20,0.30),(0.30,0.50),(0.50,1.0001)]
rows = list(csv.DictReader(open("signals_all_tf_2020-01-01_2026-06-16.csv", encoding="utf-8-sig")))

byTF = defaultdict(list)
for r in rows:
    byTF[r["TF"]].append(float(r["꼬리비율"]))

print(f"\n{'='*64}\n TF별 돌파 꼬리비율 분포 (전체 {len(rows)}건)\n{'='*64}")
hdr = "구간        " + "".join(f"{tf:>14}" for tf in ["2m","5m","10m"])
print(hdr)
for lo, hi in BINS:
    cells = ""
    for tf in ["2m","5m","10m"]:
        vals = byTF[tf]; c = sum(1 for v in vals if lo <= v < hi)
        cells += f"{c:>7}({100*c/len(vals):4.1f}%)"
    print(f"{lo:.2f}~{hi:<6.2f}{cells}")

print("\n누적/요약:")
for tf in ["2m","5m","10m"]:
    vals = byTF[tf]; n = len(vals)
    le10 = sum(1 for v in vals if v <= 0.10)
    le20 = sum(1 for v in vals if v <= 0.20)
    med = sorted(vals)[n//2]
    avg = sum(vals)/n
    print(f"  {tf:>4}: n={n}  꼬리<=0.10 {100*le10/n:.1f}%  <=0.20 {100*le20/n:.1f}%  "
          f"중앙값 {med:.3f}  평균 {avg:.3f}")
