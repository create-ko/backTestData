# -*- coding: utf-8 -*-
"""71 - Pine V22 multi-factor strategy on XAUUSD 2m/5m/10m.

Run from data/:
  python ../src/scripts/71_multifactor_v22_gold.py

Console output is ASCII-only by AGENT.md rule. Files are UTF-8.
Assumptions:
- Pine-like next-bar-open fills because calc_on_every_tick=false and no
  process_orders_on_close.
- No default_qty_type/value is set in the Pine strategy, so this uses fixed
  quantity 1.
- Costs/slippage are not included unless COST_PER_TRADE is changed.
"""
import csv
import json
import math
import time

FAST = 12
SLOW = 26
SIG = 7
STOCH_LEN = 14
STOCH_SIG = 3
MOM_LEN = 10
RSI_LEN = 7
RSI_LONG_LIMIT = 100
RSI_SHORT_LIMIT = 30
PSAR_START = 0.0
PSAR_INC = 0.02
PSAR_MAX = 0.2
VORTEX_LEN = 8
DMI_LEN = 8
MFI_LEN = 10
FISH_LEN = 10
FISH_SIG = 6
LONG_SCORE_TH = 4
LONG_EXIT_TH = 1
SHORT_SCORE_TH = -6
SHORT_EXIT_TH = -2
BANKRUPT_PCT = 50.0
INITIAL_CAPITAL = 100000.0
QTY = 1.0
COST_PER_TRADE = 0.0


def load_bars(path):
    t = []
    o = []
    h = []
    l = []
    c = []
    v = []
    with open(path, encoding="utf-8-sig", newline="") as fp:
        rd = csv.reader(fp)
        next(rd)
        for r in rd:
            t.append(int(float(r[0])))
            o.append(float(r[1]))
            h.append(float(r[2]))
            l.append(float(r[3]))
            c.append(float(r[4]))
            v.append(float(r[5]))
    return t, o, h, l, c, v


def sma(src, length):
    out = [None] * len(src)
    s = 0.0
    for i, x in enumerate(src):
        s += 0.0 if x is None else x
        if i >= length:
            old = src[i - length]
            s -= 0.0 if old is None else old
        if i >= length - 1:
            out[i] = s / length
    return out


def ema(src, length):
    out = [None] * len(src)
    a = 2.0 / (length + 1.0)
    prev = None
    for i, x in enumerate(src):
        if x is None:
            out[i] = prev
            continue
        prev = x if prev is None else a * x + (1.0 - a) * prev
        out[i] = prev
    return out


def rma(src, length):
    out = [None] * len(src)
    s = 0.0
    prev = None
    for i, x in enumerate(src):
        x = 0.0 if x is None else x
        if i < length:
            s += x
            if i == length - 1:
                prev = s / length
                out[i] = prev
        else:
            prev = (prev * (length - 1) + x) / length
            out[i] = prev
    return out


def mom(src, length):
    out = [None] * len(src)
    for i in range(length, len(src)):
        out[i] = src[i] - src[i - length]
    return out


def rolling_high(src, length):
    out = [None] * len(src)
    for i in range(len(src)):
        if i >= length - 1:
            out[i] = max(src[i - length + 1:i + 1])
    return out


def rolling_low(src, length):
    out = [None] * len(src)
    for i in range(len(src)):
        if i >= length - 1:
            out[i] = min(src[i - length + 1:i + 1])
    return out


def stoch(close, high, low, length):
    out = [None] * len(close)
    hh = rolling_high(high, length)
    ll = rolling_low(low, length)
    for i in range(len(close)):
        if hh[i] is None:
            continue
        den = hh[i] - ll[i]
        out[i] = 0.0 if den == 0 else 100.0 * (close[i] - ll[i]) / den
    return out


def rsi(close, length):
    gain = [0.0] * len(close)
    loss = [0.0] * len(close)
    for i in range(1, len(close)):
        ch = close[i] - close[i - 1]
        gain[i] = max(ch, 0.0)
        loss[i] = max(-ch, 0.0)
    ag = rma(gain, length)
    al = rma(loss, length)
    out = [None] * len(close)
    for i in range(len(close)):
        if ag[i] is None or al[i] is None:
            continue
        out[i] = 100.0 if al[i] == 0 else 100.0 - (100.0 / (1.0 + ag[i] / al[i]))
    return out


