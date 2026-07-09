# -*- coding: utf-8 -*-
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(ROOT, "src", "scripts", "76_sma_cross_ladder_2026_charts.py")

spec = importlib.util.spec_from_file_location("sma_cross_ladder_charts", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def test_marker_line_svg_contains_labels():
    svg = M.marker_line_svg(
        values=[100.0, 101.0, 102.0],
        sma20=[None, 100.5, 101.5],
        sma120=[None, 99.5, 100.5],
        markers=[{"idx": 1, "label": "ENTRY", "color": "#0f8f63"}],
        levels=[{"price": 100.0, "label": "AVG", "color": "#344054"}],
        width=300,
        height=180,
    )
    assert "<svg" in svg
    assert "ENTRY" in svg
    assert "AVG" in svg
    assert "polyline" in svg


TESTS = [test_marker_line_svg_contains_labels]


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
