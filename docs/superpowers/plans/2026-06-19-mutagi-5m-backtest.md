# 무따기 5분봉 Tip 백테스트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 골드 5분봉(및 2m·10m)에서 20/120 SMA 크로스를 추세 필터로 쓰는 3개 진입 전략(원비터치/즉시/장기이평터치)을 매수+매도 대칭으로 백테스트하고 연도별 성과 HTML 리포트를 만든다.

**Architecture:** 순수 로직은 import 가능한 `src/scripts/mutagi_engine.py`(stdlib만)에 모아 단위 테스트로 검증하고, 숫자 접두 러너 `60_*`(트레이드 CSV 생성)·`61_*`(연도별 HTML)은 I/O만 담당하는 얇은 래퍼로 둔다. 진입은 항상 트리거 봉마감 다음 봉 시가, 청산은 반대 크로스 다음 봉 시가 → 미래참조 없음.

**Tech Stack:** Python 3 표준 라이브러리만 (csv, math, datetime, collections). 테스트 프레임워크 없이 stdlib `assert` 기반 테스트 파일(`python tests/test_mutagi_engine.py`로 실행). 콘솔 출력은 ASCII만(cp949).

**근거 스펙:** `docs/superpowers/specs/2026-06-19-mutagi-5m-backtest-design.md`

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/scripts/mutagi_engine.py` | 순수 분석 라이브러리: SMA, 볼린저(모표준편차), 크로스 탐지, 지표 묶음, 트리거 판정, 트레이드 생성, 연도별 집계·PF·MDD. import 가능(숫자 접두 없음). |
| `src/scripts/60_mutagi_5m_signals.py` | 러너: `data/`의 `xauusd_{2m,5m,10m}_...csv` 로드 → 엔진으로 3전략×2방향 트레이드 생성 → `mutagi_trades_{tf}.csv` 출력. |
| `src/scripts/61_mutagi_report.py` | 러너: `mutagi_trades_{tf}.csv` 로드 → 엔진 집계 함수로 연도별 통계 → `result/mutagi_5m_report.html` 생성. |
| `tests/test_mutagi_engine.py` | 엔진 순수 함수 단위 테스트(합성 데이터). stdlib assert. |

엔진은 `compute_indicators(bars, sma_fast=20, sma_slow=120, bb_len=4, bb_mult=4.0)` 처럼 길이를 파라미터로 받아, 테스트에서는 짧은 길이로 합성 바를 써서 검증한다(실데이터 120봉 불필요).

공통 자료형:
```python
from collections import namedtuple
Bar = namedtuple("Bar", "epoch open high low close")   # epoch=UTC seconds(int)
# Indicators: dict {"sma_fast":[...], "sma_slow":[...], "up":[...], "lo":[...], "cross":[...]}
#   cross[i] in {"golden","dead",None}
```

트레이드 dict 키(= CSV 컬럼 순서):
`strategy, direction, tf, entry_dt_kst, entry_epoch, exit_dt_kst, entry_price, exit_price, points_gross, points_net, pct_gross, pct_net, hold_bars, year, open_at_end`

KST = UTC+9. 연도는 `entry_dt_kst` 기준.

---

## Task 1: 프로젝트 스캐폴드 + SMA

**Files:**
- Create: `src/scripts/mutagi_engine.py`
- Test: `tests/test_mutagi_engine.py`

- [ ] **Step 1: Write the failing test**

`tests/test_mutagi_engine.py`:
```python
# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "scripts"))
import mutagi_engine as M

def test_sma_basic():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = M.sma(vals, 3)
    assert out[0] is None and out[1] is None
    assert abs(out[2] - 2.0) < 1e-9   # (1+2+3)/3
    assert abs(out[3] - 3.0) < 1e-9
    assert abs(out[4] - 4.0) < 1e-9

TESTS = [test_sma_basic]

def run():
    failed = 0
    for t in TESTS:
        try:
            t(); print("PASS", t.__name__)
        except Exception as e:
            failed += 1; print("FAIL", t.__name__, repr(e))
    print("ALL PASS" if failed == 0 else "FAILED %d" % failed)
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_mutagi_engine.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mutagi_engine'` (or AttributeError).

- [ ] **Step 3: Write minimal implementation**

