# -*- coding: utf-8 -*-
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(ROOT, "src", "scripts", "87_earnforex_channel_systems.py")

spec = importlib.util.spec_from_file_location("earnforex_channel_systems", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def bar(epoch, open_, high, low, close):
    return M.Bar(epoch, open_, high, low, close)


def test_aggregate_daily_keeps_first_open_high_low_last_close():
    bars = [
        bar(0, 10, 12, 9, 11),
        bar(60, 11, 13, 10, 12),
        bar(86400, 20, 22, 19, 21),
    ]
    daily = M.aggregate_daily(bars)
    assert daily == [
        bar(0, 10, 13, 9, 12),
        bar(86400, 20, 22, 19, 21),
    ]


def test_basic_indicators_are_rolling_and_use_current_bar():
    values = [1, 2, 3, 4, 5]
    assert M.sma_at(values, 4, 3) == 4.0
    assert round(M.stddev_at(values, 4, 3), 6) == round((2.0 / 3.0) ** 0.5, 6)
    bars = [
        bar(0, 10, 12, 9, 11),
        bar(1, 11, 14, 10, 12),
        bar(2, 12, 13, 8, 9),
    ]
    assert M.true_range_at(bars, 0) == 3
    assert M.true_range_at(bars, 1) == 4
    assert M.true_range_at(bars, 2) == 5
    assert M.avg_true_range_at(bars, 2, 2) == 4.5


def test_bollinger_bandit_uses_rate_of_change_filter():
    bars = [bar(i, 100 + i, 101 + i, 99 + i, 100 + i) for i in range(80)]
    signal = M.bollinger_bandit_signal(bars, 60, ma_length=10, roc_length=30, deviations=1.0)
    assert signal["direction"] == 1
    assert signal["order_type"] == "stop"
    closes = [b.close for b in bars]
    expected = M.sma_at(closes, 60, 10) + M.stddev_at(closes, 60, 10)
    assert signal["price"] == expected

    falling = [bar(i, 200 - i, 201 - i, 199 - i, 200 - i) for i in range(80)]
    signal = M.bollinger_bandit_signal(falling, 60, ma_length=10, roc_length=30, deviations=1.0)
    assert signal["direction"] == -1
    closes = [b.close for b in falling]
    expected = M.sma_at(closes, 60, 10) - M.stddev_at(closes, 60, 10)
    assert signal["price"] == expected


def test_king_keltner_uses_channel_breakout_in_ma_direction():
    bars = [bar(i, 100 + i, 102 + i, 99 + i, 101 + i) for i in range(45)]
    signal = M.king_keltner_signal(bars, 41, avg_length=5, atr_length=5)
    assert signal["direction"] == 1
    assert signal["price"] > bars[41].close

    falling = [bar(i, 200 - i, 202 - i, 199 - i, 201 - i) for i in range(45)]
    signal = M.king_keltner_signal(falling, 41, avg_length=5, atr_length=5)
    assert signal["direction"] == -1
    assert signal["price"] < falling[41].close


def test_stop_order_fills_on_next_bar_without_same_bar_lookahead():
    bars = [
        bar(0, 10, 11, 9, 10),
        bar(1, 10, 12, 9, 11),
        bar(2, 11, 13, 10, 12),
    ]
    order = {"direction": 1, "price": 12.5, "order_type": "stop", "strategy": "TEST"}
    fill = M.fill_next_bar_stop_order(bars, 0, order)
    assert fill is None
    fill = M.fill_next_bar_stop_order(bars, 1, order)
    assert fill["entry_index"] == 2
    assert fill["entry_price"] == 12.5


def test_dynamic_breakout_emits_adaptive_stop_orders():
    bars = []
    for i in range(80):
        close = 100 + i * 0.5
        if i >= 60:
            close += (i - 59) * 2.0
        bars.append(bar(i, close, close + 2, close - 1, close))
    orders = M.dynamic_breakout_orders(bars, floor_days=20, ceiling_days=60, vol_length=10, deviations=1.0)
    assert len(orders) > 0
    assert orders[-1]["direction"] == 1
    assert 20 <= orders[-1]["lookback_days"] <= 60


def test_backtest_strategy_exits_long_on_moving_average_stop():
    bars = []
    for i in range(45):
        close = 100 + i
        bars.append(bar(i, close, close + 2, close - 1, close))
    bars.append(bar(45, 145, 148, 144, 147))
    bars.append(bar(46, 147, 148, 120, 121))

    trades = M.backtest_strategy(bars, "king_keltner", avg_length=5, atr_length=5)

    assert len(trades) >= 1
    first = trades[0]
    assert first["strategy"] == "King Keltner"
    assert first["direction"] == 1
    assert first["exit_reason"] == "MA_STOP"
    assert first["exit_index"] > first["entry_index"]


def test_apply_trade_cost_subtracts_round_turn_points():
    trades = [
        {"points": 10.0},
        {"points": -3.0},
    ]
    out = M.apply_trade_cost(trades, cost_points=1.5)
    assert out[0]["net_points"] == 8.5
    assert out[1]["net_points"] == -4.5
    assert "net_points" not in trades[0]


def test_performance_summary_includes_pf_and_mdd():
    trades = [
        {"entry_epoch": 0, "direction": 1, "points": 10.0, "net_points": 8.0},
        {"entry_epoch": 86400, "direction": -1, "points": -5.0, "net_points": -7.0},
        {"entry_epoch": 2 * 86400, "direction": 1, "points": 4.0, "net_points": 2.0},
    ]
    summary = M.performance_summary(trades)
    assert summary["trades"] == 3
    assert summary["wins"] == 2
    assert summary["losses"] == 1
    assert summary["total_net_points"] == 3.0
    assert round(summary["profit_factor"], 6) == round(10.0 / 7.0, 6)
    assert summary["max_drawdown_points"] == 7.0


def test_yearly_summary_groups_by_entry_year():
    trades = [
        {"entry_epoch": 1262304000, "direction": 1, "net_points": 3.0},
        {"entry_epoch": 1293840000, "direction": -1, "net_points": -2.0},
        {"entry_epoch": 1293926400, "direction": 1, "net_points": 5.0},
    ]
    rows = M.yearly_summary(trades)
    assert rows[0]["year"] == 2010
    assert rows[0]["trades"] == 1
    assert rows[0]["total_net_points"] == 3.0
    assert rows[1]["year"] == 2011
    assert rows[1]["trades"] == 2
    assert rows[1]["total_net_points"] == 3.0


def test_summary_row_includes_timeframe_and_strategy():
    trades = [
        {"entry_epoch": 0, "direction": 1, "points": 5.0, "net_points": 4.0},
    ]
    row = M.summary_row("2m", "king_keltner", trades)
    assert row["timeframe"] == "2m"
    assert row["strategy"] == "king_keltner"
    assert row["trades"] == 1
    assert row["total_net_points"] == 4.0


TESTS = [
    test_aggregate_daily_keeps_first_open_high_low_last_close,
    test_basic_indicators_are_rolling_and_use_current_bar,
    test_bollinger_bandit_uses_rate_of_change_filter,
    test_king_keltner_uses_channel_breakout_in_ma_direction,
    test_stop_order_fills_on_next_bar_without_same_bar_lookahead,
    test_dynamic_breakout_emits_adaptive_stop_orders,
    test_backtest_strategy_exits_long_on_moving_average_stop,
    test_apply_trade_cost_subtracts_round_turn_points,
    test_performance_summary_includes_pf_and_mdd,
    test_yearly_summary_groups_by_entry_year,
    test_summary_row_includes_timeframe_and_strategy,
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
