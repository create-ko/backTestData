#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""무따기 5분봉 Tip 백테스트 순수 로직 (stdlib only)."""
import math
from collections import namedtuple
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
Bar = namedtuple("Bar", "epoch open high low close")


def sma(values, length):
    n = len(values); out = [None] * n; s = 0.0
    for i in range(n):
        s += values[i]
        if i >= length:
            s -= values[i - length]
        if i >= length - 1:
            out[i] = s / length
    return out


def bollinger(values, length, mult):
    """모표준편차(/N). returns (upper, lower) - 각 list[Optional[float]]."""
    n = len(values); up = [None] * n; lo = [None] * n
    s = ss = 0.0
    for i in range(n):
        v = values[i]; s += v; ss += v * v
        if i >= length:
            r = values[i - length]; s -= r; ss -= r * r
        if i >= length - 1:
            mean = s / length
            var = ss / length - mean * mean
            if var < 0:
                var = 0.0
            dev = mult * math.sqrt(var)
            up[i] = mean + dev; lo[i] = mean - dev
    return up, lo


def detect_cross(fast, slow):
    """각 i에 'golden'/'dead'/None. 직전/현재 둘 다 값이 있어야 판정."""
    n = len(fast); out = [None] * n
    for i in range(1, n):
        a0, a1 = fast[i - 1], fast[i]
        b0, b1 = slow[i - 1], slow[i]
        if None in (a0, a1, b0, b1):
            continue
        if a1 > b1 and a0 <= b0:
            out[i] = "golden"
        elif a1 < b1 and a0 >= b0:
            out[i] = "dead"
    return out


def compute_indicators(bars, sma_fast=20, sma_slow=120, bb_len=4, bb_mult=4.0):
    closes = [b.close for b in bars]
    opens = [b.open for b in bars]
    f = sma(closes, sma_fast)
    s = sma(closes, sma_slow)
    up, lo = bollinger(opens, bb_len, bb_mult)
    cross = detect_cross(f, s)
    return {"sma_fast": f, "sma_slow": s, "up": up, "lo": lo, "cross": cross}


def is_trigger(strategy, direction, i, bars, ind):
    if strategy == "S2":
        return True
    b = bars[i]
    if strategy == "S1":
        band = ind["lo"][i] if direction == "LONG" else ind["up"][i]
    elif strategy == "S3":
        band = ind["sma_slow"][i]
    else:
        raise ValueError("unknown strategy: %s" % strategy)
    if band is None:
        return False
    return b.low <= band if direction == "LONG" else b.high >= band


def generate_trades(bars, ind, strategy, direction, cost=0.4, tf=""):
    n = len(bars)
    opens = [b.open for b in bars]
    closes = [b.close for b in bars]
    cross = ind["cross"]
    entry_cross = "golden" if direction == "LONG" else "dead"
    exit_cross = "dead" if direction == "LONG" else "golden"
    trades = []
    position = None   # dict: entry_idx, entry_price
    armed = False

    def _close(entry, exit_idx, exit_price, open_at_end):
        ep = entry["entry_price"]
        if direction == "LONG":
            gross = exit_price - ep
        else:
            gross = ep - exit_price
        net = gross - cost
        edt = datetime.fromtimestamp(bars[entry["entry_idx"]].epoch, KST)
        xdt = datetime.fromtimestamp(bars[exit_idx].epoch, KST)
        trades.append({
            "strategy": strategy, "direction": direction, "tf": tf,
            "entry_dt_kst": edt.strftime("%Y-%m-%d %H:%M"),
            "entry_epoch": bars[entry["entry_idx"]].epoch,
            "exit_dt_kst": xdt.strftime("%Y-%m-%d %H:%M"),
            "entry_price": ep, "exit_price": exit_price,
            "points_gross": gross, "points_net": net,
            "pct_gross": gross / ep * 100.0, "pct_net": net / ep * 100.0,
            "hold_bars": exit_idx - entry["entry_idx"],
            "year": edt.year, "open_at_end": open_at_end,
        })

    for i in range(n):
        if position is not None and cross[i] == exit_cross:
            if i + 1 < n:
                _close(position, i + 1, opens[i + 1], False)
            else:
                _close(position, i, closes[i], True)
            position = None; armed = False
            continue
        if cross[i] == exit_cross:
            armed = False
        if cross[i] == entry_cross:
            armed = True
        if armed and position is None and i + 1 < n:
            if is_trigger(strategy, direction, i, bars, ind):
                position = {"entry_idx": i + 1, "entry_price": opens[i + 1]}
                armed = False
    if position is not None:
        _close(position, n - 1, closes[n - 1], True)
    return trades
