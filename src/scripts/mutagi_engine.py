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
