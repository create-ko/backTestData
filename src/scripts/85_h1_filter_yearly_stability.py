# -*- coding: utf-8 -*-
"""Year/month stability report for the strongest Gold 10m pullback candidates."""
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


OUTPUT_DIR = Path(__file__).resolve().parents[2] / "result" / "h1_filter_yearly_stability"

TIMEFRAME = "10m"
ENTRY_TYPE = "pullback"
DIRECTION = "long"
MAX_ENTRIES = 3
MAX_HOLDING_BARS = 48
V_METHOD = "avg_range_20"
EXIT_MODEL = "defensive_return_to_entry1"
H1_FILTERS = [
    "h1_ema20_slope",
    "h1_bb20_mid_slope",
    "h1_ema20_ema60_alignment",
]

COMMISSION_PER_CONTRACT_ROUND_TURN = 0.0
TICK_SIZE = 0.1
POINT_VALUE = 100.0
COST_BASE = {
    "cost_scenario": "cost_base",
    "commission_per_contract_round_turn": COMMISSION_PER_CONTRACT_ROUND_TURN,
    "slippage_ticks_per_fill": 1.0,
}


def _load_module(name: str, filename: str):
    path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIRST_PASS = _load_module("first_pass_summary", "80_first_pass_summary.py")
H1 = _load_module("h1_trend_filter_compare", "84_h1_trend_filter_compare.py")


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
    return commission_side_points, slippage_points


def _metric_row(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "total_trades": 0,
            "expectancy_v": math.nan,
            "profit_factor": math.nan,
            "max_drawdown_v": math.nan,
            "win_rate": math.nan,
            "avg_win_v": math.nan,
            "avg_loss_v": math.nan,
            "cumulative_pnl_v": 0.0,
        }
    work = trades.sort_values("entry_time").copy()
    summary = prep.summarize_backtest_results(work).iloc[0].to_dict()
    return {
        "total_trades": int(summary["total_trades"]),
        "expectancy_v": summary["expectancy_v"],
        "profit_factor": summary["profit_factor"],
        "max_drawdown_v": summary["max_drawdown_v"],
        "win_rate": summary["win_rate"],
        "avg_win_v": summary["avg_win_v"],
        "avg_loss_v": summary["avg_loss_v"],
        "cumulative_pnl_v": summary["cumulative_pnl_v"],
    }


def _rolling_metric_row(window: pd.DataFrame) -> dict:
    row = _metric_row(window)
    return {
        "rolling_12m_trades": row["total_trades"],
        "rolling_12m_expectancy_v": row["expectancy_v"],
        "rolling_12m_profit_factor": row["profit_factor"],
        "rolling_12m_max_drawdown_v": row["max_drawdown_v"],
        "rolling_12m_cumulative_pnl_v": row["cumulative_pnl_v"],
    }


def _run_filtered_trades(df: pd.DataFrame, candidates_h1: pd.DataFrame, h1_filter: str) -> pd.DataFrame:
    candidates = H1.apply_h1_filter(candidates_h1, h1_filter)
    candidates = _quiet_call(prep.add_v_metrics_to_candidates, df, candidates)
    grid = _quiet_call(
        prep.simulate_grid_path,
        df,
        candidates,
        v_method=V_METHOD,
        max_entries=MAX_ENTRIES,
        max_holding_bars=MAX_HOLDING_BARS,
    )
    fee_points, slippage_points = _cost_points_per_execution(COST_BASE)
    trades = _quiet_call(
        prep.backtest_exit_model,
        df,
        grid,
        model_name=EXIT_MODEL,
        conservative_same_bar=True,
        fee_points=fee_points,
        slippage_points=slippage_points,
        max_entries=MAX_ENTRIES,
        max_holding_bars=MAX_HOLDING_BARS,
    )
    trades = trades.copy()
    trades["h1_filter"] = h1_filter
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["year"] = trades["entry_time"].dt.year
    entry_time_naive = trades["entry_time"].dt.tz_localize(None)
    trades["year_month"] = entry_time_naive.dt.to_period("M").astype(str)
    trades["year_month_period"] = entry_time_naive.dt.to_period("M")
    return trades.sort_values("entry_time").reset_index(drop=True)


