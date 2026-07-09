# -*- coding: utf-8 -*-
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(ROOT, "src", "scripts", "74_sma_cross_ladder.py")

spec = importlib.util.spec_from_file_location("sma_cross_ladder", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def test_detect_crosses():
    fast = [None, 1.0, 2.0, 3.0, 1.0]
    slow = [None, 2.0, 2.0, 2.0, 2.0]
    crosses = M.detect_crosses(fast, slow)
    assert crosses == [None, None, None, "golden", "dead"]


def test_average_entry_after_ladder_fills_long():
    prices = M.ladder_prices(100.0, 1, 10.0, 5)
    assert prices == [100.0, 90.0, 80.0, 70.0, 60.0]
    assert M.average_price(prices) == 80.0


def test_trailing_stop_from_average_price_long():
    assert M.trailing_stop(avg_price=100.0, direction=1, best_price=109.9) is None
    assert M.trailing_stop(avg_price=100.0, direction=1, best_price=110.0) == 105.0
    assert M.trailing_stop(avg_price=100.0, direction=1, best_price=114.9) == 105.0
    assert M.trailing_stop(avg_price=100.0, direction=1, best_price=115.0) == 110.0


def test_trailing_stop_from_average_price_short():
    assert M.trailing_stop(avg_price=100.0, direction=-1, best_price=90.1) is None
    assert M.trailing_stop(avg_price=100.0, direction=-1, best_price=90.0) == 95.0
    assert M.trailing_stop(avg_price=100.0, direction=-1, best_price=85.0) == 90.0


def test_sixth_zone_stop_long():
    assert M.hard_stop_price(100.0, 1, 10.0, 5) == 50.0
    assert M.hard_stop_price(100.0, -1, 10.0, 5) == 150.0


TESTS = [
    test_detect_crosses,
    test_average_entry_after_ladder_fills_long,
    test_trailing_stop_from_average_price_long,
    test_trailing_stop_from_average_price_short,
    test_sixth_zone_stop_long,
]


def run():
    failed = 0
    for test in TESTS:
        try:
            test()
            print("PASS", test.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL", test.__name__, repr(exc))
    print("ALL PASS" if failed == 0 else "FAILED %d" % failed)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    run()
