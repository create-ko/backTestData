# -*- coding: utf-8 -*-
"""Compare H1 trend filters on the existing Gold 10m pullback backtest.

The entry/grid/exit logic is not changed. H1 features are built from the 10m
data and merged onto entry candidates using only the last fully closed H1 bar.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import math
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gold_data_prep as prep  # noqa: E402


OUTPUT_DIR = Path(__file__).resolve().parents[2] / "result" / "h1_trend_filter_compare"

TIMEFRAME = "10m"
DIRECTIONS = ["long", "short"]
ENTRY_TYPE = "pullback"
V_METHODS = ["session_opening_range", "avg_range_20"]
EXIT_MODELS = ["defensive_return_to_entry1", "conservative_psychology_model"]
MAX_ENTRIES = 3
MAX_HOLDING_BARS = 48

COMMISSION_PER_CONTRACT_ROUND_TURN = 0.0
TICK_SIZE = 0.1
TICK_VALUE = 10.0
POINT_VALUE = 100.0
COST_BASE = {
    "cost_scenario": "cost_base",
    "commission_per_contract_round_turn": COMMISSION_PER_CONTRACT_ROUND_TURN,
    "slippage_ticks_per_fill": 1.0,
}
COST_ZERO = {
    "cost_scenario": "cost_0",
    "commission_per_contract_round_turn": 0.0,
    "slippage_ticks_per_fill": 0.0,
}

H1_FILTERS = [
    "no_h1_filter",
    "h1_bb20_mid_slope",
    "h1_ema20_slope",
    "h1_ema20_ema60_alignment",
]

METRIC_COLS = [
    "total_trades",
    "trade_reduction_ratio",
    "expectancy_v",
    "profit_factor",
    "max_drawdown_v",
    "win_rate",
    "avg_win_v",
    "avg_loss_v",
    "avg_mfe_v",
    "avg_mae_v",
    "mfe_capture_ratio",
    "reached_4th_entry_ratio",
    "returned_to_entry_1_after_3_fills_ratio",
    "avg_trade_cost_v",
    "cost_as_percent_of_gross_profit",
    "low_sample",
]


def _load_first_pass_helpers():
    helper_path = SCRIPT_DIR / "80_first_pass_summary.py"
    spec = importlib.util.spec_from_file_location("first_pass_summary", helper_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIRST_PASS = _load_first_pass_helpers()


def _quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _round_report(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(3)
    return out


def _cost_points_per_execution(scenario: dict) -> tuple[float, float]:
    commission_rt = float(scenario["commission_per_contract_round_turn"])
    slippage_ticks = float(scenario["slippage_ticks_per_fill"])
    commission_side_points = (commission_rt / 2.0) / POINT_VALUE if POINT_VALUE else 0.0
    slippage_points = slippage_ticks * TICK_SIZE
    expected_tick_value = TICK_SIZE * POINT_VALUE
    if abs(expected_tick_value - TICK_VALUE) > 1e-9:
        # TODO: Decide whether point/tick mismatch should stop the report.
        pass
    return commission_side_points, slippage_points


def make_h1_features_from_10m(df: pd.DataFrame) -> pd.DataFrame:
    """Build H1 OHLCV and trend features from timezone-aware 10m data."""
    h1 = (
        df[["open", "high", "low", "close", "volume"]]
        .resample("1h", label="left", closed="left")
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        .dropna(subset=["open", "high", "low", "close"])
    )
    h1["h1_bar_time_used"] = h1.index
    h1["h1_bar_end_time_used"] = h1.index + pd.Timedelta(hours=1)
    h1["h1_close"] = h1["close"]
    h1["h1_bb20_mid"] = h1["close"].rolling(20, min_periods=20).mean()
    h1["h1_bb20_mid_3bars_ago"] = h1["h1_bb20_mid"].shift(3)
    h1["h1_ema20"] = h1["close"].ewm(span=20, adjust=False, min_periods=20).mean()
    h1["h1_ema20_3bars_ago"] = h1["h1_ema20"].shift(3)
    h1["h1_ema60"] = h1["close"].ewm(span=60, adjust=False, min_periods=60).mean()

    cols = [
        "h1_bar_time_used",
        "h1_bar_end_time_used",
        "h1_close",
        "h1_bb20_mid",
        "h1_bb20_mid_3bars_ago",
        "h1_ema20",
        "h1_ema20_3bars_ago",
        "h1_ema60",
    ]
    return h1[cols].reset_index(drop=True).sort_values("h1_bar_end_time_used")


def attach_h1_features_to_candidates(candidates: pd.DataFrame, h1_features: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    left = candidates.copy().sort_values("entry_time")
    left["_entry_time_merge_ns"] = left["entry_time"].map(lambda ts: pd.Timestamp(ts).value)
    right = h1_features.copy().sort_values("h1_bar_end_time_used")
    right["_h1_bar_end_time_merge_ns"] = right["h1_bar_end_time_used"].map(lambda ts: pd.Timestamp(ts).value)
    out = pd.merge_asof(
        left,
        right,
        left_on="_entry_time_merge_ns",
        right_on="_h1_bar_end_time_merge_ns",
        direction="backward",
        allow_exact_matches=True,
    )
    out["h1_bar_time_used_before_entry"] = out["h1_bar_time_used"] < out["entry_time"]
    out["h1_bar_end_time_used_not_after_entry"] = out["h1_bar_end_time_used"] <= out["entry_time"]
    out = out.drop(columns=["_entry_time_merge_ns", "_h1_bar_end_time_merge_ns"])
    return out


def apply_h1_filter(candidates: pd.DataFrame, filter_name: str) -> pd.DataFrame:
    if filter_name == "no_h1_filter":
        out = candidates.copy()
        out["h1_filter_pass"] = True
        out["h1_filter_name"] = filter_name
        return out

    direction = candidates["direction"] if "direction" in candidates.columns else pd.Series("long", index=candidates.index)
    if filter_name == "h1_bb20_mid_slope":
        long_ok = (
            (candidates["h1_close"] > candidates["h1_bb20_mid"])
            & (candidates["h1_bb20_mid"] > candidates["h1_bb20_mid_3bars_ago"])
        )
        short_ok = (
            (candidates["h1_close"] < candidates["h1_bb20_mid"])
            & (candidates["h1_bb20_mid"] < candidates["h1_bb20_mid_3bars_ago"])
        )
    elif filter_name == "h1_ema20_slope":
        long_ok = (
            (candidates["h1_close"] > candidates["h1_ema20"])
            & (candidates["h1_ema20"] > candidates["h1_ema20_3bars_ago"])
        )
        short_ok = (
            (candidates["h1_close"] < candidates["h1_ema20"])
            & (candidates["h1_ema20"] < candidates["h1_ema20_3bars_ago"])
        )
    elif filter_name == "h1_ema20_ema60_alignment":
        long_ok = (
            (candidates["h1_ema20"] > candidates["h1_ema60"])
            & (candidates["h1_close"] > candidates["h1_ema20"])
        )
        short_ok = (
            (candidates["h1_ema20"] < candidates["h1_ema60"])
            & (candidates["h1_close"] < candidates["h1_ema20"])
        )
    else:
        raise ValueError("Unsupported H1 filter: %s" % filter_name)

    leak_safe = candidates["h1_bar_time_used_before_entry"].fillna(False) & candidates["h1_bar_end_time_used_not_after_entry"].fillna(False)
    passed = ((direction == "long") & long_ok.fillna(False)) | ((direction == "short") & short_ok.fillna(False))
    out = candidates.loc[passed & leak_safe].copy()
    out["h1_filter_pass"] = True
    out["h1_filter_name"] = filter_name
    return out


def _mean_bool(series: pd.Series) -> float:
    if series.empty:
        return math.nan
    return float(series.fillna(False).astype(bool).mean())


def _summary_metrics(
    trades: pd.DataFrame,
    baseline_trades: pd.DataFrame | None,
    no_filter_total_trades: int | float | None,
) -> dict:
    summary = prep.summarize_backtest_results(trades).iloc[0].to_dict()
    pnl = pd.to_numeric(trades["realized_pnl_v"], errors="coerce").fillna(0.0)

    if baseline_trades is not None and len(baseline_trades) == len(trades):
        base_pnl = pd.to_numeric(baseline_trades["realized_pnl_v"], errors="coerce").fillna(0.0).reset_index(drop=True)
        cost_pnl = pnl.reset_index(drop=True)
        cost_drag = base_pnl - cost_pnl
        total_cost_v = float(cost_drag.sum())
        avg_cost_v = float(cost_drag.mean()) if len(cost_drag) else 0.0
        gross_profit_base = float(base_pnl[base_pnl > 0].sum())
    else:
        total_cost_v = 0.0
        avg_cost_v = 0.0
        gross_profit_base = float(pnl[pnl > 0].sum())

    total_trades = int(summary.get("total_trades") or 0)
    if no_filter_total_trades and no_filter_total_trades > 0:
        trade_reduction_ratio = 1.0 - (total_trades / float(no_filter_total_trades))
    else:
        trade_reduction_ratio = 0.0

    entry_fills = pd.to_numeric(trades.get("max_filled_entries", pd.Series(dtype=float)), errors="coerce")
    three_fill_mask = entry_fills >= 3
    if three_fill_mask.any() and "returned_to_entry_1_after_3_fills" in trades.columns:
        returned_ratio = _mean_bool(trades.loc[three_fill_mask, "returned_to_entry_1_after_3_fills"])
    else:
        returned_ratio = 0.0

    return {
        "total_trades": total_trades,
        "trade_reduction_ratio": trade_reduction_ratio,
        "expectancy_v": summary.get("expectancy_v"),
        "profit_factor": summary.get("profit_factor"),
        "max_drawdown_v": summary.get("max_drawdown_v"),
        "win_rate": summary.get("win_rate"),
        "avg_win_v": summary.get("avg_win_v"),
        "avg_loss_v": summary.get("avg_loss_v"),
        "avg_mfe_v": summary.get("average_mfe_v"),
        "avg_mae_v": summary.get("average_mae_v"),
        "mfe_capture_ratio": summary.get("mfe_capture_ratio"),
        "reached_4th_entry_ratio": _mean_bool(trades["reached_4th_entry"]) if "reached_4th_entry" in trades.columns else math.nan,
        "returned_to_entry_1_after_3_fills_ratio": returned_ratio,
        "avg_trade_cost_v": avg_cost_v,
        "cost_as_percent_of_gross_profit": total_cost_v / gross_profit_base if gross_profit_base > 0 else math.inf,
        "low_sample": total_trades < 300,
    }


def _add_context(row: dict, context: dict) -> dict:
    out = dict(context)
    out.update(row)
    return out


def _run_trades(df: pd.DataFrame, grid: pd.DataFrame, exit_model: str, scenario: dict) -> pd.DataFrame:
    fee_points, slippage_points = _cost_points_per_execution(scenario)
    return _quiet_call(
        prep.backtest_exit_model,
        df,
        grid,
        model_name=exit_model,
        conservative_same_bar=True,
        fee_points=fee_points,
        slippage_points=slippage_points,
        max_entries=MAX_ENTRIES,
        max_holding_bars=MAX_HOLDING_BARS,
    )


def _context(direction: str, h1_filter: str, v_method: str, exit_model: str) -> dict:
    return {
        "product": "Gold",
        "period": "2010-01-01~2026-06-16",
        "timeframe": TIMEFRAME,
        "entry_type": ENTRY_TYPE,
        "max_entries": MAX_ENTRIES,
        "cost_scenario": COST_BASE["cost_scenario"],
        "direction": direction,
        "h1_filter_name": h1_filter,
        "v_method": v_method,
        "exit_model": exit_model,
    }


def _append_group(
    rows: list[dict],
    trades: pd.DataFrame,
    baseline: pd.DataFrame,
    no_filter_trades: pd.DataFrame | None,
    group_col: str,
    value_col: str,
    context: dict,
) -> None:
    if trades.empty or group_col not in trades.columns:
        return
    for value, group in trades.groupby(group_col, dropna=False):
        base_group = baseline.loc[group.index] if set(group.index).issubset(set(baseline.index)) else None
        if no_filter_trades is not None and group_col in no_filter_trades.columns:
            no_filter_total = int((no_filter_trades[group_col] == value).sum())
        else:
            no_filter_total = len(group)
        row = _summary_metrics(group, base_group, no_filter_total)
        row[value_col] = value
        rows.append(_add_context(row, context))


def run() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = _quiet_call(FIRST_PASS._prepare_data, TIMEFRAME)
    h1_features = make_h1_features_from_10m(df)

    candidates_by_direction = {}
    for direction in DIRECTIONS:
        pullback = _quiet_call(FIRST_PASS._candidate_sets, df, direction)[ENTRY_TYPE]
        candidates_by_direction[direction] = attach_h1_features_to_candidates(pullback, h1_features)

    filtered_candidates = {
        (direction, h1_filter): apply_h1_filter(candidates, h1_filter)
        for direction, candidates in candidates_by_direction.items()
        for h1_filter in H1_FILTERS
    }

    summary_rows = []
    session_rows = []
    direction_rows = []
    exit_model_rows = []
    v_method_rows = []
    trade_cache = {}

    for h1_filter in H1_FILTERS:
        for v_method in V_METHODS:
            for exit_model in EXIT_MODELS:
                direction_cost_trades = []
                direction_zero_trades = []
                no_filter_cost_by_direction = {}

                for direction in DIRECTIONS:
                    candidates = filtered_candidates[(direction, h1_filter)]
                    no_filter_candidates = filtered_candidates[(direction, "no_h1_filter")]
                    context = _context(direction, h1_filter, v_method, exit_model)

                    if candidates.empty:
                        continue
                    candidates_v = _quiet_call(prep.add_v_metrics_to_candidates, df, candidates)
                    grid = _quiet_call(
                        prep.simulate_grid_path,
                        df,
                        candidates_v,
                        v_method=v_method,
                        max_entries=MAX_ENTRIES,
                        max_holding_bars=MAX_HOLDING_BARS,
                    )
                    if grid.empty:
                        continue

                    zero_trades = _run_trades(df, grid, exit_model, COST_ZERO).reset_index(drop=True)
                    cost_trades = _run_trades(df, grid, exit_model, COST_BASE).reset_index(drop=True)
                    if cost_trades.empty:
                        continue
                    for trades in (zero_trades, cost_trades):
                        trades["h1_filter_name"] = h1_filter
                        trades["entry_type"] = ENTRY_TYPE
                        trades["timeframe"] = TIMEFRAME
                        trades["v_method"] = v_method

                    if h1_filter == "no_h1_filter":
                        no_filter_cost_trades = cost_trades
                    else:
                        no_filter_pair = trade_cache.get((direction, "no_h1_filter", v_method, exit_model))
                        no_filter_cost_trades = no_filter_pair[0] if no_filter_pair is not None else None

                    no_filter_total = len(no_filter_cost_trades) if no_filter_cost_trades is not None else len(no_filter_candidates)
                    row = _summary_metrics(cost_trades, zero_trades, no_filter_total)
                    summary_rows.append(_add_context(row, context))
                    _append_group(session_rows, cost_trades, zero_trades, no_filter_cost_trades, "session", "session", context)
                    direction_rows.append(_add_context(row, context))
                    exit_model_rows.append(_add_context(row, context))
                    v_method_rows.append(_add_context(row, context))

                    direction_cost_trades.append(cost_trades)
                    direction_zero_trades.append(zero_trades)
                    trade_cache[(direction, h1_filter, v_method, exit_model)] = (cost_trades, zero_trades)

                if direction_cost_trades:
                    combined_cost = pd.concat(direction_cost_trades, ignore_index=True)
                    combined_zero = pd.concat(direction_zero_trades, ignore_index=True)
                    if h1_filter == "no_h1_filter":
                        combined_no_filter_cost = combined_cost
                    else:
                        no_filter_parts = []
                        for direction in DIRECTIONS:
                            no_filter_pair = trade_cache.get((direction, "no_h1_filter", v_method, exit_model))
                            if no_filter_pair is not None:
                                no_filter_parts.append(no_filter_pair[0])
                        combined_no_filter_cost = pd.concat(no_filter_parts, ignore_index=True) if no_filter_parts else None

                    combined_no_filter_total = len(combined_no_filter_cost) if combined_no_filter_cost is not None else len(combined_cost)
                    context = _context("combined", h1_filter, v_method, exit_model)
                    combined_row = _summary_metrics(combined_cost, combined_zero, combined_no_filter_total)
                    summary_rows.append(_add_context(combined_row, context))
                    _append_group(session_rows, combined_cost, combined_zero, combined_no_filter_cost, "session", "session", context)
                    direction_rows.append(_add_context(combined_row, context))
                    exit_model_rows.append(_add_context(combined_row, context))
                    v_method_rows.append(_add_context(combined_row, context))

    tables = {
        "h1_filter_summary": pd.DataFrame(summary_rows),
        "h1_filter_by_session": pd.DataFrame(session_rows),
        "h1_filter_by_direction": pd.DataFrame(direction_rows),
        "h1_filter_by_exit_model": pd.DataFrame(exit_model_rows),
        "h1_filter_by_v_method": pd.DataFrame(v_method_rows),
    }

    for name, table in tables.items():
        table = _round_report(table)
        tables[name] = table
        table.to_csv(OUTPUT_DIR / ("%s.csv" % name), index=False, encoding="utf-8-sig")

    debug_rows = []
    for (direction, h1_filter), candidates in filtered_candidates.items():
        if candidates.empty:
            continue
        sample = candidates[[
            "direction",
            "entry_time",
            "h1_bar_time_used",
            "h1_bar_end_time_used",
            "h1_bar_time_used_before_entry",
            "h1_bar_end_time_used_not_after_entry",
        ]].head(50).copy()
        sample["h1_filter_name"] = h1_filter
        debug_rows.append(sample)
    if debug_rows:
        pd.concat(debug_rows, ignore_index=True).to_csv(
            OUTPUT_DIR / "h1_filter_debug_samples.csv",
            index=False,
            encoding="utf-8-sig",
        )

    summary = tables["h1_filter_summary"]
    top_cols = [
        "h1_filter_name",
        "direction",
        "v_method",
        "exit_model",
    ] + METRIC_COLS
    top = summary.sort_values("expectancy_v", ascending=False)
    print("")
    print("=== H1 FILTER COST_BASE TOP 30 ===")
    print(top[top_cols].head(30).to_string(index=False))
    print("")
    print("WROTE:", OUTPUT_DIR)
    return tables


if __name__ == "__main__":
    run()
