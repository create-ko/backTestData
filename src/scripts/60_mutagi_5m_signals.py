#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""60_mutagi_5m_signals.py
무따기 5분봉 Tip 3전략(S1/S2/S3) x 매수/매도 트레이드 생성.
입력 : xauusd_{2m,5m,10m}_2010-01-01_2026-06-16.csv  (cwd=data/)
출력 : mutagi_trades_{2m,5m,10m}.csv
실행 : cd data && python ../src/scripts/60_mutagi_5m_signals.py
"""
import csv, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutagi_engine as M

TFS = ["2m", "5m", "10m"]
STRATS = ["S1", "S2", "S3"]
DIRS = ["LONG", "SHORT"]
COST = 0.4
COLS = ["strategy", "direction", "tf", "entry_dt_kst", "entry_epoch", "exit_dt_kst",
        "entry_price", "exit_price", "points_gross", "points_net",
        "pct_gross", "pct_net", "hold_bars", "year", "open_at_end"]


def load_bars(path):
    bars = []
    with open(path, encoding="utf-8-sig") as fp:
        rd = csv.reader(fp); next(rd)
        for r in rd:
            bars.append(M.Bar(int(float(r[0])), float(r[1]), float(r[2]),
                              float(r[3]), float(r[4])))
    return bars


def main():
    for tf in TFS:
        path = "xauusd_%s_2010-01-01_2026-06-16.csv" % tf
        bars = load_bars(path)
        ind = M.compute_indicators(bars)   # 20/120/4/4 defaults
        rows = []
        for strat in STRATS:
            for d in DIRS:
                tr = M.generate_trades(bars, ind, strat, d, cost=COST, tf=tf)
                rows.extend(tr)
                print("[%s] %s %s: %d trades" % (tf, strat, d, len(tr)))
        out = "mutagi_trades_%s.csv" % tf
        with open(out, "w", newline="", encoding="utf-8-sig") as fp:
            w = csv.writer(fp); w.writerow(COLS)
            for t in rows:
                w.writerow([t[c] for c in COLS])
        print("[%s] wrote %s (%d rows)" % (tf, out, len(rows)))


if __name__ == "__main__":
    main()
