# -*- coding: utf-8 -*-
"""ktr_takeprofit_N 기준 단계별 도달률 + 6차 손절률 (KTR / BREAKOUT, fresh)."""
import csv
from collections import defaultdict

SRC = "ktr_takeprofit_N_all_tf_2020-01-01_2026-06-16.csv"
LAB_ORDER = ["바로출발","1번눌림","2번눌림","3번눌림","4번눌림","6차"]
rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))

for base in ["KTR","BREAKOUT"]:
    sub = [r for r in rows if r["base종류"] == base]
    n = len(sub)
    stopped = sum(1 for r in sub if r["손절여부"] == "Yes")
    six = [r for r in sub if r["단계라벨"] == "6차"]
    six_stop = sum(1 for r in six if r["손절여부"] == "Yes")
    print(f"\n=== {base} (fresh {n}건) ===")
    print(f"전체 손절률: {100*stopped/n:.2f}%  ({stopped}/{n})")
    print(f"6차 도달: {len(six)}건 ({100*len(six)/n:.1f}%) → 그중 손절 {six_stop}건 = 6차 손절률 {100*six_stop/len(six):.1f}%")
    # 단계별 도달 분포 + 손절
    cnt = defaultdict(int); stp = defaultdict(int)
    for r in sub:
        cnt[r["단계라벨"]] += 1
        if r["손절여부"] == "Yes": stp[r["단계라벨"]] += 1
    print("  단계별 도달(비율) / 손절:")
    for lab in LAB_ORDER:
        c = cnt[lab]
        if not c: continue
        print(f"    {lab:<6}: {c:>6} ({100*c/n:4.1f}%)  손절 {stp[lab]}")
