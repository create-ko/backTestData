#!/usr/bin/env python3
# 골드 2010-2019 데이터 무결성 검증 (1m/2m/5m/10m 전부)
# - 행수/기간/단조성·중복·역순/봉간격 일관성/누락(월별·주별)/가격 sanity/소수자릿수
# - 2020-2026 데이터와 경계 연속성(겹침/공백) 대조
import csv, os, sys, datetime as dt
from collections import defaultdict

DATA = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
KST = 9 * 3600
TF_SEC = {'1m': 60, '2m': 120, '5m': 300, '10m': 600}

def kst(sec):
    return dt.datetime.utcfromtimestamp(sec + KST).strftime('%Y-%m-%d %H:%M')

def kst_month(sec):
    d = dt.datetime.utcfromtimestamp(sec + KST)
    return f'{d.year}-{d.month:02d}'

def load(fp):
    rows = []
    with open(fp, encoding='utf-8-sig') as f:
        r = csv.reader(f)
        next(r)  # header
        for c in r:
            if not c:
                continue
            rows.append((int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])))
    return rows

def verify(tf):
    fp = os.path.join(DATA, f'xauusd_{tf}_2010-01-01_2019-12-31.csv')
    print(f'\n{"="*60}\n[{tf}]  {os.path.basename(fp)}')
    if not os.path.exists(fp):
        print('  ❌ 파일 없음'); return None
    rows = load(fp)
    n = len(rows)
    step = TF_SEC[tf]
    times = [r[0] for r in rows]

    # 단조/중복/역순
    dup = back = 0
    for i in range(1, n):
        if times[i] == times[i-1]: dup += 1
        elif times[i] < times[i-1]: back += 1
    sorted_ok = all(times[i] >= times[i-1] for i in range(1, n))

    # 간격 일관성 (정렬본 기준)
    st = sorted(times)
    gap_hist = defaultdict(int)
    big_gaps = []  # (start, end, gap_sec)
    for i in range(1, len(st)):
        d = st[i] - st[i-1]
        gap_hist[d] += 1
        if d > step:  # 결손/주말
            big_gaps.append((st[i-1], st[i], d))

    # 가격 sanity (골드 2010-2019: 대략 1040~1920)
    closes = [r[4] for r in rows]
    highs = [r[2] for r in rows]; lows = [r[3] for r in rows]
    opens = [r[1] for r in rows]
    ohlc_bad = sum(1 for o,h,l,c in zip(opens,highs,lows,closes)
                   if not (l <= o <= h and l <= c <= h and l <= h))
    nonpos = sum(1 for c in closes if c <= 0)
    pmin, pmax = min(closes), max(closes)

    # 소수자릿수
    dec = max(len(str(c).split('.')[1]) if '.' in str(c) else 0 for c in closes[:500])

    # 월별 봉수 (누락 의심)
    by_month = defaultdict(int)
    for t in times: by_month[kst_month(t)] += 1
    months = sorted(by_month)
    # 분봉별 정상 월 봉수 추정: 5일*~22h(거래시간) 근사 대신 중앙값 대비 50% 미만을 의심
    counts = sorted(by_month.values())
    med = counts[len(counts)//2]
    suspect = [(m, by_month[m]) for m in months if by_month[m] < med * 0.5]

    print(f'  총 봉수      : {n:,}')
    print(f'  기간(KST)    : {kst(min(times))} ~ {kst(max(times))}')
    print(f'  정렬상태     : {"OK 단조증가" if sorted_ok else "⚠ 비정렬"}  / 중복 {dup}  / 역순 {back}')
    print(f'  봉 간격      : 정상({step}s) {gap_hist.get(step,0):,}개  / 비정상간격 {len(big_gaps):,}개')
    # 가장 큰 공백 top5 (주말 제외 위해 24h 초과만)
    over_day = sorted([g for g in big_gaps if g[2] > 86400], key=lambda x:-x[2])[:5]
    if over_day:
        print(f'  24h↑ 공백 top: ')
        for s,e,d in over_day:
            print(f'      {kst(s)} → {kst(e)}  ({d/86400:.1f}일)')
    print(f'  가격범위(C)  : {pmin:.3f} ~ {pmax:.3f}  {"✓정상대역" if 900<pmin and pmax<2000 else "⚠ 범위확인"}')
    print(f'  OHLC 위배    : {ohlc_bad}  / 0이하가격 {nonpos}  / 소수자릿수 {dec}')
    print(f'  월수         : {len(months)}개월 ({months[0]}~{months[-1]}), 월봉수 중앙값 {med:,}')
    if suspect:
        print(f'  ⚠ 봉수 부족 의심월(중앙값 50%↓): {len(suspect)}개')
        for m,c in suspect[:8]:
            print(f'      {m}: {c:,}')
    else:
        print(f'  누락 의심월  : 없음')
    return {'n': n, 'min': min(times), 'max': max(times), 'rows': rows}

def boundary_check(tf, info10):
    # 2010-2019 끝 ↔ 2020-2026 시작 연속성
    fp2 = os.path.join(DATA, f'xauusd_{tf}_2020-01-01_2026-06-16.csv')
    if not os.path.exists(fp2) or info10 is None:
        return
    rows2 = load(fp2)
    t2_first = rows2[0][0]
    t1_last = info10['max']
    step = TF_SEC[tf]
    gap = t2_first - t1_last
    print(f'  [{tf}] 2019끝 {kst(t1_last)} → 2020시작 {kst(t2_first)}  공백 {gap/3600:.1f}h ({gap/step:.0f}봉)')

if __name__ == '__main__':
    print('골드 XAUUSD 2010-01-01 ~ 2019-12-31 무결성 검증')
    infos = {}
    for tf in ['2m', '5m', '10m', '1m']:
        infos[tf] = verify(tf)
    print(f'\n{"="*60}\n[경계 연속성] 2010-2019 ↔ 2020-2026')
    for tf in ['2m', '5m', '10m', '1m']:
        boundary_check(tf, infos.get(tf))