`src/scripts/mutagi_engine.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_mutagi_engine.py`
Expected: `PASS test_sma_basic` then `ALL PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/scripts/mutagi_engine.py tests/test_mutagi_engine.py
git commit -m "feat(mutagi): SMA helper + test scaffold"
```

---

## Task 2: 볼린저밴드 (모표준편차 ÷N)

**Files:**
- Modify: `src/scripts/mutagi_engine.py`
- Test: `tests/test_mutagi_engine.py`

- [ ] **Step 1: Write the failing test**

`test_mutagi_engine.py`에 추가하고 `TESTS` 리스트에 등록:
```python
def test_bollinger_population_std():
    # opens = [10,12,14,16], length=4, mult=2
    # mean=13, var=(9+1+1+9)/4=5, std=sqrt(5)=2.2360679...
    up, lo = M.bollinger([10.0, 12.0, 14.0, 16.0], 4, 2.0)
    assert up[0] is None and up[2] is None     # not enough bars until i=3
    assert abs(up[3] - (13.0 + 2 * math.sqrt(5))) < 1e-9
    assert abs(lo[3] - (13.0 - 2 * math.sqrt(5))) < 1e-9
```
파일 상단에 `import math` 추가(테스트용).

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_mutagi_engine.py`
Expected: FAIL — `AttributeError: module 'mutagi_engine' has no attribute 'bollinger'`.

- [ ] **Step 3: Write minimal implementation**

`mutagi_engine.py`에 추가:
```python
def bollinger(values, length, mult):
    """모표준편차(÷N). returns (upper, lower) — 각 list[Optional[float]]."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_mutagi_engine.py`
Expected: `PASS test_bollinger_population_std`, `ALL PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/scripts/mutagi_engine.py tests/test_mutagi_engine.py
git commit -m "feat(mutagi): Bollinger bands (population std)"
```

---

## Task 3: 크로스 탐지

**Files:**
- Modify: `src/scripts/mutagi_engine.py`
- Test: `tests/test_mutagi_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_detect_cross():
    fast = [None, 1.0, 3.0, 2.0, 0.5]
    slow = [None, 2.0, 2.0, 2.0, 2.0]
    # i=2: fast 3>2 and prev 1<=2 -> golden
    # i=3: fast 2<2? no (equal) -> None
    # i=4: fast 0.5<2 and prev 2>=2 -> dead
    cr = M.detect_cross(fast, slow)
    assert cr[1] is None
    assert cr[2] == "golden"
    assert cr[3] is None
    assert cr[4] == "dead"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_mutagi_engine.py`
Expected: FAIL — no attribute `detect_cross`.

- [ ] **Step 3: Write minimal implementation**

```python
def detect_cross(fast, slow):
    """각 i에 'golden'/'dead'/None. 직전·현재 둘 다 값이 있어야 판정."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_mutagi_engine.py`
Expected: `PASS test_detect_cross`, `ALL PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/scripts/mutagi_engine.py tests/test_mutagi_engine.py
git commit -m "feat(mutagi): golden/dead cross detection"
```

---

## Task 4: 지표 묶음 compute_indicators

**Files:**
- Modify: `src/scripts/mutagi_engine.py`
- Test: `tests/test_mutagi_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_compute_indicators_shapes():
    bars = [M.Bar(i * 300, 10.0 + i, 11.0 + i, 9.0 + i, 10.0 + i) for i in range(10)]
    ind = M.compute_indicators(bars, sma_fast=2, sma_slow=4, bb_len=3, bb_mult=2.0)
    assert set(ind.keys()) == {"sma_fast", "sma_slow", "up", "lo", "cross"}
    assert len(ind["sma_fast"]) == 10
    assert ind["sma_fast"][0] is None
    assert ind["sma_fast"][1] is not None      # length 2 -> valid from i=1
    assert ind["sma_slow"][3] is not None       # length 4 -> valid from i=3
    assert ind["up"][2] is not None             # bb_len 3 -> valid from i=2
    assert len(ind["cross"]) == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_mutagi_engine.py`
Expected: FAIL — no attribute `compute_indicators`.

- [ ] **Step 3: Write minimal implementation**

