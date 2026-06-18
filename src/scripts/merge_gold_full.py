#!/usr/bin/env python3
# 골드 2010-2019 + 2020-2026 → 단일 2010-2026 합본 (1/2/5/10m)
# 겹침(2020-01-01) dedup, 1차 확정 파일(2020-2026) 우선. 원본은 보존.
import csv, os, datetime as dt

DATA = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
TFS = ['1m', '2m', '5m', '10m']
KST = 9 * 3600
kst = lambda s: dt.datetime.utcfromtimestamp(s + KST).strftime('%Y-%m-%d %H:%M')

def read_rows(fp, m):
    """ts -> raw line. 이미 있으면 건드리지 않음(우선권 보존)."""
    added = 0
    with open(fp, encoding='utf-8-sig') as f:
        first = True
        for line in f:
            line = line.rstrip('\n').lstrip('﻿')
            if first:
                first = False
                if line.startswith('time,'):
                    continue
            if not line:
                continue
            ts = int(line.split(',', 1)[0])
            if ts not in m:
                m[ts] = line
                added += 1
    return added

for tf in TFS:
    f_old = os.path.join(DATA, f'xauusd_{tf}_2010-01-01_2019-12-31.csv')
    f_new = os.path.join(DATA, f'xauusd_{tf}_2020-01-01_2026-06-16.csv')
    out   = os.path.join(DATA, f'xauusd_{tf}_2010-01-01_2026-06-16.csv')

    m = {}
    n_new = read_rows(f_new, m)   # 1차 확정 우선 적재
    before = len(m)
    n_old = read_rows(f_old, m)   # 과거분은 누락 ts만 추가
    old_total = sum(1 for _ in open(f_old, encoding='utf-8-sig')) - 1  # 헤더 제외
    overlap_dedup = old_total - n_old   # 기존(2010-2019)에서 겹쳐 제거된 행수

    ts_sorted = sorted(m)
    # 무결성 점검
    dup = back = 0
    for i in range(1, len(ts_sorted)):
        if ts_sorted[i] == ts_sorted[i-1]: dup += 1
        elif ts_sorted[i] < ts_sorted[i-1]: back += 1

    with open(out, 'w', encoding='utf-8') as f:
        f.write('﻿time,open,high,low,close,volume\n')
        for t in ts_sorted:
            f.write(m[t] + '\n')

    print(f'[{tf}] 2020+ {n_new:,} + 2010-2019 추가 {n_old:,} = {len(ts_sorted):,}행 '
          f'(겹침 dedup {overlap_dedup:,})')
    print(f'     기간 {kst(ts_sorted[0])} ~ {kst(ts_sorted[-1])} | 중복 {dup} 역순 {back} -> {os.path.basename(out)}')
print('합본 완료. 원본 4쌍은 보존됨.')