def true_range(high, low, close):
    out = [0.0] * len(close)
    for i in range(len(close)):
        if i == 0:
            out[i] = high[i] - low[i]
        else:
            out[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return out


def dmi(high, low, close, length):
    tr = true_range(high, low, close)
    plus_dm = [0.0] * len(close)
    minus_dm = [0.0] * len(close)
    for i in range(1, len(close)):
        up = high[i] - high[i - 1]
        dn = low[i - 1] - low[i]
        plus_dm[i] = up if up > dn and up > 0 else 0.0
        minus_dm[i] = dn if dn > up and dn > 0 else 0.0
    tr_r = rma(tr, length)
    p_r = rma(plus_dm, length)
    m_r = rma(minus_dm, length)
    plus = [None] * len(close)
    minus = [None] * len(close)
    dx = [None] * len(close)
    for i in range(len(close)):
        if tr_r[i] is None or tr_r[i] == 0:
            continue
        plus[i] = 100.0 * p_r[i] / tr_r[i]
        minus[i] = 100.0 * m_r[i] / tr_r[i]
        den = plus[i] + minus[i]
        dx[i] = 0.0 if den == 0 else 100.0 * abs(plus[i] - minus[i]) / den
    return plus, minus, rma(dx, length)


def sum_n(src, length):
    out = [0.0] * len(src)
    s = 0.0
    for i, x in enumerate(src):
        s += 0.0 if x is None else x
        if i >= length:
            old = src[i - length]
            s -= 0.0 if old is None else old
        out[i] = s
    return out


def psar(high, low, start, inc, max_af):
    n = len(high)
    out = [None] * n
    if n < 2:
        return out
    long = close_like_initial_long(high, low)
    sar = low[0] if long else high[0]
    ep = high[0] if long else low[0]
    af = start
    out[0] = sar
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if long:
            if i >= 2:
                sar = min(sar, low[i - 1], low[i - 2])
            else:
                sar = min(sar, low[i - 1])
            if low[i] < sar:
                long = False
                sar = ep
                ep = low[i]
                af = start
            else:
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + inc, max_af)
        else:
            if i >= 2:
                sar = max(sar, high[i - 1], high[i - 2])
            else:
                sar = max(sar, high[i - 1])
            if high[i] > sar:
                long = True
                sar = ep
                ep = high[i]
                af = start
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + inc, max_af)
        out[i] = sar
    return out


def close_like_initial_long(high, low):
    if len(high) < 2:
        return True
    return (high[1] + low[1]) >= (high[0] + low[0])