```python
def compute_indicators(bars, sma_fast=20, sma_slow=120, bb_len=4, bb_mult=4.0):
    closes = [b.close for b in bars]
    opens = [b.open for b in bars]
    f = sma(closes, sma_fast)
    s = sma(closes, sma_slow)
    up, lo = bollinger(opens, bb_len, bb_mult)
    cross = detect_cross(f, s)
    return {"sma_fast": f, "sma_slow": s, "up": up, "lo": lo, "cross": cross}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_mutagi_engine.py`
Expected: `PASS test_compute_indicators_shapes`, `ALL PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/scripts/mutagi_engine.py tests/test_mutagi_engine.py
git commit -m "feat(mutagi): compute_indicators bundle"
```

---

## Task 5: 트리거 판정 is_trigger

**Files:**
- Modify: `src/scripts/mutagi_engine.py`
- Test: `tests/test_mutagi_engine.py`

규칙(스펙 §3): 비교는 `<=`/`>=`. S2는 항상 트리거(armed 첫 봉=크로스 봉에서 발동→다음봉 시가).
- S1 LONG: `lo[i] is not None and bars[i].low <= lo[i]` / SHORT: `up[i] is not None and bars[i].high >= up[i]`
- S2: 항상 True
- S3 LONG: `sma_slow[i] is not None and bars[i].low <= sma_slow[i]` / SHORT: `sma_slow[i] is not None and bars[i].high >= sma_slow[i]`

- [ ] **Step 1: Write the failing test**

```python
def _ind_for_trigger():
    # 5 bars; index 3 will be the trigger test bar
    bars = [
        M.Bar(0, 10, 11, 9, 10),
        M.Bar(300, 10, 11, 9, 10),
        M.Bar(600, 10, 11, 9, 10),
        M.Bar(900, 10, 11, 8, 10),   # low=8, high=11
        M.Bar(1200, 10, 11, 9, 10),
    ]
    ind = {
        "sma_fast": [None] * 5, "sma_slow": [None, None, None, 8.5, 8.5],
        "up": [None, None, None, 10.5, 10.5], "lo": [None, None, None, 8.2, 8.2],
        "cross": [None] * 5,
    }
    return bars, ind

def test_is_trigger():
    bars, ind = _ind_for_trigger()
    # S1 LONG at i=3: low 8 <= lo 8.2 -> True
    assert M.is_trigger("S1", "LONG", 3, bars, ind) is True
    # S1 SHORT at i=3: high 11 >= up 10.5 -> True
    assert M.is_trigger("S1", "SHORT", 3, bars, ind) is True
    # S2 always True
    assert M.is_trigger("S2", "LONG", 3, bars, ind) is True
    # S3 LONG at i=3: low 8 <= sma_slow 8.5 -> True
    assert M.is_trigger("S3", "LONG", 3, bars, ind) is True
    # S3 LONG at i=2: sma_slow None -> False
    assert M.is_trigger("S3", "LONG", 2, bars, ind) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_mutagi_engine.py`
Expected: FAIL — no attribute `is_trigger`.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_mutagi_engine.py`
Expected: `PASS test_is_trigger`, `ALL PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/scripts/mutagi_engine.py tests/test_mutagi_engine.py
git commit -m "feat(mutagi): is_trigger for S1/S2/S3 long+short"
```

---

## Task 6: 트레이드 생성 generate_trades (상태기계)

**Files:**
- Modify: `src/scripts/mutagi_engine.py`
- Test: `tests/test_mutagi_engine.py`

알고리즘(LONG; SHORT는 entry_cross/exit_cross만 뒤집음):
- `entry_cross = "golden" if LONG else "dead"`, `exit_cross = "dead" if LONG else "golden"`
- 상태: `position`(열린 트레이드 dict 또는 None), `armed`(entry_cross 본 뒤 트리거 대기).
- 각 i에서 순서:
  1. position 있고 `cross[i] == exit_cross` → 다음 봉 시가 청산(`opens[i+1]`). 없으면(끝) `closes[i]`로 청산 + `open_at_end=True`. 트레이드 기록, position=None, armed=False.
  2. `cross[i] == exit_cross` → armed=False (반대 국면 진입).
  3. `cross[i] == entry_cross` → armed=True (새 국면 시작; 같은 i에서 트리거 검사 가능).
  4. armed이고 position 없으면 `is_trigger(...)` 검사 → True & `i+1 < n` 이면 `opens[i+1]`에 진입(position 설정), armed=False(1국면 1진입).
- 루프 종료 후 position이 남아 있으면 마지막 종가로 청산 + `open_at_end=True`.
- 손익: LONG gross=`exit-entry`, SHORT gross=`entry-exit`; `net=gross-cost`; `pct=val/entry*100`; `hold_bars=exit_idx-entry_idx`; `year`=entry KST 연도.

- [ ] **Step 1: Write the failing test**

```python
def _bars(prices_ohlc, step=300):
    # prices_ohlc: list of (o,h,l,c)
    return [M.Bar(i * step, o, h, l, c) for i, (o, h, l, c) in enumerate(prices_ohlc)]

