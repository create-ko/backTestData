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
