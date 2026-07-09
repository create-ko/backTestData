# -*- coding: utf-8 -*-
"""72 - Hourly basic double-BB strategy on XAUUSD.

Run from data/:
  python ../src/scripts/72_hourly_basicbb.py

Rules tested:
- Build 1H bars from XAUUSD 1m data and test on 1H bars only.
- Basic double-BB approximation:
  LONG  when 1H 20MA slope > 0 and 1H low touches 4/4 lower band.
  SHORT when 1H 20MA slope < 0 and 1H high touches 4/4 upper band.
- Enter next 1H open after the signal hour closes.
- TP is 1H 20MA mean reversion.
- SL variants are ATR multiples: 1.5, 3.5, 5.0.
- One position at a time. KST entry window 08:00~23:59.
- If TP and SL are both touched in the same 1H bar, SL wins.

Console output is ASCII-only by AGENT.md rule. Output JSON is UTF-8.
"""
import bisect
import csv
import json
import math
import time

START_H = 8
INITIAL_CAPITAL = 100000.0
RISK = 0.02
SPREAD = 0.30
BB_LEN = 4
BB_MULT = 4.0
MA_LEN = 20
ATR_LEN = 14
SLOPE_LOOKBACK = 3
SL_MULTS = [1.5, 3.5, 5.0]


def load_bars(path):
    t = []
    o = []
    h = []
    l = []
    c = []
    with open(path, encoding="utf-8-sig", newline="") as fp:
        rd = csv.reader(fp)
        next(rd)
        for r in rd:
            tt = int(float(r[0]))
            if tt > 100000000000:
                tt //= 1000
            t.append(tt)
            o.append(float(r[1]))
            h.append(float(r[2]))
            l.append(float(r[3]))
            c.append(float(r[4]))
    return t, o, h, l, c