def test_generate_trades_s2_long_basic():
    # 6 bars. golden at i=1, dead at i=4. S2 LONG enters open[2], exits open[5].
    bars = _bars([(100, 100, 100, 100)] * 6)
    bars[2] = M.Bar(600, 110, 110, 110, 110)   # entry open = 110
    bars[5] = M.Bar(1500, 130, 130, 130, 130)  # exit open = 130
    ind = {
        "sma_fast": [None] * 6, "sma_slow": [None] * 6,
        "up": [None] * 6, "lo": [None] * 6,
        "cross": [None, "golden", None, None, "dead", None],
    }
    tr = M.generate_trades(bars, ind, "S2", "LONG", cost=0.4, tf="5m")
    assert len(tr) == 1
    t = tr[0]
    assert abs(t["entry_price"] - 110) < 1e-9
    assert abs(t["exit_price"] - 130) < 1e-9
    assert abs(t["points_gross"] - 20) < 1e-9
    assert abs(t["points_net"] - 19.6) < 1e-9
    assert t["hold_bars"] == 3
    assert t["direction"] == "LONG" and t["strategy"] == "S2" and t["tf"] == "5m"
    assert t["open_at_end"] is False

def test_generate_trades_short_and_open_at_end():
    # SHORT: entry_cross=dead at i=1, no golden after -> open_at_end close at last close.
    bars = _bars([(100, 100, 100, 100)] * 4)
    bars[2] = M.Bar(600, 120, 120, 120, 120)    # entry open = 120
    bars[3] = M.Bar(900, 90, 90, 90, 90)        # last close = 90
    ind = {
        "sma_fast": [None] * 4, "sma_slow": [None] * 4,
        "up": [None] * 4, "lo": [None] * 4,
        "cross": [None, "dead", None, None],
    }
    tr = M.generate_trades(bars, ind, "S2", "SHORT", cost=0.4, tf="5m")
    assert len(tr) == 1
    t = tr[0]
    assert abs(t["entry_price"] - 120) < 1e-9
    assert abs(t["exit_price"] - 90) < 1e-9
    assert abs(t["points_gross"] - 30) < 1e-9   # short: entry - exit = 120-90
    assert t["open_at_end"] is True

