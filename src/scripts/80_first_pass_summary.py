# -*- coding: utf-8 -*-
"""First-pass Gold strategy summary report.

This script aggregates existing double-BB grid backtest logic into compact CSVs.
It does not change the strategy functions in gold_data_prep.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gold_data_prep as prep  # noqa: E402


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "result" / "first_pass_summary"

TIMEFRAMES = ["5m", "10m"]
DIRECTIONS = ["long", "short"]
ENTRY_TYPES = ["immediate", "pullback"]
V_METHODS = ["session_opening_range", "avg_range_20"]
EXIT_MODELS = ["defensive_return_to_entry1", "split_v_targets", "conservative_psychology_model"]
MAX_ENTRIES = 3
MAX_HOLDING_BARS = 48

METRIC_COLS = [
    "total_trades",
    "win_rate",
    "expectancy_v",
    "profit_factor",
    "max_drawdown_v",
    "average_mfe_v",
    "average_mae_v",
    "mfe_capture_ratio",
    "reached_4th_entry_rate",
    "returned_to_entry1_after_3_rate",
]


def _round_report(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(3)
    return out


def _summary_metrics(trades: pd.DataFrame) -> dict:
    summary = prep.summarize_backtest_results(trades).iloc[0].to_dict()
    return {
        "total_trades": summary.get("total_trades"),
        "win_rate": summary.get("win_rate"),
        "expectancy_v": summary.get("expectancy_v"),
        "profit_factor": summary.get("profit_factor"),
        "max_drawdown_v": summary.get("max_drawdown_v"),
        "average_mfe_v": summary.get("average_mfe_v"),
        "average_mae_v": summary.get("average_mae_v"),
        "mfe_capture_ratio": summary.get("mfe_capture_ratio"),
        "reached_4th_entry_rate": summary.get("reached_4th_entry_rate"),
        "returned_to_entry1_after_3_rate": summary.get("returned_to_entry1_after_3_rate"),
    }


def _bars_bucket(value):
    if pd.isna(value):
        return "na"
    value = int(value)
    if 1 <= value <= 3:
        return "1~3"
    if 4 <= value <= 6:
        return "4~6"
    if 7 <= value <= 10:
        return "7~10"
    if value >= 11:
        return "11+"
    return "na"


def _filled_bucket(row):
    if bool(row.get("reached_4th_entry", False)):
        return "4+"
    value = row.get("filled_entries_count", row.get("max_filled_entries", pd.NA))
    if pd.isna(value):
        return "na"
    value = int(value)
    return str(value) if value in (1, 2, 3) else "4+"


def _add_context(row: dict, context: dict) -> dict:
    out = dict(context)
    out.update(row)
    return out


def _append_group_summaries(rows: list, trades: pd.DataFrame, group_col: str, context: dict, value_name: str) -> None:
    if trades.empty or group_col not in trades.columns:
        return
    for value, group in trades.groupby(group_col, dropna=False):
        row = _summary_metrics(group)
        row[value_name] = value
        rows.append(_add_context(row, context))


def _make_immediate_candidates(df: pd.DataFrame, direction: str) -> pd.DataFrame:
    event_col = "buy_breakout_double_bb" if direction == "long" else "sell_breakout_double_bb"
    if event_col not in df.columns:
        raise ValueError("Missing event column: %s" % event_col)

    event_positions = [i for i, flag in enumerate(df[event_col].to_numpy()) if bool(flag)]
    rows = []
    idx = df.index
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    timeframe = df.attrs.get("timeframe", "unknown")
    session_values = df["session"] if "session" in df.columns else pd.Series("unknown", index=df.index)

    for breakout_pos in event_positions:
        entry_pos = breakout_pos + 1
        if entry_pos >= len(df):
            continue
        candle_range = highs[breakout_pos] - lows[breakout_pos]
        if candle_range == 0:
            close_position = pd.NA
        elif direction == "long":
            close_position = (closes[breakout_pos] - lows[breakout_pos]) / candle_range
        else:
            close_position = (highs[breakout_pos] - closes[breakout_pos]) / candle_range
        rows.append({
            "direction": direction,
            "breakout_time": idx[breakout_pos],
            "pullback_touch_time": idx[breakout_pos],
            "entry_time": idx[entry_pos],
            "entry_price": opens[entry_pos],
            "session": session_values.iloc[entry_pos],
            "timeframe": timeframe,
            "bars_to_pullback": pd.NA,
            "midline_broken_before_entry": False,
            "breakout_close_position": close_position,
            "candidate_window": "immediate",
            "entry_type": "immediate",
        })
    candidates = pd.DataFrame(rows)
    print("Immediate candidates %s %s: %s" % (timeframe, direction, len(candidates)))
    return candidates


def _prepare_data(timeframe: str) -> pd.DataFrame:
    filepath = DATA_DIR / ("xauusd_%s_2010-01-01_2026-06-16.csv" % timeframe)
    df = prep.load_gold_data(filepath, timeframe=timeframe)
    df = prep.assign_session(df)
    df = prep.add_bollinger_bands(df)
    df = prep.detect_buy_breakout_double_bb(df, direction="long")
    df = prep.detect_buy_breakout_double_bb(df, direction="short")
    return df


def _candidate_sets(df: pd.DataFrame, direction: str) -> dict[str, pd.DataFrame]:
    immediate = _make_immediate_candidates(df, direction)
    pullback = prep.find_buy_pullback_entries(df, max_bars=6, direction=direction)
    if not pullback.empty:
        pullback = pullback.copy()
        pullback["entry_type"] = "pullback"
    return {"immediate": immediate, "pullback": pullback}


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    by_config = []
    by_midline = []
    by_session = []
    by_bars = []
    by_fills = []

    for timeframe in TIMEFRAMES:
        df = _prepare_data(timeframe)
        candidate_cache = {direction: _candidate_sets(df, direction) for direction in DIRECTIONS}

        for entry_type in ENTRY_TYPES:
            for v_method in V_METHODS:
                for exit_model in EXIT_MODELS:
                    direction_trades = []
                    for direction in DIRECTIONS:
                        candidates = candidate_cache[direction][entry_type]
                        if candidates.empty:
                            continue
                        candidates = prep.add_v_metrics_to_candidates(df, candidates)
                        grid = prep.simulate_grid_path(
                            df,
                            candidates,
                            v_method=v_method,
                            max_entries=MAX_ENTRIES,
                            max_holding_bars=MAX_HOLDING_BARS,
                        )
                        trades = prep.backtest_exit_model(
                            df,
                            grid,
                            model_name=exit_model,
                            conservative_same_bar=True,
                            fee_points=0.0,
                            slippage_points=0.0,
                            max_entries=MAX_ENTRIES,
                            max_holding_bars=MAX_HOLDING_BARS,
                        )
                        if trades.empty:
                            continue
                        trades = trades.copy()
                        trades["entry_type"] = entry_type
                        trades["filled_entries_bucket"] = trades.apply(_filled_bucket, axis=1)
                        trades["bars_to_pullback_bucket"] = trades["bars_to_pullback"].map(_bars_bucket)
                        direction_trades.append(trades)

                        context = {
                            "product": "Gold",
                            "period": "2010-01-01~2026-06-16",
                            "timeframe": timeframe,
                            "direction": direction,
                            "entry_type": entry_type,
                            "v_method": v_method,
                            "exit_model": exit_model,
                        }
                        by_config.append(_add_context(_summary_metrics(trades), context))
                        _append_group_summaries(by_midline, trades, "midline_broken_before_entry", context, "midline_broken_before_entry")
                        _append_group_summaries(by_session, trades, "session", context, "session")
                        _append_group_summaries(by_bars, trades, "bars_to_pullback_bucket", context, "bars_to_pullback_bucket")
                        _append_group_summaries(by_fills, trades, "filled_entries_bucket", context, "filled_entries_count")

                    if direction_trades:
                        combined = pd.concat(direction_trades, ignore_index=True)
                        context = {
                            "product": "Gold",
                            "period": "2010-01-01~2026-06-16",
                            "timeframe": timeframe,
                            "direction": "combined",
                            "entry_type": entry_type,
                            "v_method": v_method,
                            "exit_model": exit_model,
                        }
                        by_config.append(_add_context(_summary_metrics(combined), context))
                        _append_group_summaries(by_midline, combined, "midline_broken_before_entry", context, "midline_broken_before_entry")
                        _append_group_summaries(by_session, combined, "session", context, "session")
                        _append_group_summaries(by_bars, combined, "bars_to_pullback_bucket", context, "bars_to_pullback_bucket")
                        _append_group_summaries(by_fills, combined, "filled_entries_bucket", context, "filled_entries_count")

    tables = {
        "summary_by_config": pd.DataFrame(by_config),
        "summary_by_midline": pd.DataFrame(by_midline),
        "summary_by_session": pd.DataFrame(by_session),
        "summary_by_bars_to_pullback": pd.DataFrame(by_bars),
        "summary_by_filled_entries": pd.DataFrame(by_fills),
    }
    for name, table in tables.items():
        table = _round_report(table)
        tables[name] = table
        table.to_csv(OUTPUT_DIR / ("%s.csv" % name), index=False, encoding="utf-8-sig")

    print("")
    print("=== FIRST PASS SUMMARY: by_config ===")
    cols = ["timeframe", "direction", "entry_type", "v_method", "exit_model"] + METRIC_COLS
    print(tables["summary_by_config"][cols].to_string(index=False))
    print("")
    print("WROTE:", OUTPUT_DIR)
    return tables


if __name__ == "__main__":
    run()
