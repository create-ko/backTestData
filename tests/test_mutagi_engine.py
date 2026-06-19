# -*- coding: utf-8 -*-
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "scripts"))
import mutagi_engine as M

def test_sma_basic():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = M.sma(vals, 3)
    assert out[0] is None and out[1] is None
    assert abs(out[2] - 2.0) < 1e-9   # (1+2+3)/3
    assert abs(out[3] - 3.0) < 1e-9
    assert abs(out[4] - 4.0) < 1e-9

def test_bollinger_population_std():
    # opens = [10,12,14,16], length=4, mult=2
    # mean=13, var=(9+1+1+9)/4=5, std=sqrt(5)
    up, lo = M.bollinger([10.0, 12.0, 14.0, 16.0], 4, 2.0)
    assert up[0] is None and up[2] is None
    assert abs(up[3] - (13.0 + 2 * math.sqrt(5))) < 1e-9
    assert abs(lo[3] - (13.0 - 2 * math.sqrt(5))) < 1e-9

def test_detect_cross():
    fast = [None, 1.0, 3.0, 2.0, 0.5]
    slow = [None, 2.0, 2.0, 2.0, 2.0]
    # i=2: 3>2 & prev 1<=2 -> golden; i=3: 2<2? no -> None; i=4: 0.5<2 & prev 2>=2 -> dead
    cr = M.detect_cross(fast, slow)
    assert cr[1] is None
    assert cr[2] == "golden"
    assert cr[3] is None
    assert cr[4] == "dead"

def test_compute_indicators_shapes():
    bars = [M.Bar(i * 300, 10.0 + i, 11.0 + i, 9.0 + i, 10.0 + i) for i in range(10)]
    ind = M.compute_indicators(bars, sma_fast=2, sma_slow=4, bb_len=3, bb_mult=2.0)
    assert set(ind.keys()) == {"sma_fast", "sma_slow", "up", "lo", "cross"}
    assert len(ind["sma_fast"]) == 10
    assert ind["sma_fast"][0] is None
    assert ind["sma_fast"][1] is not None
    assert ind["sma_slow"][3] is not None
    assert ind["up"][2] is not None
    assert len(ind["cross"]) == 10

def _ind_for_trigger():
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
    assert M.is_trigger("S1", "LONG", 3, bars, ind) is True    # low 8 <= lo 8.2
    assert M.is_trigger("S1", "SHORT", 3, bars, ind) is True   # high 11 >= up 10.5
    assert M.is_trigger("S2", "LONG", 3, bars, ind) is True    # always
    assert M.is_trigger("S3", "LONG", 3, bars, ind) is True    # low 8 <= sma_slow 8.5
    assert M.is_trigger("S3", "LONG", 2, bars, ind) is False   # sma_slow None

TESTS = [test_sma_basic, test_bollinger_population_std, test_detect_cross,
         test_compute_indicators_shapes, test_is_trigger]

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