def resample(t, o, h, l, c, period):
    rt = []
    ro = []
    rh = []
    rl = []
    rc = []
    cur = None
    for i, tt in enumerate(t):
        b = (tt // period) * period
        if b != cur:
            cur = b
            rt.append(b)
            ro.append(o[i])
            rh.append(h[i])
            rl.append(l[i])
            rc.append(c[i])
        else:
            if h[i] > rh[-1]:
                rh[-1] = h[i]
            if l[i] < rl[-1]:
                rl[-1] = l[i]
            rc[-1] = c[i]
    return rt, ro, rh, rl, rc


def sma(src, length):
    out = [None] * len(src)
    s = 0.0
    for i, x in enumerate(src):
        s += x
        if i >= length:
            s -= src[i - length]
        if i >= length - 1:
            out[i] = s / length
    return out


def boll(src, length, mult):
    up = [None] * len(src)
    lo = [None] * len(src)
    s = 0.0
    ss = 0.0
    for i, x in enumerate(src):
        s += x
        ss += x * x
        if i >= length:
            old = src[i - length]
            s -= old
            ss -= old * old
        if i >= length - 1:
            mean = s / length
            var = ss / length - mean * mean
            if var < 0:
                var = 0.0
            dev = mult * math.sqrt(var)
            up[i] = mean + dev
            lo[i] = mean - dev
    return up, lo


def atr(h, l, c, length):
    tr = [0.0] * len(c)
    for i in range(len(c)):
        if i == 0:
            tr[i] = h[i] - l[i]
        else:
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = [None] * len(c)
    s = 0.0
    for i, x in enumerate(tr):
        s += x
        if i >= length:
            s -= tr[i - length]
        if i >= length - 1:
            out[i] = s / length
    return out


def khour(epoch):
    return ((epoch // 3600) + 9) % 24


def kyear(epoch):
    return time.strftime("%Y", time.gmtime(epoch + 9 * 3600))


def maxdd(eq):
    peak = eq[0]
    m = 0.0
    for x in eq:
        if x > peak:
            peak = x
        d = (peak - x) / peak if peak else 0.0
        if d > m:
            m = d
    return 100.0 * m


def pf(xs):
    gp = sum(x for x in xs if x > 0)
    gl = sum(-x for x in xs if x < 0)
    if gl == 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def make_signals(ht, ho, hh, hl, hc):
    ma = sma(hc, MA_LEN)
    bu, bl = boll(ho, BB_LEN, BB_MULT)
    av = atr(hh, hl, hc, ATR_LEN)
    sigs = []
    for i in range(max(MA_LEN + SLOPE_LOOKBACK, ATR_LEN, BB_LEN), len(ht) - 1):
        if ma[i] is None or ma[i - SLOPE_LOOKBACK] is None or bu[i] is None or av[i] is None:
            continue
        slope = ma[i] - ma[i - SLOPE_LOOKBACK]
        if slope > 0 and hl[i] <= bl[i]:
            sigs.append({
                "signal_epoch": ht[i] + 3600,
                "direction": 1,
                "tp": ma[i],
                "atr": av[i],
                "signal_price": hc[i],
                "year": kyear(ht[i]),
            })
        elif slope < 0 and hh[i] >= bu[i]:
            sigs.append({
                "signal_epoch": ht[i] + 3600,
                "direction": -1,
                "tp": ma[i],
                "atr": av[i],
                "signal_price": hc[i],
                "year": kyear(ht[i]),
            })
    return sigs


def resolve_trade(t, o, h, l, c, entry_i, direction, tp, sl):
    for j in range(entry_i, len(t)):
        if direction == 1:
            if l[j] <= sl:
                return j, sl, "SL"
            if h[j] >= tp:
                return j, tp, "TP"
        else:
            if h[j] >= sl:
                return j, sl, "SL"
            if l[j] <= tp:
                return j, tp, "TP"
    return len(t) - 1, c[-1], "FINAL"


def run_variant(t, o, h, l, c, sigs, sl_mult):
    eq = [INITIAL_CAPITAL]
    trades = []
    busy_until = -1
    for s in sigs:
        entry_i = bisect.bisect_left(t, s["signal_epoch"])
        if entry_i >= len(t):
            continue
        if t[entry_i] <= busy_until:
            continue
        if khour(t[entry_i]) < START_H:
            continue
        entry = o[entry_i]
        direction = s["direction"]
        tp = s["tp"]
        # Ignore malformed cases where the mean-reversion TP is already behind entry.
        if direction == 1 and tp <= entry:
            continue
        if direction == -1 and tp >= entry:
            continue
        sl = entry - sl_mult * s["atr"] if direction == 1 else entry + sl_mult * s["atr"]
        exit_i, exit_price, reason = resolve_trade(t, o, h, l, c, entry_i, direction, tp, sl)
        points = (exit_price - entry) * direction
        # Risk-normalized R after approximate round-trip spread.
        risk_points = abs(entry - sl)
        r = (points - SPREAD) / risk_points if risk_points > 0 else 0.0
        pnl = eq[-1] * RISK * r
        eq.append(eq[-1] + pnl)
        trades.append({
            "entry_epoch": t[entry_i],
            "exit_epoch": t[exit_i],
            "direction": "LONG" if direction == 1 else "SHORT",
            "points": points,
            "r": r,
            "pnl": pnl,
            "reason": reason,
            "year": kyear(t[entry_i]),
        })
        busy_until = t[exit_i]
    return trades, eq


def summarize(trades, eq, start, end):
    rs = [x["r"] for x in trades]
    pnls = [x["pnl"] for x in trades]
    wins = sum(1 for x in rs if x > 0)
    years = (end - start) / (365.25 * 86400.0)
    cagr = -100.0 if eq[-1] <= 0 else 100.0 * ((eq[-1] / INITIAL_CAPITAL) ** (1.0 / years) - 1.0)
    return {
        "trades": len(trades),
        "win_rate": round(100.0 * wins / len(trades), 2) if trades else 0.0,
        "net_r": round(sum(rs), 3),
        "return_pct": round(100.0 * (eq[-1] / INITIAL_CAPITAL - 1.0), 3),
        "cagr": round(cagr, 3),
        "mdd": round(maxdd(eq), 3),
        "pf": round(pf(rs), 3) if pf(rs) != float("inf") else "inf",
        "ending_equity": round(eq[-1], 3),
    }


def by_direction(trades):
    out = {}
    for d in ("LONG", "SHORT"):
        xs = [x["r"] for x in trades if x["direction"] == d]
        wins = sum(1 for x in xs if x > 0)
        out[d] = {
            "trades": len(xs),
            "net_r": round(sum(xs), 3),
            "win_rate": round(100.0 * wins / len(xs), 2) if xs else 0.0,
            "pf": round(pf(xs), 3) if xs and pf(xs) != float("inf") else ("inf" if xs else 0.0),
        }
    return out


def by_year(trades):
    out = {}
    for tr in trades:
        out.setdefault(tr["year"], []).append(tr["r"])
    rows = []
    for y in sorted(out):
        xs = out[y]
        wins = sum(1 for x in xs if x > 0)
        rows.append({
            "year": y,
            "trades": len(xs),
            "net_r": round(sum(xs), 3),
            "win_rate": round(100.0 * wins / len(xs), 2),
            "pf": round(pf(xs), 3) if pf(xs) != float("inf") else "inf",
        })
    return rows


def main():
    print("Hourly basicBB XAUUSD | 1H only | entry next 1H open | spread=0.30 | risk=2%")
    print("TF   SLx   sigs trades  win%    netR    CAGR%    MDD%     PF")
    out = {}
    src_t, src_o, src_h, src_l, src_c = load_bars("xauusd_1m_2010-01-01_2026-06-16.csv")
    t, o, h, l, c = resample(src_t, src_o, src_h, src_l, src_c, 3600)
    sigs = make_signals(t, o, h, l, c)
    tf = "1h"
    out[tf] = {}
    for slm in SL_MULTS:
        trades, eq = run_variant(t, o, h, l, c, sigs, slm)
        sm = summarize(trades, eq, t[0], t[-1])
        out[tf][str(slm)] = {
            "summary": sm,
            "direction": by_direction(trades),
            "yearly": by_year(trades),
        }
        print("%-4s %3.1f %6d %6d %6.2f %8.2f %8.3f %7.3f %6s" % (
            tf, slm, len(sigs), sm["trades"], sm["win_rate"], sm["net_r"],
            sm["cagr"], sm["mdd"], str(sm["pf"])
        ))
    with open("hourly_basicbb_summary.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)
    print("WROTE hourly_basicbb_summary.json")


if __name__ == "__main__":
    main()
