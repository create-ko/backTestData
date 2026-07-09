# -*- coding: utf-8 -*-
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(ROOT, "src", "scripts", "83_session_open_retest_5m.py")

spec = importlib.util.spec_from_file_location("session_open_retest_5m", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def bar(epoch, open_, high, low, close):
    return M.Bar(epoch, open_, high, low, close)


def test_bullish_first_bar_creates_long_setup():
    first = bar(1000, 3000, 3012, 2998, 3010)
    setup = M.setup_from_first_bar(first)
    assert setup["direction"] == 1
    assert setup["level"] == 3010
    assert setup["stop"] == 3005


def test_bearish_first_bar_creates_short_setup():
    first = bar(1000, 3010, 3012, 2998, 3000)
    setup = M.setup_from_first_bar(first)
    assert setup["direction"] == -1
    assert setup["level"] == 3000
    assert setup["stop"] == 3005


def test_doji_first_bar_has_no_setup():
    first = bar(1000, 3000, 3005, 2995, 3000)
    assert M.setup_from_first_bar(first) is None


def test_long_retest_requires_touch_and_close_above_level():
    setup = {"direction": 1, "level": 3010}
    assert M.is_retest(bar(1300, 3015, 3018, 3009, 3011), setup)
    assert not M.is_retest(bar(1300, 3015, 3018, 3011, 3012), setup)
    assert not M.is_retest(bar(1300, 3015, 3018, 3009, 3008), setup)


def test_short_retest_requires_touch_and_close_below_level():
    setup = {"direction": -1, "level": 3000}
    assert M.is_retest(bar(1300, 2995, 3001, 2990, 2999), setup)
    assert not M.is_retest(bar(1300, 2995, 2999, 2990, 2998), setup)
    assert not M.is_retest(bar(1300, 2995, 3001, 2990, 3002), setup)


def test_entry_is_next_open_and_tp_is_two_risk():
    bars = [
        bar(0, 3000, 3012, 2998, 3010),
        bar(300, 3012, 3014, 3011, 3013),
        bar(600, 3013, 3016, 3009, 3011),
        bar(900, 3012, 3027, 3011, 3026),
    ]
    sessions = [M.Session(1, "Asia", 0, 1200)]
    trades, meta = M.backtest(bars, sessions)
    assert meta["setups"] == 1
    assert len(trades) == 1
    trade = trades[0]
    assert trade["direction"] == "LONG"
    assert trade["entry_epoch"] == 900
    assert trade["entry_price"] == 3012
    assert trade["stop"] == 3005
    assert trade["tp"] == 3026
    assert trade["exit_reason"] == "TP"


def test_same_bar_stop_and_tp_conflict_uses_stop_first():
    bars = [
        bar(0, 3000, 3012, 2998, 3010),
        bar(300, 3012, 3014, 3011, 3013),
        bar(600, 3013, 3016, 3009, 3011),
        bar(900, 3012, 3027, 3004, 3020),
    ]
    sessions = [M.Session(1, "Asia", 0, 1200)]
    trades, meta = M.backtest(bars, sessions)
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "SL"
    assert trades[0]["exit_price"] == 3005


def test_html_shell_has_dropdown_and_markers():
    html = M.html_shell([], [], {"trades": 0})
    assert "<select id=\"tradeSelect\">" in html
    assert "FIRST" in html
    assert "RETEST" in html
    assert "ENTRY" in html


TESTS = [
    test_bullish_first_bar_creates_long_setup,
    test_bearish_first_bar_creates_short_setup,
    test_doji_first_bar_has_no_setup,
    test_long_retest_requires_touch_and_close_above_level,
    test_short_retest_requires_touch_and_close_below_level,
    test_entry_is_next_open_and_tp_is_two_risk,
    test_same_bar_stop_and_tp_conflict_uses_stop_first,
    test_html_shell_has_dropdown_and_markers,
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
