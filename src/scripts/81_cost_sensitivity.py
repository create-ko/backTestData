# -*- coding: utf-8 -*-
"""Cost sensitivity report for the Gold double-BB grid strategy.

This script does not change strategy logic. It reruns the existing candidate,
grid, and exit-model functions with per-execution cost inputs.
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


OUTPUT_DIR = Path(__file__).resolve().parents[2] / "result" / "cost_sensitivity"

TIMEFRAMES = ["5m", "10m"]
DIRECTIONS = ["long", "short"]
ENTRY_TYPES = ["immediate", "pullback"]
V_METHODS = ["session_opening_range", "avg_range_20"]
EXIT_MODELS = ["defensive_return_to_entry1", "split_v_targets", "conservative_psychology_model"]
MAX_ENTRIES = 3
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
    "avg_trade_cost_v",
    "cost_as_percent_of_gross_profit",
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
        # Keep running, but the constants should be reviewed if this matters.
        pass
    return commission_side_points, slippage_points


def _summary_metrics(trades: pd.DataFrame, baseline_trades: pd.DataFrame | None = None) -> dict:
    summary = prep.summarize_backtest_results(trades).iloc[0].to_dict()
    pnl = pd.to_numeric(trades["realized_pnl_v"], errors="coerce").fillna(0.0)
    gross_profit = float(pnl[pnl > 0].sum())

    if baseline_trades is not None and len(baseline_trades) == len(trades):
        base_pnl = pd.to_numeric(baseline_trades["realized_pnl_v"], errors="coerce").fillna(0.0).reset_index(drop=True)
        cost_pnl = pnl.reset_index(drop=True)
        cost_drag = base_pnl - cost_pnl
        total_cost_v = float(cost_drag.sum())
        avg_cost_v = float(cost_drag.mean()) if len(cost_drag) else 0.0
        baseline_gross_profit = float(base_pnl[base_pnl > 0].sum())
    else:
        total_cost_v = 0.0
        avg_cost_v = 0.0
        baseline_gross_profit = gross_profit

    cost_pct = total_cost_v / baseline_gross_profit if baseline_gross_profit > 0 else math.inf
    return {
        "total_trades": summary.get("total_trades"),
        "expectancy_v": summary.get("expectancy_v"),
        "profit_factor": summary.get("profit_factor"),
        "max_drawdown_v": summary.get("max_drawdown_v"),
        "avg_trade_cost_v": avg_cost_v,
        "cost_as_percent_of_gross_profit": cost_pct,
        "flagged": bool(summary.get("expectancy_v") < 0),
    }


def _add_context(row: dict, context: dict) -> dict:
    out = dict(context)
    out.update(row)
    return out


def _append_group(rows, trades, baseline, group_col, context, value_col):
    if trades.empty or group_col not in trades.columns:
        return
    for value, group in trades.groupby(group_col, dropna=False):
        base_group = None
        if baseline is not None and group_col in baseline.columns:
            base_group = baseline.loc[group.index] if set(group.index).issubset(set(baseline.index)) else None
        row = _summary_metrics(group, base_group)
        row[value_col] = value
        rows.append(_add_context(row, context))


def _candidate_grid_cache(df):
    cache = {}
    for direction in DIRECTIONS:
        candidate_sets = FIRST_PASS._candidate_sets(df, direction)
        for entry_type, candidates in candidate_sets.items():
            if candidates.empty:
                continue
            candidates = _quiet_call(prep.add_v_metrics_to_candidates, df, candidates)
            for v_method in V_METHODS:
                grid = _quiet_call(
                    prep.simulate_grid_path,
                    df,
                    candidates,
                    v_method=v_method,
                    max_entries=MAX_ENTRIES,
                    max_holding_bars=MAX_HOLDING_BARS,
                )
                cache[(direction, entry_type, v_method)] = grid
    return cache


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    session_rows = []
    timeframe_rows = []
    entry_type_rows = []
    direction_console_rows = []

    for timeframe in TIMEFRAMES:
        df = _quiet_call(FIRST_PASS._prepare_data, timeframe)
        grid_cache = _candidate_grid_cache(df)

        for entry_type in ENTRY_TYPES:
            for v_method in V_METHODS:
                for exit_model in EXIT_MODELS:
                    scenario_direction_trades = {scenario["cost_scenario"]: [] for scenario in COST_SCENARIOS}
                    scenario_baseline_by_direction = {}

                    for direction in DIRECTIONS:
                        grid = grid_cache.get((direction, entry_type, v_method))
                        if grid is None or grid.empty:
                            continue

                        baseline_trades = None
                        for scenario in COST_SCENARIOS:
                            fee_points, slippage_points = _cost_points_per_execution(scenario)
                            trades = _quiet_call(
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
                            trades = trades.copy()
                            trades["entry_type"] = entry_type
                            trades["timeframe"] = timeframe
                            trades["cost_scenario"] = scenario["cost_scenario"]
                            trades["filled_entries_bucket"] = trades.apply(FIRST_PASS._filled_bucket, axis=1)
                            trades["bars_to_pullback_bucket"] = trades["bars_to_pullback"].map(FIRST_PASS._bars_bucket)
                            if scenario["cost_scenario"] == "cost_0":
                                baseline_trades = trades.copy()
                                scenario_baseline_by_direction[direction] = baseline_trades

                            context = {
                                "product": "Gold",
                                "period": "2010-01-01~2026-06-16",
                                "timeframe": timeframe,
                                "direction": direction,
                                "entry_type": entry_type,
                                "v_method": v_method,
                                "exit_model": exit_model,
                                "cost_scenario": scenario["cost_scenario"],
                                "commission_per_contract_round_turn": scenario["commission_per_contract_round_turn"],
                                "slippage_ticks_per_fill": scenario["slippage_ticks_per_fill"],
                                "tick_size": TICK_SIZE,
                                "tick_value": TICK_VALUE,
                                "point_value": POINT_VALUE,
                            }
                            summary_rows.append(_add_context(_summary_metrics(trades, baseline_trades), context))
                            _append_group(session_rows, trades, baseline_trades, "session", context, "session")
                            scenario_direction_trades[scenario["cost_scenario"]].append(trades)

                    for scenario in COST_SCENARIOS:
                        parts = scenario_direction_trades[scenario["cost_scenario"]]
                        if not parts:
                            continue
                        combined = pd.concat(parts, ignore_index=True)
                        base_parts = []
                        for direction in DIRECTIONS:
                            base = scenario_baseline_by_direction.get(direction)
                            if base is not None:
                                base_parts.append(base)
                        baseline_combined = pd.concat(base_parts, ignore_index=True) if base_parts else None
                        context = {
                            "product": "Gold",
                            "period": "2010-01-01~2026-06-16",
                            "timeframe": timeframe,
                            "direction": "combined",
                            "entry_type": entry_type,
                            "v_method": v_method,
                            "exit_model": exit_model,
                            "cost_scenario": scenario["cost_scenario"],
                            "commission_per_contract_round_turn": scenario["commission_per_contract_round_turn"],
                            "slippage_ticks_per_fill": scenario["slippage_ticks_per_fill"],
                            "tick_size": TICK_SIZE,
                            "tick_value": TICK_VALUE,
                            "point_value": POINT_VALUE,
                        }
                        summary_rows.append(_add_context(_summary_metrics(combined, baseline_combined), context))
                        _append_group(session_rows, combined, baseline_combined, "session", context, "session")
                        timeframe_rows.append(_add_context(_summary_metrics(combined, baseline_combined), context))
                        entry_type_rows.append(_add_context(_summary_metrics(combined, baseline_combined), context))
                        direction_console_rows.append(_add_context(_summary_metrics(combined, baseline_combined), context))

    summary = _round_report(pd.DataFrame(summary_rows))
    by_session = _round_report(pd.DataFrame(session_rows))
    by_timeframe = _round_report(pd.DataFrame(timeframe_rows))
    by_entry_type = _round_report(pd.DataFrame(entry_type_rows))

    summary.to_csv(OUTPUT_DIR / "cost_sensitivity_summary.csv", index=False, encoding="utf-8-sig")
    by_session.to_csv(OUTPUT_DIR / "cost_sensitivity_by_session.csv", index=False, encoding="utf-8-sig")
    by_timeframe.to_csv(OUTPUT_DIR / "cost_sensitivity_by_timeframe.csv", index=False, encoding="utf-8-sig")
    by_entry_type.to_csv(OUTPUT_DIR / "cost_sensitivity_by_entry_type.csv", index=False, encoding="utf-8-sig")

    print("")
    print("=== COST SENSITIVITY: top combined configs by cost_base expectancy ===")
    top = summary[
        (summary["direction"] == "combined")
        & (summary["cost_scenario"] == "cost_base")
    ].sort_values("expectancy_v", ascending=False)
    cols = ["timeframe", "entry_type", "v_method", "exit_model", "cost_scenario"] + METRIC_COLS
    print(top[cols].head(16).to_string(index=False))

    print("")
    print("=== PULLBACK VS IMMEDIATE ===")
    print(by_entry_type.groupby(["cost_scenario", "entry_type"])[METRIC_COLS].mean(numeric_only=True).round(3).to_string())

    print("")
    print("=== 5M VS 10M ===")
    print(by_timeframe.groupby(["cost_scenario", "timeframe"])[METRIC_COLS].mean(numeric_only=True).round(3).to_string())

    print("")
    print("=== SESSION ===")
    print(by_session.groupby(["cost_scenario", "session"])[METRIC_COLS].mean(numeric_only=True).round(3).to_string())

    print("")
    print("WROTE:", OUTPUT_DIR)
    return {
        "summary": summary,
        "by_session": by_session,
        "by_timeframe": by_timeframe,
        "by_entry_type": by_entry_type,
    }


if __name__ == "__main__":
    run()