def test_generate_trades_one_entry_per_regime():
    # S1 LONG: golden at i=1; two qualifying touch bars (i=1,i=2) but only first enters.
    bars = _bars([(100, 100, 100, 100)] * 6)
    ind = {
        "sma_fast": [None] * 6, "sma_slow": [None] * 6,
        "up": [None] * 6,
        "lo": [None, 100, 100, 100, None, None],   # low(100) <= lo(100) at i=1,2,3
        "cross": [None, "golden", None, None, "dead", None],
    }
    tr = M.generate_trades(bars, ind, "S1", "LONG", cost=0.4, tf="5m")
    assert len(tr) == 1
    # trigger at i=1 -> entry open[2]; exit dead at i=4 -> open[5]
    assert tr[0]["hold_bars"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_mutagi_engine.py`
Expected: FAIL — no attribute `generate_trades`.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_mutagi_engine.py`
Expected: `PASS` for all three new tests, `ALL PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/scripts/mutagi_engine.py tests/test_mutagi_engine.py
git commit -m "feat(mutagi): generate_trades state machine"
```

---

## Task 7: 연도별 집계 aggregate_by_year + PF/MDD

**Files:**
- Modify: `src/scripts/mutagi_engine.py`
- Test: `tests/test_mutagi_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_profit_factor_and_mdd():
    assert abs(M.profit_factor([3.0, -1.0, 2.0]) - 5.0) < 1e-9   # 5 / 1
    assert M.profit_factor([1.0, 2.0]) == float("inf")          # no losses
    # cumulative net curve drawdown
    assert abs(M.max_drawdown([2.0, -5.0, 1.0]) - 5.0) < 1e-9   # peak 2 -> -3, dd=5

def test_aggregate_by_year():
    trades = [
        {"year": 2011, "points_net": 2.0, "pct_net": 1.0, "hold_bars": 4, "open_at_end": False},
        {"year": 2011, "points_net": -1.0, "pct_net": -0.5, "hold_bars": 2, "open_at_end": False},
        {"year": 2012, "points_net": 3.0, "pct_net": 1.5, "hold_bars": 6, "open_at_end": True},
    ]
    agg = M.aggregate_by_year(trades)
    assert agg[2011]["trades"] == 2
    assert abs(agg[2011]["win_rate"] - 50.0) < 1e-9
    assert abs(agg[2011]["total_points"] - 1.0) < 1e-9
    assert abs(agg[2011]["pf"] - 2.0) < 1e-9       # 2 / 1
    assert agg[2012]["trades"] == 1
    assert "ALL" in agg and agg["ALL"]["trades"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_mutagi_engine.py`
Expected: FAIL — no attribute `profit_factor`.

- [ ] **Step 3: Write minimal implementation**

```python
def profit_factor(points):
    gains = sum(p for p in points if p > 0)
    losses = sum(-p for p in points if p < 0)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def max_drawdown(points):
    """누적합 곡선의 최대낙폭(양수)."""
    cum = 0.0; peak = 0.0; mdd = 0.0
    for p in points:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > mdd:
            mdd = dd
    return mdd


def aggregate_by_year(trades):
    from collections import defaultdict
    buckets = defaultdict(list)
    for t in trades:
        buckets[t["year"]].append(t)
        buckets["ALL"].append(t)

    def summarize(ts):
        pts = [t["points_net"] for t in ts]
        pcts = [t["pct_net"] for t in ts]
        holds = [t["hold_bars"] for t in ts]
        wins = sum(1 for p in pts if p > 0)
        nt = len(ts)
        return {
            "trades": nt,
            "win_rate": 100.0 * wins / nt if nt else 0.0,
            "total_points": sum(pts),
            "avg_points": sum(pts) / nt if nt else 0.0,
            "total_pct": sum(pcts),
            "avg_pct": sum(pcts) / nt if nt else 0.0,
            "pf": profit_factor(pts),
            "mdd": max_drawdown(pts),
            "avg_hold": sum(holds) / nt if nt else 0.0,
        }

    return {k: summarize(v) for k, v in buckets.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_mutagi_engine.py`
Expected: `PASS` both, `ALL PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/scripts/mutagi_engine.py tests/test_mutagi_engine.py
git commit -m "feat(mutagi): aggregate_by_year + PF/MDD"
```

---

## Task 8: 러너 60 — 트레이드 CSV 생성

**Files:**
- Create: `src/scripts/60_mutagi_5m_signals.py`

CSV 로더: 헤더 `time,open,high,low,close,volume` 건너뛰고 `Bar(int(time), open, high, low, close)` 생성. `encoding="utf-8-sig"`.
3전략 × 2방향 모든 조합을 각 TF에 대해 생성, `mutagi_trades_{tf}.csv` 출력.

- [ ] **Step 1: Write the runner (no unit test; verified by smoke run on real data)**

`src/scripts/60_mutagi_5m_signals.py`:
```python
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
```

- [ ] **Step 2: Smoke run on real data**

Run: `cd data && python ../src/scripts/60_mutagi_5m_signals.py`
Expected: 각 TF×전략×방향별 트레이드 수가 출력되고(>0), `mutagi_trades_{2m,5m,10m}.csv` 3개 생성. S2가 가장 많고(크로스마다 진입), S1/S3은 그보다 적어야 함(트리거 미발동 국면 존재).

- [ ] **Step 3: Sanity check output**

Run: `cd data && python -c "import csv; r=list(csv.reader(open('mutagi_trades_5m.csv',encoding='utf-8-sig'))); print(r[0]); print(len(r)-1,'rows'); print(r[1])"`
Expected: 헤더가 `COLS`와 일치, 행 수 > 0, 첫 행의 entry/exit 가격이 골드 가격대(수백~수천)임.

- [ ] **Step 4: Commit**

```bash
git add src/scripts/60_mutagi_5m_signals.py
git commit -m "feat(mutagi): runner 60 - generate trades CSV per TF"
```

---

## Task 9: 러너 61 — 연도별 HTML 리포트

**Files:**
- Create: `src/scripts/61_mutagi_report.py`

`mutagi_trades_{tf}.csv` 로드 → `M.aggregate_by_year`로 전략×TF×방향별 연도 통계 → `result/mutagi_5m_report.html` 생성(데이터 인라인, 자기완결). HTML은 UTF-8이라 기호 자유. 콘솔 print는 ASCII만.

- [ ] **Step 1: Write the runner**

`src/scripts/61_mutagi_report.py`:
```python
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
                agg = M.aggregate_by_year(sub) if sub else {"ALL": {
                    "trades": 0, "win_rate": 0, "total_points": 0, "avg_points": 0,
                    "total_pct": 0, "avg_pct": 0, "pf": 0, "mdd": 0, "avg_hold": 0}}
                title = "%s / %s / %s" % (tf, STRAT_LABEL[strat], "매수" if d == "LONG" else "매도")
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
```

- [ ] **Step 2: Run the report**

Run: `cd data && python ../src/scripts/61_mutagi_report.py`
Expected: `wrote ..\result\mutagi_5m_report.html`. 에러 없음(UnicodeEncodeError 없어야 함 — 콘솔 print는 ASCII만).

- [ ] **Step 3: Verify HTML**

Run: `python -c "s=open('result/mutagi_5m_report.html',encoding='utf-8').read(); print(len(s),'chars'); print('S1 원비터치' in s, '전체' in s)"`
Expected: chars > 1000, 두 `True`. (수동으로 브라우저 확인 권장: 18개 섹션 = 3전략×3TF×2방향, 각 연도 표 2010~2026 행 존재.)

- [ ] **Step 4: Commit**

```bash
git add src/scripts/61_mutagi_report.py
git commit -m "feat(mutagi): runner 61 - year-by-year HTML report"
```

---

## Task 10: 전체 회귀 + 문서 갱신

**Files:**
- Modify: `CLAUDE.md` (파일 맵에 무따기 파이프라인 한 줄 추가)

- [ ] **Step 1: Run full test suite**

Run: `python tests/test_mutagi_engine.py`
Expected: `ALL PASS`.

- [ ] **Step 2: Run full pipeline end-to-end**

Run:
```
cd data && python ../src/scripts/60_mutagi_5m_signals.py
cd data && python ../src/scripts/61_mutagi_report.py
```
Expected: 트레이드 CSV 3개 + `result/mutagi_5m_report.html` 생성, 에러 없음.

- [ ] **Step 3: Update CLAUDE.md 파일 맵**

`CLAUDE.md`의 파일 맵 섹션에 추가(기존 문장 보존, 한 항목 추가):
```
  - 무따기 5분봉 Tip(별도 전략): `mutagi_engine.py`(순수 로직) + `60_mutagi_5m_signals.py`(트레이드 CSV) + `61_mutagi_report.py`(연도별 HTML). 골드 단독, 3전략(원비터치/즉시/장기이평터치) x 2m,5m,10m x 매수/매도, 데드/골든 크로스 청산, 비용 0.4. 테스트: `python tests/test_mutagi_engine.py`. 산출물 `result/mutagi_5m_report.html`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add mutagi 5m pipeline to CLAUDE.md file map"
```

---

## Self-Review 체크

- **Spec coverage:** 공통정의(Task1-4)·3전략 트리거(Task5)·진입/청산/손익(Task6)·연도집계(Task7)·트레이드CSV(Task8)·연도별HTML(Task9)·문서/회귀(Task10) — 스펙 §2~§5 전부 매핑됨. 2m·5m·10m 모두 처리(규칙#2), 매수+매도 대칭, 비용 0.4 net+gross, `<=` 비교, 다음봉 시가 진입/청산, open_at_end 처리 포함.
- **Placeholder scan:** 모든 코드 스텝에 실제 코드 포함, TBD/TODO 없음.
- **Type consistency:** `Bar`(namedtuple), Indicators dict 키(`sma_fast/sma_slow/up/lo/cross`), 트레이드 dict 키(`COLS`)가 Task 전반에서 일관. `is_trigger`/`generate_trades`/`aggregate_by_year` 시그니처가 호출부(러너)와 일치.
