# -*- coding: utf-8 -*-
"""Compare cost-adjusted performance by max_entries.

This report keeps the existing strategy logic intact. It reruns the existing
candidate, grid, and exit-model functions while varying max_entries and
per-execution cost assumptions.
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


OUTPUT_DIR = Path(__file__).resolve().parents[2] / "result" / "max_entries_cost_compare"

TIMEFRAMES = ["5m", "10m"]
DIRECTIONS = ["long", "short"]
ENTRY_TYPES = ["immediate", "pullback"]
V_METHODS = ["session_opening_range", "avg_range_20"]
EXIT_MODELS = ["defensive_return_to_entry1", "split_v_targets", "conservative_psychology_model"]
MAX_ENTRIES_LIST = [1, 2, 3]
MAX_HOLDING_BARS = 48

# Adjust these constants for broker/exchange assumptions.
COMMISSION_PER_CONTRACT_ROUND_TURN = 0.0
TICK_SIZE = 0.1
TICK_VALUE = 10.0
POINT_VALUE = 100.0

COST_SCENARIOS = [
    {"cost_scenario": "cost_0", "commission_per_contract_round_turn": 0.0, "slippage_ticks_per_fill": 0.0},
    {"cost_scenario": "cost_light", "commission_per_contract_round_turn": COMMISSION_PER_CONTRACT_ROUND_TURN, "slippage_ticks_per_fill": 0.5},
    {"cost_scenario": "cost_base", "commission_per_contract_round_turn": COMMISSION_PER_CONTRACT_ROUND_TURN, "slippage_ticks_per_fill": 1.0},
    {"cost_scenario": "cost_stress", "commission_per_contract_round_turn": COMMISSION_PER_CONTRACT_ROUND_TURN, "slippage_ticks_per_fill": 2.0},
]

METRIC_COLS = [
    "total_trades",
    "expectancy_v",
    "profit_factor",
    "max_drawdown_v",
    "avg_fills_per_trade",
    "avg_exit_fills_per_trade",
    "avg_trade_cost_v",
    "reached_stop_ratio",
    "reached_4th_entry_ratio",
    "returned_to_entry_1_after_3_fills_ratio",
    "flagged",
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
        # TODO: Decide whether to fail hard when point/tick constants disagree.
        pass
    return commission_side_points, slippage_points


def _mean_bool(series: pd.Series) -> float:
    if series.empty:
        return math.nan
    return float(series.fillna(False).astype(bool).mean())


def _summary_metrics(trades: pd.DataFrame, baseline_trades: pd.DataFrame | None = None) -> dict:
    summary = prep.summarize_backtest_results(trades).iloc[0].to_dict()
    pnl = pd.to_numeric(trades["realized_pnl_v"], errors="coerce").fillna(0.0)

    if baseline_trades is not None and len(baseline_trades) == len(trades):
        base_pnl = pd.to_numeric(baseline_trades["realized_pnl_v"], errors="coerce").fillna(0.0).reset_index(drop=True)
        cost_pnl = pnl.reset_index(drop=True)
        cost_drag = base_pnl - cost_pnl
        avg_cost_v = float(cost_drag.mean()) if len(cost_drag) else 0.0
    else:
        avg_cost_v = 0.0

    entry_fills = pd.to_numeric(
        trades.get("entry_executions_count", trades.get("max_filled_entries", pd.Series(dtype=float))),
        errors="coerce",
    )
    exit_fills = pd.to_numeric(
        trades.get("exit_executions_count", pd.Series(dtype=float)),
        errors="coerce",
    )
    three_fill_mask = entry_fills >= 3
    if three_fill_mask.any() and "returned_to_entry_1_after_3_fills" in trades.columns:
        returned_ratio = _mean_bool(trades.loc[three_fill_mask, "returned_to_entry_1_after_3_fills"])
    else:
        returned_ratio = 0.0

    return {
        "total_trades": summary.get("total_trades"),
        "expectancy_v": summary.get("expectancy_v"),
        "profit_factor": summary.get("profit_factor"),
        "max_drawdown_v": summary.get("max_drawdown_v"),
        "avg_fills_per_trade": float(entry_fills.mean()) if len(entry_fills) else math.nan,
        "avg_exit_fills_per_trade": float(exit_fills.mean()) if len(exit_fills) else math.nan,
        "avg_trade_cost_v": avg_cost_v,
        "reached_stop_ratio": _mean_bool(trades["exit_reason"].eq("stop")) if "exit_reason" in trades.columns else math.nan,
        "reached_4th_entry_ratio": _mean_bool(trades["reached_4th_entry"]) if "reached_4th_entry" in trades.columns else math.nan,
        "returned_to_entry_1_after_3_fills_ratio": returned_ratio,
        "flagged": bool(summary.get("expectancy_v") < 0),
    }


def _add_context(row: dict, context: dict) -> dict:
    out = dict(context)
    out.update(row)
    return out


def _append_group(rows: list[dict], trades: pd.DataFrame, baseline: pd.DataFrame | None, group_col: str, context: dict, value_col: str) -> None:
    if trades.empty or group_col not in trades.columns:
        return
    for value, group in trades.groupby(group_col, dropna=False):
        base_group = baseline.loc[group.index] if baseline is not None and set(group.index).issubset(set(baseline.index)) else None
        row = _summary_metrics(group, base_group)
        row[value_col] = value
        rows.append(_add_context(row, context))


def _candidate_cache_for_timeframe(df: pd.DataFrame) -> dict[tuple[str, str], pd.DataFrame]:
    cache = {}
    for direction in DIRECTIONS:
        candidate_sets = _quiet_call(FIRST_PASS._candidate_sets, df, direction)
        for entry_type, candidates in candidate_sets.items():
            if candidates.empty:
                continue
            cache[(direction, entry_type)] = _quiet_call(prep.add_v_metrics_to_candidates, df, candidates)
    return cache


def _build_trades_for_grid(
    df: pd.DataFrame,
    grid: pd.DataFrame,
    exit_model: str,
    scenario: dict,
    max_entries: int,
    context: dict,
) -> pd.DataFrame:
    fee_points, slippage_points = _cost_points_per_execution(scenario)
    trades = _quiet_call(
        prep.backtest_exit_model,
        df,
        grid,
        model_name=exit_model,
        conservative_same_bar=True,
        fee_points=fee_points,
        slippage_points=slippage_points,
        max_entries=max_entries,
        max_holding_bars=MAX_HOLDING_BARS,
    )
    trades = trades.copy()
    trades["entry_type"] = context["entry_type"]
    trades["timeframe"] = context["timeframe"]
    trades["v_method"] = context["v_method"]
    trades["exit_model"] = exit_model
    trades["max_entries_setting"] = max_entries
    trades["cost_scenario"] = scenario["cost_scenario"]
    return trades


def _base_context(timeframe: str, direction: str, entry_type: str, v_method: str, exit_model: str, max_entries: int, scenario: dict) -> dict:
    return {
        "product": "Gold",
        "period": "2010-01-01~2026-06-16",
        "timeframe": timeframe,
        "direction": direction,
        "entry_type": entry_type,
        "v_method": v_method,
        "exit_model": exit_model,
        "max_entries": max_entries,
        "cost_scenario": scenario["cost_scenario"],
        "commission_per_contract_round_turn": scenario["commission_per_contract_round_turn"],
        "slippage_ticks_per_fill": scenario["slippage_ticks_per_fill"],
        "tick_size": TICK_SIZE,
        "tick_value": TICK_VALUE,
        "point_value": POINT_VALUE,
    }


def run() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    session_rows = []
    entry_type_rows = []
    timeframe_rows = []
    direction_rows = []
    v_method_rows = []

    for timeframe in TIMEFRAMES:
        df = _quiet_call(FIRST_PASS._prepare_data, timeframe)
        candidate_cache = _candidate_cache_for_timeframe(df)

        for max_entries in MAX_ENTRIES_LIST:
            for entry_type in ENTRY_TYPES:
                for v_method in V_METHODS:
                    grid_cache = {}
                    for direction in DIRECTIONS:
                        candidates = candidate_cache.get((direction, entry_type))
                        if candidates is None or candidates.empty:
                            continue
                        grid_cache[direction] = _quiet_call(
                            prep.simulate_grid_path,
                            df,
                            candidates,
                            v_method=v_method,
                            max_entries=max_entries,
                            max_holding_bars=MAX_HOLDING_BARS,
                        )

                    for exit_model in EXIT_MODELS:
                        scenario_trades_by_direction = {scenario["cost_scenario"]: [] for scenario in COST_SCENARIOS}
                        scenario_baseline_by_direction = {}

                        for direction in DIRECTIONS:
                            grid = grid_cache.get(direction)
                            if grid is None or grid.empty:
                                continue

                            baseline_trades = None
                            for scenario in COST_SCENARIOS:
                                context = _base_context(timeframe, direction, entry_type, v_method, exit_model, max_entries, scenario)
                                trades = _build_trades_for_grid(df, grid, exit_model, scenario, max_entries, context)
                                if trades.empty:
                                    continue
                                if scenario["cost_scenario"] == "cost_0":
                                    baseline_trades = trades.copy()
                                    scenario_baseline_by_direction[direction] = baseline_trades

                                summary_rows.append(_add_context(_summary_metrics(trades, baseline_trades), context))
                                _append_group(session_rows, trades, baseline_trades, "session", context, "session")
                                scenario_trades_by_direction[scenario["cost_scenario"]].append(trades)

                        for scenario in COST_SCENARIOS:
                            parts = scenario_trades_by_direction[scenario["cost_scenario"]]
                            if not parts:
                                continue
                            combined = pd.concat(parts, ignore_index=True)
                            baseline_parts = [scenario_baseline_by_direction[d] for d in DIRECTIONS if d in scenario_baseline_by_direction]
                            baseline_combined = pd.concat(baseline_parts, ignore_index=True) if baseline_parts else None
                            context = _base_context(timeframe, "combined", entry_type, v_method, exit_model, max_entries, scenario)

                            summary_rows.append(_add_context(_summary_metrics(combined, baseline_combined), context))
                            _append_group(session_rows, combined, baseline_combined, "session", context, "session")
                            entry_type_rows.append(_add_context(_summary_metrics(combined, baseline_combined), context))
                            timeframe_rows.append(_add_context(_summary_metrics(combined, baseline_combined), context))
                            direction_rows.append(_add_context(_summary_metrics(combined, baseline_combined), context))
                            v_method_rows.append(_add_context(_summary_metrics(combined, baseline_combined), context))

    tables = {
        "max_entries_cost_summary": pd.DataFrame(summary_rows),
        "max_entries_cost_by_session": pd.DataFrame(session_rows),
        "max_entries_cost_by_entry_type": pd.DataFrame(entry_type_rows),
        "max_entries_cost_by_timeframe": pd.DataFrame(timeframe_rows),
        "max_entries_cost_by_direction": pd.DataFrame(direction_rows),
        "max_entries_cost_by_v_method": pd.DataFrame(v_method_rows),
    }

    for name, table in tables.items():
        table = _round_report(table)
        tables[name] = table
        table.to_csv(OUTPUT_DIR / ("%s.csv" % name), index=False, encoding="utf-8-sig")

    summary = tables["max_entries_cost_summary"]
    combined = summary[summary["direction"] == "combined"].copy()

    print("")
    print("=== MAX ENTRIES COST COMPARE: combined average by scenario ===")
    print(combined.groupby(["cost_scenario", "max_entries"])[METRIC_COLS].mean(numeric_only=True).round(3).to_string())

    print("")
    print("=== COST_BASE: max_entries 2 vs 3 by entry_type/timeframe/v_method ===")
    focus = combined[
        (combined["cost_scenario"] == "cost_base")
        & (combined["max_entries"].isin([2, 3]))
    ]
    focus_cols = ["entry_type", "timeframe", "v_method", "exit_model", "max_entries"] + METRIC_COLS
    print(focus[focus_cols].sort_values(["entry_type", "timeframe", "v_method", "exit_model", "max_entries"]).to_string(index=False))

    print("")
    print("WROTE:", OUTPUT_DIR)
    return tables


if __name__ == "__main__":
    run()