def compute_score(o, h, l, c, vol):
    macd_line = [a - b for a, b in zip(ema(c, FAST), ema(c, SLOW))]
    signal = ema(macd_line, SIG)
    k = stoch(c, h, l, STOCH_LEN)
    d = sma(k, STOCH_SIG)
    mo = mom(c, MOM_LEN)
    rs = rsi(c, RSI_LEN)
    tr = true_range(h, l, c)
    plus_di, minus_di, adx = dmi(h, l, c, DMI_LEN)

    vm_plus = [0.0] * len(c)
    vm_minus = [0.0] * len(c)
    for i in range(len(c)):
        prev_low = l[i - 1] if i > 0 else 0.0
        prev_high = h[i - 1] if i > 0 else 0.0
        vm_plus[i] = abs(h[i] - prev_low)
        vm_minus[i] = abs(l[i] - prev_high)
    vip_sum = sum_n(vm_plus, VORTEX_LEN)
    vim_sum = sum_n(vm_minus, VORTEX_LEN)
    tr_sum = sum_n(tr, VORTEX_LEN)
    vip = [0.0 if tr_sum[i] == 0 else vip_sum[i] / tr_sum[i] for i in range(len(c))]
    vim = [0.0 if tr_sum[i] == 0 else vim_sum[i] / tr_sum[i] for i in range(len(c))]

    tp = [(h[i] + l[i] + c[i]) / 3.0 for i in range(len(c))]
    raw_mf = [tp[i] * vol[i] for i in range(len(c))]
    pos_mf = [0.0] * len(c)
    neg_mf = [0.0] * len(c)
    for i in range(len(c)):
        prev_tp = tp[i - 1] if i > 0 else 0.0
        pos_mf[i] = raw_mf[i] if tp[i] > prev_tp else 0.0
        neg_mf[i] = raw_mf[i] if tp[i] < prev_tp else 0.0
    pos_sum = sum_n(pos_mf, MFI_LEN)
    neg_sum = sum_n(neg_mf, MFI_LEN)
    mfi = [100.0 if neg_sum[i] == 0 else 100.0 - (100.0 / (1.0 + pos_sum[i] / neg_sum[i])) for i in range(len(c))]

    hi = rolling_high(c, FISH_LEN)
    lo = rolling_low(c, FISH_LEN)
    fish = [None] * len(c)
    for i in range(len(c)):
        if hi[i] is None:
            continue
        vv = 0.5 if hi[i] == lo[i] else (c[i] - lo[i]) / (hi[i] - lo[i])
        vv = max(min(vv, 0.999), 0.001)
        fish[i] = 0.5 * math.log(vv / (1.0 - vv))
    fish_sig = sma(fish, FISH_SIG)
    ps = psar(h, l, PSAR_START, PSAR_INC, PSAR_MAX)

    score = [None] * len(c)
    for i in range(len(c)):
        vals = (signal[i], k[i], d[i], mo[i], rs[i], plus_di[i], minus_di[i], fish[i], fish_sig[i], ps[i])
        if any(x is None for x in vals):
            continue
        s = 0
        s += 1 if macd_line[i] > signal[i] else -1
        s += 1 if k[i] > d[i] else -1
        s += 1 if mo[i] > 0 else -1
        s += 1 if rs[i] > 50 else -1
        s += 1 if vip[i] > vim[i] else -1
        s += 1 if plus_di[i] > minus_di[i] else -1
        s += 1 if mfi[i] > 50 else -1
        s += 1 if fish[i] > fish_sig[i] else -1
        score[i] = s
    return score, rs, ps, adx


def kst_year(epoch):
    return time.strftime("%Y", time.gmtime(epoch + 9 * 3600))


def max_drawdown(equity):
    peak = equity[0]
    mdd = 0.0
    for x in equity:
        if x > peak:
            peak = x
        if peak > 0:
            d = (peak - x) / peak
            if d > mdd:
                mdd = d
    return 100.0 * mdd


def profit_factor(pnls):
    gp = sum(x for x in pnls if x > 0)
    gl = sum(-x for x in pnls if x < 0)
    if gl == 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def summarize(trades, equity, start_epoch, end_epoch):
    pnls = [t["pnl"] for t in trades]
    wins = sum(1 for x in pnls if x > 0)
    years = (end_epoch - start_epoch) / (365.25 * 86400.0)
    ending = equity[-1]
    cagr = -100.0 if ending <= 0 else 100.0 * ((ending / INITIAL_CAPITAL) ** (1.0 / years) - 1.0)
    return {
        "trades": len(trades),
        "win_rate": round(100.0 * wins / len(trades), 2) if trades else 0.0,
        "net_profit": round(sum(pnls), 3),
        "return_pct": round(100.0 * (ending / INITIAL_CAPITAL - 1.0), 3),
        "cagr": round(cagr, 3),
        "mdd": round(max_drawdown(equity), 3),
        "pf": round(profit_factor(pnls), 3) if profit_factor(pnls) != float("inf") else "inf",
        "ending_equity": round(ending, 3),
    }