def _yearly_report(all_trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (h1_filter, year), group in all_trades.groupby(["h1_filter", "year"], sort=True):
        row = {"year": int(year), "h1_filter": h1_filter}
        row.update(_metric_row(group))
        rows.append(row)
    return pd.DataFrame(rows)


def _monthly_report(all_trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (h1_filter, year_month), group in all_trades.groupby(["h1_filter", "year_month"], sort=True):
        row = {"year_month": year_month, "h1_filter": h1_filter}
        metrics = _metric_row(group)
        row.update({
            "total_trades": metrics["total_trades"],
            "expectancy_v": metrics["expectancy_v"],
            "cumulative_pnl_v": metrics["cumulative_pnl_v"],
        })
        rows.append(row)
    return pd.DataFrame(rows)


def _rolling_12m_report(all_trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for h1_filter, trades in all_trades.groupby("h1_filter", sort=True):
        months = pd.period_range(
            trades["year_month_period"].min(),
            trades["year_month_period"].max(),
            freq="M",
        )
        for month in months[11:]:
            start = month - 11
            mask = (trades["year_month_period"] >= start) & (trades["year_month_period"] <= month)
            window = trades.loc[mask]
            row = {
                "window_end_month": str(month),
                "window_start_month": str(start),
                "h1_filter": h1_filter,
            }
            row.update(_rolling_metric_row(window))
            rows.append(row)
    return pd.DataFrame(rows)


def _positive_negative_year_ratio(yearly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for h1_filter, group in yearly.groupby("h1_filter", sort=True):
        total = len(group)
        pos = int((group["cumulative_pnl_v"] > 0).sum())
        neg = int((group["cumulative_pnl_v"] < 0).sum())
        flat = int((group["cumulative_pnl_v"] == 0).sum())
        rows.append({
            "h1_filter": h1_filter,
            "years": total,
            "positive_years": pos,
            "negative_years": neg,
            "flat_years": flat,
            "positive_year_ratio": pos / total if total else math.nan,
            "negative_year_ratio": neg / total if total else math.nan,
        })
    return pd.DataFrame(rows)


def run() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = _quiet_call(FIRST_PASS._prepare_data, TIMEFRAME)
    pullback = _quiet_call(FIRST_PASS._candidate_sets, df, DIRECTION)[ENTRY_TYPE]
    h1_features = H1.make_h1_features_from_10m(df)
    candidates_h1 = H1.attach_h1_features_to_candidates(pullback, h1_features)

    trades_by_filter = [_run_filtered_trades(df, candidates_h1, h1_filter) for h1_filter in H1_FILTERS]
    all_trades = pd.concat(trades_by_filter, ignore_index=True)

    yearly = _round_report(_yearly_report(all_trades))
    monthly = _round_report(_monthly_report(all_trades))
    rolling = _round_report(_rolling_12m_report(all_trades))
    ratios = _round_report(_positive_negative_year_ratio(yearly))

    yearly.to_csv(OUTPUT_DIR / "yearly_stability_h1_filters.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "monthly_stability_h1_filters.csv", index=False, encoding="utf-8-sig")
    rolling.to_csv(OUTPUT_DIR / "rolling_12m_stability_h1_filters.csv", index=False, encoding="utf-8-sig")
    ratios.to_csv(OUTPUT_DIR / "yearly_positive_negative_ratio_h1_filters.csv", index=False, encoding="utf-8-sig")
    all_trades.drop(columns=["year_month_period"]).to_csv(OUTPUT_DIR / "trades_h1_filter_stability_source.csv", index=False, encoding="utf-8-sig")

    worst_year = yearly.sort_values("cumulative_pnl_v", ascending=True).head(10)
    worst_month = monthly.sort_values("cumulative_pnl_v", ascending=True).head(10)
    worst_rolling = rolling.sort_values("rolling_12m_cumulative_pnl_v", ascending=True).head(10)

    print("")
    print("=== YEARLY STABILITY ===")
    print(yearly.to_string(index=False))
    print("")
    print("=== POSITIVE / NEGATIVE YEAR RATIO ===")
    print(ratios.to_string(index=False))
    print("")
    print("=== WORST YEARS BY CUMULATIVE PNL V ===")
    print(worst_year.to_string(index=False))
    print("")
    print("=== WORST MONTHS BY CUMULATIVE PNL V ===")
    print(worst_month.to_string(index=False))
    print("")
    print("=== WORST ROLLING 12M BY CUMULATIVE PNL V ===")
    print(worst_rolling.to_string(index=False))
    print("")
    print("WROTE:", OUTPUT_DIR)

    return {
        "yearly": yearly,
        "monthly": monthly,
        "rolling_12m": rolling,
        "year_ratios": ratios,
    }


if __name__ == "__main__":
    run()
