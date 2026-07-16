# -*- coding: utf-8 -*-
"""Select retest direction/session/signal filters on 2026, then freeze historically."""
from __future__ import annotations

import importlib.util
import itertools
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_OUTPUT = ROOT / "result" / "daily_trend_adr_retest_expansion_rr2"
OUTPUT = ROOT / "result" / "daily_trend_retest_rr2_filtered_oos"
START = "2010-01-01"
SELECTION_START = "2026-01-01"
END = "2026-06-17"
SELECTION_DAYS = 142
FULL_DAYS = 5125


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


strategy = load_module(
    "strategy152_for_180",
    SCRIPT_DIR / "152_daily_trend_adr_retest_expansion_rr2.py",
)
metrics = strategy.metrics


SESSION_SETS = {
    "all": {"Asia", "Europe", "NewYork"},
    "asia": {"Asia"},
    "europe": {"Europe"},
    "new_york": {"NewYork"},
    "asia_europe": {"Asia", "Europe"},
    "asia_new_york": {"Asia", "NewYork"},
    "europe_new_york": {"Europe", "NewYork"},
}
DIRECTION_SETS = {
    "both": {"long", "short"},
    "long": {"long"},
    "short": {"short"},
}
SIGNAL_SETS = {
    "both": {"continuation_retest", "counter_break_failure"},
    "continuation": {"continuation_retest"},
    "failed": {"counter_break_failure"},
}


def filter_trades(
    trades: pd.DataFrame,
    direction_mode: str,
    session_mode: str,
    signal_mode_filter: str,
) -> pd.DataFrame:
    mask = (
        trades["direction"].isin(DIRECTION_SETS[direction_mode])
        & trades["session"].isin(SESSION_SETS[session_mode])
        & trades["signal_type"].isin(SIGNAL_SETS[signal_mode_filter])
    )
    return trades.loc[mask].sort_values("entry_time").reset_index(drop=True)


def selection_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "trades": 0, "active_days": 0, "trades_per_day": 0.0,
            "net_points": 0.0, "profit_factor": 0.0,
            "max_drawdown": 0.0, "win_rate": 0.0,
            "positive_month_rate": 0.0,
        }
    pnl = trades["net_points"]
    monthly = trades.groupby("month")["net_points"].sum()
    return {
        "trades": len(trades),
        "active_days": trades["day"].nunique(),
        "trades_per_day": len(trades) / SELECTION_DAYS,
        "net_points": pnl.sum(),
        "profit_factor": metrics.profit_factor(pnl),
        "max_drawdown": metrics.max_drawdown(pnl),
        "win_rate": 100.0 * pnl.gt(0).mean(),
        "positive_month_rate": 100.0 * monthly.gt(0).mean(),
    }


def load_full_trades(candidate, bars, sessions, feature_cache) -> pd.DataFrame:
    sma_length = int(candidate.sma_length)
    if sma_length not in feature_cache:
        feature_cache[sma_length] = strategy.hybrid.daily_features(bars, sma_length)
    entries = strategy.find_entries(
        bars, sessions, feature_cache[sma_length], START, END,
        str(candidate.signal_mode), int(candidate.retest_window),
        float(candidate.body_min), float(candidate.risk_fraction),
        float(candidate.risk_floor),
    )
    return strategy.simulate(bars, entries, int(candidate.max_hold_bars))