def backtest(t, o, h, l, c, score, rs, ps):
    bankrupt_level = INITIAL_CAPITAL * BANKRUPT_PCT / 100.0
    is_bankrupt = False
    pos = 0
    entry_price = None
    entry_i = None
    trades = []
    equity = [INITIAL_CAPITAL]

    def close_pos(i, reason):
        nonlocal pos, entry_price, entry_i
        if pos == 0:
            return
        exit_price = o[i]
        pnl = (exit_price - entry_price) * pos * QTY - COST_PER_TRADE
        trades.append({
            "entry_epoch": t[entry_i],
            "exit_epoch": t[i],
            "direction": "LONG" if pos > 0 else "SHORT",
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "points": (exit_price - entry_price) * pos,
            "bars": i - entry_i,
            "reason": reason,
            "year": kst_year(t[entry_i]),
        })
        equity.append(equity[-1] + pnl)
        pos = 0
        entry_price = None
        entry_i = None

    def open_pos(i, direction):
        nonlocal pos, entry_price, entry_i
        pos = direction
        entry_price = o[i]
        entry_i = i

    for i in range(len(c) - 1):
        if score[i] is None or rs[i] is None or ps[i] is None:
            continue
        if not is_bankrupt and equity[-1] <= bankrupt_level:
            is_bankrupt = True
            if pos != 0:
                close_pos(i + 1, "BANKRUPT")
            continue
        long_entry = score[i] >= LONG_SCORE_TH and rs[i] < RSI_LONG_LIMIT
        short_entry = score[i] <= SHORT_SCORE_TH and rs[i] > RSI_SHORT_LIMIT
        long_exit = score[i] <= LONG_EXIT_TH or ps[i] > c[i]
        short_exit = score[i] >= SHORT_EXIT_TH or ps[i] < c[i]
        ni = i + 1

        # Pine order calls are evaluated in source order: long entry, long close,
        # short entry, short close. This approximates that sequence at next open.
        if long_entry and (not is_bankrupt) and pos <= 0:
            if pos < 0:
                close_pos(ni, "REVERSE_TO_LONG")
            open_pos(ni, 1)
        if long_exit and pos > 0:
            close_pos(ni, "LONG_EXIT")
        if short_entry and (not is_bankrupt) and pos >= 0:
            if pos > 0:
                close_pos(ni, "REVERSE_TO_SHORT")
            open_pos(ni, -1)
        if short_exit and pos < 0:
            close_pos(ni, "SHORT_EXIT")

    if pos != 0:
        # Final mark-to-close.
        fake_open = list(o)
        fake_open[-1] = c[-1]
        old_o = o[-1]
        o[-1] = c[-1]
        close_pos(len(c) - 1, "FINAL")
        o[-1] = old_o
    return trades, equity


def yearly_rows(trades):
    by = {}
    for tr in trades:
        by.setdefault(tr["year"], []).append(tr["pnl"])
    rows = []
    for y in sorted(by):
        xs = by[y]
        wins = sum(1 for x in xs if x > 0)
        rows.append({
            "year": y,
            "trades": len(xs),
            "net_profit": round(sum(xs), 3),
            "win_rate": round(100.0 * wins / len(xs), 2),
            "pf": round(profit_factor(xs), 3) if profit_factor(xs) != float("inf") else "inf",
        })
    return rows


def direction_rows(trades):
    out = {}
    for direction in ("LONG", "SHORT"):
        xs = [t["pnl"] for t in trades if t["direction"] == direction]
        wins = sum(1 for x in xs if x > 0)
        out[direction] = {
            "trades": len(xs),
            "net_profit": round(sum(xs), 3),
            "win_rate": round(100.0 * wins / len(xs), 2) if xs else 0.0,
            "pf": round(profit_factor(xs), 3) if xs and profit_factor(xs) != float("inf") else ("inf" if xs else 0.0),
            "avg_pnl": round(sum(xs) / len(xs), 6) if xs else 0.0,
        }
    return out


def main():
    out = {}
    print("V22 XAUUSD backtest, qty=1, next-open fills, cost=0")
    print("TF      bars   trades  win%    netP      ret%    CAGR%    MDD%    PF")
    for tf in ("2m", "5m", "10m"):
        path = "xauusd_%s_2010-01-01_2026-06-16.csv" % tf
        t, o, h, l, c, vol = load_bars(path)
        score, rs, ps, adx = compute_score(o, h, l, c, vol)
        trades, equity = backtest(t, o, h, l, c, score, rs, ps)
        summ = summarize(trades, equity, t[0], t[-1])
        out[tf] = {"summary": summ, "direction": direction_rows(trades), "yearly": yearly_rows(trades)}
        print("%-4s %8d %7d %6.2f %9.2f %8.3f %8.3f %7.3f %5s" % (
            tf, len(t), summ["trades"], summ["win_rate"], summ["net_profit"],
            summ["return_pct"], summ["cagr"], summ["mdd"], str(summ["pf"])
        ))
    with open("multifactor_v22_gold_summary.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)
    print("WROTE multifactor_v22_gold_summary.json")


if __name__ == "__main__":
    main()
