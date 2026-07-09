# -*- coding: utf-8 -*-
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(ROOT, "src", "scripts", "73_xauusd_session_ktr.py")

spec = importlib.util.spec_from_file_location("session_ktr", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def test_sma_uses_completed_window():
    out = M.sma([1.0, 2.0, 3.0, 4.0], 3)
    assert out == [None, None, 2.0, 3.0]


def test_asia_ktr_caps_open_gap_against_recent_daily_range():
    raw, avg10, effective = M.compute_asia_ktr(
        open_high=105.0,
        open_low=100.0,
        prev_close=90.0,
        recent_ranges=[20.0] * 10,
    )
    assert raw == 15.0
    assert avg10 == 20.0
    assert effective == 5.0


def test_asia_ktr_keeps_small_raw_value():
    raw, avg10, effective = M.compute_asia_ktr(
        open_high=101.0,
        open_low=99.0,
        prev_close=100.0,
        recent_ranges=[20.0] * 10,
    )
    assert raw == 2.0
    assert avg10 == 20.0
    assert effective == 2.0


def test_new_york_reset_handles_dst_and_standard_time():
    summer = M.local_reset_to_kst_epoch(2026, 7, 1, "America/New_York", 9, 30)
    winter = M.local_reset_to_kst_epoch(2026, 1, 2, "America/New_York", 9, 30)
    assert M.kst_hm(summer) == (22, 30)
    assert M.kst_hm(winter) == (23, 30)


def test_resolve_exit_counts_stop_first_when_same_bar_touches_both():
    bars = [
        M.Bar(0, 100.0, 101.0, 99.0, 100.0),
        M.Bar(600, 100.0, 106.0, 94.0, 101.0),
    ]
    exit_i, exit_price, reason = M.resolve_exit(
        bars=bars,
        entry_i=1,
        direction=1,
        stop=95.0,
        tp=105.0,
        force_exit_epoch=None,
    )
    assert exit_i == 1
    assert exit_price == 95.0
    assert reason == "SL"


TESTS = [
    test_sma_uses_completed_window,
    test_asia_ktr_caps_open_gap_against_recent_daily_range,
    test_asia_ktr_keeps_small_raw_value,
    test_new_york_reset_handles_dst_and_standard_time,
    test_resolve_exit_counts_stop_first_when_same_bar_touches_both,
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