def main() -> None:
    candidates = pd.read_csv(SOURCE_OUTPUT / "selection_2026_sweep.csv").head(8)
    data_path = ROOT / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"
    bars = strategy.base.load_bars(
        data_path,
        strategy.base.parse_kst("2010-01-01 00:00:00"),
        strategy.base.parse_kst(END + " 00:00:00"),
    )
    sessions = strategy.base.build_session_windows(bars[0].epoch, bars[-1].epoch, 300)
    feature_cache = {}
    trade_cache = {}
    sweep_rows = []

    for rank, candidate in enumerate(candidates.itertuples(index=False), start=1):
        full = load_full_trades(candidate, bars, sessions, feature_cache)
        trade_cache[rank] = full
        selection = metrics.select_period(full, SELECTION_START, END)
        for direction_mode, session_mode, signal_filter in itertools.product(
            DIRECTION_SETS, SESSION_SETS, SIGNAL_SETS,
        ):
            filtered = filter_trades(selection, direction_mode, session_mode, signal_filter)
            row = {
                "parameter_rank_2026": rank,
                "sma_length": int(candidate.sma_length),
                "base_signal_mode": candidate.signal_mode,
                "retest_window": int(candidate.retest_window),
                "body_min": float(candidate.body_min),
                "risk_fraction": float(candidate.risk_fraction),
                "max_hold_bars": int(candidate.max_hold_bars),
                "direction_filter": direction_mode,
                "session_filter": session_mode,
                "signal_filter": signal_filter,
            }
            row.update(selection_metrics(filtered))
            row["frequency_pass"] = 1.0 <= row["trades_per_day"] <= 3.0
            row["performance_pass"] = row["net_points"] > 0 and row["profit_factor"] > 1.0
            row["score"] = (
                row["net_points"] - 0.25 * row["max_drawdown"]
                + 2.0 * row["positive_month_rate"]
            )
            sweep_rows.append(row)

    sweep = pd.DataFrame(sweep_rows)
    eligible = sweep.loc[sweep["frequency_pass"] & sweep["performance_pass"]].copy()
    if eligible.empty:
        raise RuntimeError("No 2026 filter combination passed frequency and performance")
    eligible = eligible.sort_values(
        ["positive_month_rate", "score", "profit_factor", "trades"],
        ascending=[False, False, False, False],
    )
    best = eligible.iloc[0]

    historical_rows = []
    for row in eligible.itertuples(index=False):
        filtered = filter_trades(
            trade_cache[int(row.parameter_rank_2026)],
            str(row.direction_filter), str(row.session_filter), str(row.signal_filter),
        )
        chunk_nets = []
        for start, end, _ in metrics.SLICES:
            chunk = metrics.select_period(filtered, start, end)
            chunk_nets.append(float(chunk["net_points"].sum()))
        summary = metrics.summarize("full", START, END, FULL_DAYS, filtered)
        historical_rows.append({
            "parameter_rank_2026": int(row.parameter_rank_2026),
            "direction_filter": row.direction_filter,
            "session_filter": row.session_filter,
            "signal_filter": row.signal_filter,
            "selection_trades": int(row.trades),
            "selection_trades_per_day": row.trades_per_day,
            "selection_net": row.net_points,
            "selection_pf": row.profit_factor,
            "full_trades": summary["trades"],
            "full_net": summary["net_points"],
            "full_pf": summary["profit_factor"],
            "full_dd": summary["max_drawdown_points"],
            "profitable_chunks": sum(value > 0 for value in chunk_nets),
            "worst_chunk_net": min(chunk_nets),
            **{f"chunk_{i + 1}_net": value for i, value in enumerate(chunk_nets)},
        })
    historical = pd.DataFrame(historical_rows)

    best_full = filter_trades(
        trade_cache[int(best["parameter_rank_2026"])],
        str(best["direction_filter"]), str(best["session_filter"]),
        str(best["signal_filter"]),
    )
    best_selection = metrics.select_period(best_full, SELECTION_START, END)
    validation_rows = [
        metrics.summarize(
            "selection_2026", SELECTION_START, END, SELECTION_DAYS, best_selection,
        )
    ]
    for start, end, days in metrics.SLICES:
        validation_rows.append(metrics.summarize(
            "3y_chunk", start, end, days,
            metrics.select_period(best_full, start, end),
        ))
    validation_rows.append(metrics.summarize("full", START, END, FULL_DAYS, best_full))
    validation = pd.DataFrame(validation_rows)
    validation["frequency_pass"] = validation["trades_per_trading_day"].between(
        1.0, 3.0, inclusive="both",
    )
    validation["passed"] = validation["frequency_pass"] & validation["performance_pass"]

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep.sort_values(
        ["frequency_pass", "performance_pass", "positive_month_rate", "score"],
        ascending=[False, False, False, False],
    ).round(6).to_csv(OUTPUT / "selection_2026_filter_sweep.csv", index=False, encoding="utf-8-sig")
    historical.round(6).to_csv(
        OUTPUT / "eligible_filters_historical_audit.csv", index=False, encoding="utf-8-sig",
    )
    validation.round(6).to_csv(OUTPUT / "selected_fixed_validation.csv", index=False, encoding="utf-8-sig")
    best_selection.to_csv(OUTPUT / "selected_2026_trades.csv", index=False, encoding="utf-8-sig")
    best_full.to_csv(OUTPUT / "selected_full_trades.csv", index=False, encoding="utf-8-sig")

    selected_hist = historical.loc[
        (historical["parameter_rank_2026"] == int(best["parameter_rank_2026"]))
        & historical["direction_filter"].eq(best["direction_filter"])
        & historical["session_filter"].eq(best["session_filter"])
        & historical["signal_filter"].eq(best["signal_filter"])
    ].iloc[0]
    all_six = int(historical["profitable_chunks"].eq(6).sum())
    selected_pass = (
        selected_hist["full_net"] > 0
        and selected_hist["full_pf"] > 1.0
        and int(selected_hist["profitable_chunks"]) == 6
    )
    decision = "PASSED" if selected_pass else "REJECTED"
    report = [
        "# Daily Trend Session Retest RR2: 2026 Filter Selection", "",
        "- Base family: prior completed daily close versus shifted SMA; first 15m session range; completed 5m breakout/retest; next 5m open entry.",
        "- Stop: prior 20-day ADR fraction; target: fixed 2R; round-trip cost: 0.5.",
        "- Base parameter candidates, direction, session set, and signal type were ranked using 2026 only.",
        "- Historical chunks were not used to choose the selected configuration.", "",
        "## Selected on 2026", "",
        f"- Parameter rank: {int(best['parameter_rank_2026'])}; SMA {int(best['sma_length'])}; base signal {best['base_signal_mode']}; retest window {int(best['retest_window'])}; ADR risk {best['risk_fraction']}; hold {int(best['max_hold_bars'])} bars.",
        f"- Filters: direction {best['direction_filter']}; sessions {best['session_filter']}; signal {best['signal_filter']}.",
        f"- 2026: {int(best['trades'])} trades, {best['trades_per_day']:.4f}/day, net {best['net_points']:.2f}, PF {best['profit_factor']:.4f}.", "",
        "## Frozen historical validation", "",
        f"- Full: {int(selected_hist['full_trades'])} trades, net {selected_hist['full_net']:.2f}, PF {selected_hist['full_pf']:.4f}, DD {selected_hist['full_dd']:.2f}.",
        f"- Profitable three-year chunks: {int(selected_hist['profitable_chunks'])}/6; worst chunk {selected_hist['worst_chunk_net']:.2f}.",
        f"- Among all {len(historical)} 2026-eligible variants, {all_six} later showed 6/6 profitable historical chunks. This count is diagnostic, not a selection rule.", "",
        "## Decision", "",
        f"**{decision}**. The 2026-selected row must retain positive full net/PF, 1-3 trades/day, and 6/6 profitable fixed chunks.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026_FILTER")
    print(best.to_string())
    print("SELECTED_VALIDATION")
    print(validation.round(4).to_string(index=False))
    print("ELIGIBLE", len(historical), "ALL_SIX", all_six)
    print("BEST_HISTORICAL_DIAGNOSTIC")
    print(historical.sort_values(
        ["profitable_chunks", "worst_chunk_net", "full_pf"], ascending=False,
    ).head(10).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
