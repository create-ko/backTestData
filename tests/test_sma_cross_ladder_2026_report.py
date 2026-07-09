# -*- coding: utf-8 -*-
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(ROOT, "src", "scripts", "75_sma_cross_ladder_2026_report.py")

spec = importlib.util.spec_from_file_location("sma_cross_ladder_2026", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def test_format_hold_minutes():
    assert M.format_hold_minutes(5) == "5m"
    assert M.format_hold_minutes(65) == "1h 5m"
    assert M.format_hold_minutes(60 * 27 + 15) == "1d 3h 15m"


def test_svg_polyline_contains_points():
    svg = M.line_chart_svg([0.0, 10.0, 5.0], width=300, height=120)
    assert "<svg" in svg
    assert "polyline" in svg
    assert "0.0,110.0" in svg


def test_month_key_from_kst_text():
    assert M.month_key("2026-03-25 23:55") == "2026-03"


TESTS = [
    test_format_hold_minutes,
    test_svg_polyline_contains_points,
    test_month_key_from_kst_text,
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
