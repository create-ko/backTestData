# -*- coding: utf-8 -*-
"""EarnForex channel-system rule implementations.

The first pass focuses on the three high-confidence rules extracted from the
EarnForex PDFs: Bollinger Bandit, Dynamic Breakout II, and King Keltner.
Signals are computed from completed bars and stop orders are filled on the next
bar only to avoid same-bar look-ahead.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
from collections import namedtuple


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(ROOT, "data")
RESULT_DIR = os.path.join(ROOT, "result")
TIMEFRAMES = ["1m", "2m", "5m", "10m"]
STRATEGIES = ["bollinger_bandit", "dynamic_breakout_ii", "king_keltner"]


Bar = namedtuple("Bar", ["epoch", "open", "high", "low", "close"])


def load_bars(path):
    bars = []
    with open(path, encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            bars.append(
                Bar(
                    int(float(row["time"])),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                )
            )
    return bars


def aggregate_daily(bars):
    out = []
    current_day = None
    current = None
    for b in bars:
        day = dt.datetime.fromtimestamp(b.epoch, dt.timezone.utc).date()
        day_epoch = int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp())
        if day != current_day:
            if current is not None:
                out.append(current)
            current_day = day
            current = Bar(day_epoch, b.open, b.high, b.low, b.close)
        else:
            current = Bar(current.epoch, current.open, max(current.high, b.high), min(current.low, b.low), b.close)
    if current is not None:
        out.append(current)
    return out


def sma_at(values, index, length):
    if index < length - 1:
        return None
    window = values[index - length + 1 : index + 1]
    return sum(window) / float(length)


def stddev_at(values, index, length):
    avg = sma_at(values, index, length)
    if avg is None:
        return None
    window = values[index - length + 1 : index + 1]
    return math.sqrt(sum((v - avg) ** 2 for v in window) / float(length))


def true_range_at(bars, index):
    b = bars[index]
    if index == 0:
        return b.high - b.low
    prev_close = bars[index - 1].close
    return max(b.high, prev_close) - min(b.low, prev_close)


def avg_true_range_at(bars, index, length):
    if index < length - 1:
        return None
    values = [true_range_at(bars, i) for i in range(index - length + 1, index + 1)]
    return sum(values) / float(length)


def hlc3_values(bars):
    return [(b.high + b.low + b.close) / 3.0 for b in bars]


def closes(bars):
    return [b.close for b in bars]


def bollinger_bandit_signal(bars, index, ma_length=50, roc_length=30, deviations=1.0):
    close_values = closes(bars)
    ma = sma_at(close_values, index, ma_length)
    sd = stddev_at(close_values, index, ma_length)
    if ma is None or sd is None or index < roc_length:
        return None
    roc = close_values[index] - close_values[index - roc_length]
    if roc > 0:
        return {
            "strategy": "Bollinger Bandit",
            "direction": 1,
            "order_type": "stop",
            "price": ma + deviations * sd,
            "signal_index": index,
        }
    if roc < 0:
        return {
            "strategy": "Bollinger Bandit",
            "direction": -1,
            "order_type": "stop",
            "price": ma - deviations * sd,
            "signal_index": index,
        }
    return None


def king_keltner_signal(bars, index, avg_length=40, atr_length=40):
    typical = hlc3_values(bars)
    ma = sma_at(typical, index, avg_length)
    prev_ma = sma_at(typical, index - 1, avg_length)
    atr = avg_true_range_at(bars, index, atr_length)
    if ma is None or prev_ma is None or atr is None:
        return None
    if ma > prev_ma:
        return {
            "strategy": "King Keltner",
            "direction": 1,
            "order_type": "stop",
            "price": ma + atr,
            "signal_index": index,
        }
    if ma < prev_ma:
        return {
            "strategy": "King Keltner",
            "direction": -1,
            "order_type": "stop",
            "price": ma - atr,
            "signal_index": index,
        }
    return None


def fill_next_bar_stop_order(bars, signal_index, order):
    entry_index = signal_index + 1
    if entry_index >= len(bars):
        return None
    b = bars[entry_index]
    price = float(order["price"])
    direction = int(order["direction"])
    if direction == 1 and b.high >= price:
        return {
            "strategy": order["strategy"],
            "direction": 1,
            "signal_index": signal_index,
            "entry_index": entry_index,
            "entry_epoch": b.epoch,
            "entry_price": price,
        }
    if direction == -1 and b.low <= price:
        return {
            "strategy": order["strategy"],
            "direction": -1,
            "signal_index": signal_index,
            "entry_index": entry_index,
            "entry_epoch": b.epoch,
            "entry_price": price,
        }
    return None


def exit_level_for_trade(bars, index, trade, **params):
    if index <= trade["entry_index"]:
        return None
    strategy = trade["strategy"]
    if strategy == "King Keltner":
        length = int(params.get("avg_length", 40))
        return sma_at(hlc3_values(bars), index, length)
    if strategy == "Dynamic Breakout II":
        length = int(trade.get("lookback_days") or params.get("lookback_days", 20))
        return sma_at(closes(bars), index, length)
    if strategy == "Bollinger Bandit":
        start = int(params.get("liquidation_start_length", 50))
        days_held = max(0, index - trade["entry_index"])
        length = max(1, start - days_held)
        return sma_at(closes(bars), index, length)
    return None


def fill_next_bar_exit(bars, signal_index, trade, level):
    exit_index = signal_index + 1
    if level is None or exit_index >= len(bars):
        return None
    b = bars[exit_index]
    direction = int(trade["direction"])
    if direction == 1 and b.low <= level:
        return {
            "exit_index": exit_index,
            "exit_epoch": b.epoch,
            "exit_price": level,
            "exit_reason": "MA_STOP",
        }
    if direction == -1 and b.high >= level:
        return {
            "exit_index": exit_index,
            "exit_epoch": b.epoch,
            "exit_price": level,
            "exit_reason": "MA_STOP",
        }
    return None


def signal_for_strategy(bars, index, strategy, **params):
    if strategy == "bollinger_bandit":
        return bollinger_bandit_signal(
            bars,
            index,
            ma_length=int(params.get("ma_length", 50)),
            roc_length=int(params.get("roc_length", 30)),
            deviations=float(params.get("deviations", 1.0)),
        )
    if strategy == "king_keltner":
        return king_keltner_signal(
            bars,
            index,
            avg_length=int(params.get("avg_length", 40)),
            atr_length=int(params.get("atr_length", 40)),
        )
    raise ValueError("signal_for_strategy does not support %s" % strategy)


def backtest_strategy(bars, strategy, **params):
    trades = []
    open_trade = None
    dynamic_orders = {}
    if strategy == "dynamic_breakout_ii":
        dynamic_orders = {o["signal_index"]: o for o in dynamic_breakout_orders(bars)}

    for i in range(len(bars) - 1):
        if open_trade is not None:
            level = exit_level_for_trade(bars, i, open_trade, **params)
            exit_fill = fill_next_bar_exit(bars, i, open_trade, level)
            if exit_fill:
                trade = dict(open_trade)
                trade.update(exit_fill)
                direction = int(trade["direction"])
                trade["points"] = (trade["exit_price"] - trade["entry_price"]) * direction
                trades.append(trade)
                open_trade = None
            continue

        if strategy == "dynamic_breakout_ii":
            order = dynamic_orders.get(i)
        else:
            order = signal_for_strategy(bars, i, strategy, **params)
        if not order:
            continue
        fill = fill_next_bar_stop_order(bars, i, order)
        if fill:
            open_trade = fill
            if "lookback_days" in order:
                open_trade["lookback_days"] = order["lookback_days"]

    if open_trade is not None:
        final = bars[-1]
        trade = dict(open_trade)
        trade.update(
            {
                "exit_index": len(bars) - 1,
                "exit_epoch": final.epoch,
                "exit_price": final.close,
                "exit_reason": "EOD",
            }
        )
        direction = int(trade["direction"])
        trade["points"] = (trade["exit_price"] - trade["entry_price"]) * direction
        trades.append(trade)
    return trades


def dynamic_breakout_orders(bars, floor_days=20, ceiling_days=60, vol_length=30, deviations=2.0):
    close_values = closes(bars)
    lookback = float(floor_days)
    orders = []
    for i in range(1, len(bars)):
        today_vol = stddev_at(close_values, i, vol_length)
        yesterday_vol = stddev_at(close_values, i - 1, vol_length)
        if today_vol and yesterday_vol:
            delta = (today_vol - yesterday_vol) / today_vol if today_vol else 0.0
            lookback = round(lookback * (1.0 + delta))
            lookback = min(float(ceiling_days), max(float(floor_days), lookback))
        lb = int(lookback)
        if i < lb:
            continue
        ma = sma_at(close_values, i, lb)
        sd = stddev_at(close_values, i, lb)
        if ma is None or sd is None:
            continue
        up_band = ma + deviations * sd
        dn_band = ma - deviations * sd
        buy_point = max(b.high for b in bars[i - lb + 1 : i + 1])
        sell_point = min(b.low for b in bars[i - lb + 1 : i + 1])
        if bars[i].close > up_band:
            orders.append(
                {
                    "strategy": "Dynamic Breakout II",
                    "direction": 1,
                    "order_type": "stop",
                    "price": buy_point,
                    "signal_index": i,
                    "lookback_days": lb,
                }
            )
        elif bars[i].close < dn_band:
            orders.append(
                {
                    "strategy": "Dynamic Breakout II",
                    "direction": -1,
                    "order_type": "stop",
                    "price": sell_point,
                    "signal_index": i,
                    "lookback_days": lb,
                }
            )
    return orders


def generate_fills(bars, strategy):
    fills = []
    if strategy == "bollinger_bandit":
        for i in range(len(bars) - 1):
            order = bollinger_bandit_signal(bars, i)
            if order:
                fill = fill_next_bar_stop_order(bars, i, order)
                if fill:
                    fills.append(fill)
    elif strategy == "king_keltner":
        for i in range(len(bars) - 1):
            order = king_keltner_signal(bars, i)
            if order:
                fill = fill_next_bar_stop_order(bars, i, order)
                if fill:
                    fills.append(fill)
    elif strategy == "dynamic_breakout_ii":
        for order in dynamic_breakout_orders(bars):
            fill = fill_next_bar_stop_order(bars, order["signal_index"], order)
            if fill:
                fill["lookback_days"] = order.get("lookback_days")
                fills.append(fill)
    else:
        raise ValueError("unknown strategy: %s" % strategy)
    return fills


def summarize_trades(trades):
    long_count = sum(1 for t in trades if t["direction"] == 1)
    short_count = sum(1 for t in trades if t["direction"] == -1)
    wins = sum(1 for t in trades if t.get("points", 0.0) > 0)
    total_points = sum(t.get("points", 0.0) for t in trades)
    return {
        "trades": len(trades),
        "long": long_count,
        "short": short_count,
        "wins": wins,
        "win_rate": (wins / float(len(trades))) if trades else 0.0,
        "total_points": total_points,
    }


def apply_trade_cost(trades, cost_points=0.0):
    out = []
    for trade in trades:
        item = dict(trade)
        item["cost_points"] = float(cost_points)
        item["net_points"] = float(item.get("points", 0.0)) - float(cost_points)
        out.append(item)
    return out


def max_drawdown(values):
    equity = 0.0
    peak = 0.0
    mdd = 0.0
    for value in values:
        equity += float(value)
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        if drawdown > mdd:
            mdd = drawdown
    return mdd


def performance_summary(trades):
    gross_values = [float(t.get("points", 0.0)) for t in trades]
    net_values = [float(t.get("net_points", t.get("points", 0.0))) for t in trades]
    wins = [v for v in net_values if v > 0]
    losses = [v for v in net_values if v < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    return {
        "trades": len(trades),
        "long": sum(1 for t in trades if t.get("direction") == 1),
        "short": sum(1 for t in trades if t.get("direction") == -1),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / float(len(trades))) if trades else 0.0,
        "total_points": sum(gross_values),
        "total_net_points": sum(net_values),
        "avg_net_points": (sum(net_values) / float(len(trades))) if trades else 0.0,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "max_drawdown_points": max_drawdown(net_values),
    }


def entry_year(trade):
    return dt.datetime.fromtimestamp(int(trade["entry_epoch"]), dt.timezone.utc).year


def yearly_summary(trades):
    by_year = {}
    for trade in trades:
        by_year.setdefault(entry_year(trade), []).append(trade)
    rows = []
    for year in sorted(by_year):
        row = performance_summary(by_year[year])
        row["year"] = year
        rows.append(row)
    return rows


def summary_row(timeframe, strategy, trades):
    summary = performance_summary(trades)
    row = dict(summary)
    row["timeframe"] = timeframe
    row["strategy"] = strategy
    return row


def run_one_timeframe(timeframe, cost_points=0.60):
    source = os.path.join(DATA_DIR, "xauusd_%s_2010-01-01_2026-06-16.csv" % timeframe)
    bars = aggregate_daily(load_bars(source))
    rows = []
    yearly_rows = []
    details = {}
    for strategy in STRATEGIES:
        trades = apply_trade_cost(backtest_strategy(bars, strategy), cost_points=cost_points)
        summary = summary_row(timeframe, strategy, trades)
        yearly = yearly_summary(trades)
        rows.append(summary)
        for item in yearly:
            yearly_rows.append(
                dict(item, timeframe=timeframe, strategy=strategy)
            )
        details[strategy] = {"summary": summary, "yearly": yearly, "sample_trades": trades[:20]}
    return rows, yearly_rows, details


def formatted_summary_row(row):
    return [
        row["timeframe"],
        row["strategy"],
        row["trades"],
        row["long"],
        row["short"],
        "%.6f" % row["win_rate"],
        "%.6f" % row["total_points"],
        "%.6f" % row["total_net_points"],
        "%.6f" % row["profit_factor"] if row["profit_factor"] is not None else "",
        "%.6f" % row["max_drawdown_points"],
    ]


def formatted_yearly_row(row):
    return [
        row["timeframe"],
        row["strategy"],
        row["year"],
        row["trades"],
        "%.6f" % row["win_rate"],
        "%.6f" % row["total_net_points"],
        "%.6f" % row["profit_factor"] if row["profit_factor"] is not None else "",
        "%.6f" % row["max_drawdown_points"],
    ]


def run():
    rows = []
    yearly_rows = []
    details = {}
    for timeframe in TIMEFRAMES:
        tf_rows, tf_yearly_rows, tf_details = run_one_timeframe(timeframe, cost_points=0.60)
        rows.extend(tf_rows)
        yearly_rows.extend(tf_yearly_rows)
        details[timeframe] = tf_details

    os.makedirs(RESULT_DIR, exist_ok=True)
    csv_path = os.path.join(RESULT_DIR, "earnforex_channel_systems_tf_summary.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.writer(fp)
        writer.writerow(["timeframe", "strategy", "trades", "long", "short", "win_rate", "total_points", "total_net_points", "profit_factor", "max_drawdown_points"])
        writer.writerows(formatted_summary_row(row) for row in rows)
    yearly_csv_path = os.path.join(RESULT_DIR, "earnforex_channel_systems_tf_yearly.csv")
    with open(yearly_csv_path, "w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.writer(fp)
        writer.writerow(["timeframe", "strategy", "year", "trades", "win_rate", "total_net_points", "profit_factor", "max_drawdown_points"])
        writer.writerows(formatted_yearly_row(row) for row in yearly_rows)
    json_path = os.path.join(RESULT_DIR, "earnforex_channel_systems_tf_details.json")
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(details, fp, indent=2)
    print("wrote result/earnforex_channel_systems_tf_summary.csv")
    print("wrote result/earnforex_channel_systems_tf_yearly.csv")
    print("wrote result/earnforex_channel_systems_tf_details.json")


if __name__ == "__main__":
    run()
