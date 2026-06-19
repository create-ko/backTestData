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
