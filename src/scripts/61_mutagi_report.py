#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""61_mutagi_report.py
mutagi_trades_{tf}.csv -> result/mutagi_5m_report.html (연도별 통계).
실행 : cd data && python ../src/scripts/61_mutagi_report.py
"""
import csv, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutagi_engine as M

TFS = ["2m", "5m", "10m"]
STRATS = ["S1", "S2", "S3"]
DIRS = ["LONG", "SHORT"]
STRAT_LABEL = {"S1": "S1 원비터치", "S2": "S2 즉시", "S3": "S3 장기이평터치"}
EMPTY = {"trades": 0, "win_rate": 0, "total_points": 0, "avg_points": 0,
         "total_pct": 0, "avg_pct": 0, "pf": 0, "mdd": 0, "avg_hold": 0}


def load_trades(tf):
    path = "mutagi_trades_%s.csv" % tf
    out = []
    with open(path, encoding="utf-8-sig") as fp:
        rd = csv.DictReader(fp)
        for r in rd:
            out.append({
                "strategy": r["strategy"], "direction": r["direction"],
                "year": int(r["year"]),
                "points_net": float(r["points_net"]),
                "pct_net": float(r["pct_net"]),
                "hold_bars": int(r["hold_bars"]),
                "open_at_end": r["open_at_end"] == "True",
            })
    return out


def fmt(x, nd=2):
    if x == float("inf"):
        return "inf"
    return ("%." + str(nd) + "f") % x


def year_table(agg):
    years = sorted(y for y in agg if y != "ALL")
    head = ("<tr><th>연도</th><th>거래수</th><th>승률%</th><th>총pt</th>"
            "<th>평균pt</th><th>총%</th><th>PF</th><th>MDD(pt)</th><th>평균보유봉</th></tr>")
    rows = []
    for y in years + ["ALL"]:
        s = agg[y]
        label = "전체" if y == "ALL" else str(y)
        rows.append(
            "<tr%s><td>%s</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                ' class="all"' if y == "ALL" else "",
                label, s["trades"], fmt(s["win_rate"], 1), fmt(s["total_points"]),
                fmt(s["avg_points"]), fmt(s["total_pct"]), fmt(s["pf"]),
                fmt(s["mdd"]), fmt(s["avg_hold"], 1)))
    return "<table>" + head + "".join(rows) + "</table>"


def main():
    blocks = []
    for tf in TFS:
        trades = load_trades(tf)
        for strat in STRATS:
            for d in DIRS:
                sub = [t for t in trades if t["strategy"] == strat and t["direction"] == d]
                agg = M.aggregate_by_year(sub) if sub else {"ALL": dict(EMPTY)}
                title = "%s / %s / %s" % (tf, STRAT_LABEL[strat],
                                          "매수" if d == "LONG" else "매도")
                blocks.append("<section><h2>%s</h2>%s</section>" % (title, year_table(agg)))

    html = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>무따기 5분봉 Tip 백테스트 (골드)</title>
<style>
body{font-family:system-ui,'Malgun Gothic',sans-serif;margin:24px;background:#0f1115;color:#e6e6e6}
h1{font-size:20px} h2{font-size:15px;margin-top:28px;color:#7fd1ff}
table{border-collapse:collapse;margin-top:6px;font-size:13px}
th,td{border:1px solid #333;padding:4px 8px;text-align:right}
th{background:#1a1d24} td:first-child,th:first-child{text-align:left}
tr.all td{font-weight:bold;background:#202531}
.note{color:#9aa;font-size:12px;margin:8px 0 20px}
</style></head><body>
<h1>무따기 5분봉 Tip 백테스트 — 골드 (2010-2026)</h1>
<p class="note">3전략(원비터치/즉시/장기이평터치) x 2m,5m,10m x 매수/매도.
20/120 SMA 크로스 추세필터, 데드(롱)/골든(숏) 크로스 청산, 비용 0.4(net), 1크로스 1진입.
손익은 고정 1랏 기준 가격 포인트. 연도는 진입연도 기준.</p>
%s
</body></html>""" % "".join(blocks)

    outdir = os.path.join("..", "result")
    outpath = os.path.join(outdir, "mutagi_5m_report.html")
    with open(outpath, "w", encoding="utf-8") as fp:
        fp.write(html)
    print("wrote %s" % outpath)


if __name__ == "__main__":
    main()
