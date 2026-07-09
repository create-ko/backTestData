# -*- coding: utf-8 -*-
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(ROOT, "src", "scripts", "77_sma_cross_ladder_2026_interactive.py")

spec = importlib.util.spec_from_file_location("interactive_charts", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def test_bollinger_population_std():
    up, mid, lo = M.bollinger([10.0, 12.0, 14.0, 16.0], 4, 2.0)
    assert up[0] is None
    assert mid[3] == 13.0
    assert round(up[3], 6) == round(13.0 + 2.0 * (5.0 ** 0.5), 6)
    assert round(lo[3], 6) == round(13.0 - 2.0 * (5.0 ** 0.5), 6)


def test_trade_option_label_contains_time_and_result():
    trade = {
        "entry_kst": "2026-03-25 23:55",
        "exit_kst": "2026-03-26 00:20",
        "direction": "LONG",
        "legs": "5",
        "net_points": "73.0",
    }
    label = M.trade_option_label(7, trade)
    assert "#007" in label
    assert "2026-03-25 23:55" in label
    assert "LONG" in label
    assert "legs 5" in label


def test_html_shell_has_dropdown_and_canvas_mount():
    html = M.html_shell([], [], {"trades": 0})
    assert "<select id=\"tradeSelect\"" in html
    assert "chartFrame" in html
    assert "renderTrade" in html


TESTS = [
    test_bollinger_population_std,
    test_trade_option_label_contains_time_and_result,
    test_html_shell_has_dropdown_and_canvas_mount,
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
