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

TESTS = [test_sma_basic, test_bollinger_population_std, test_detect_cross]

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
