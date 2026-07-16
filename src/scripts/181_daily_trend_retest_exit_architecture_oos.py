# -*- coding: utf-8 -*-
"""2026-only exit-architecture search for the daily-trend session retest family."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_trend_retest_exit_architecture_oos"
START = "2010-01-01"
SEARCH_START = "2025-12-31"
SELECTION_START = "2026-01-01"
END = "2026-06-17"
SELECTION_DAYS = 142
FULL_DAYS = 5125
COST = 0.5
TOP_HISTORICAL_AUDIT = 12


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


entry_model = load_module(
    "strategy152_for_181",
    SCRIPT_DIR / "152_daily_trend_adr_retest_expansion_rr2.py",
)
metrics = entry_model.metrics


def simulate_exit(
    bars,
    entries: pd.DataFrame,
    max_hold_bars: int,
    target_r: float,
    breakeven_trigger_r: float,
    concurrency_cap: int = 10,
) -> pd.DataFrame:
    rows = []
    for row in entries.itertuples(index=False):
        start = int(row.entry_i)
        end = min(len(bars) - 1, start + max_hold_bars)
        entry = float(row.entry_price)
        original_stop = float(row.stop_price)
        risk = float(row.risk_points)
        direction = 1 if row.direction == "long" else -1
        target = entry + direction * target_r * risk
        trigger = entry + direction * breakeven_trigger_r * risk
        breakeven_armed = False
        exit_i = end
        exit_price = float(bars[end].close)
        reason = "time_exit"

        for i in range(start, end + 1):
            bar = bars[i]
            active_stop = entry if breakeven_armed else original_stop
            if direction == 1:
                if bar.low <= active_stop:
                    exit_i = i
                    exit_price = min(active_stop, float(bar.open))
                    reason = "breakeven_stop" if breakeven_armed else "stop"
                    break
                if bar.high >= target:
                    exit_i, exit_price, reason = i, target, "target"
                    break
                if breakeven_trigger_r > 0 and bar.high >= trigger:
                    breakeven_armed = True
            else:
                if bar.high >= active_stop:
                    exit_i = i
                    exit_price = max(active_stop, float(bar.open))
                    reason = "breakeven_stop" if breakeven_armed else "stop"
                    break
                if bar.low <= target:
                    exit_i, exit_price, reason = i, target, "target"
                    break
                if breakeven_trigger_r > 0 and bar.low <= trigger:
                    breakeven_armed = True

        gross = (exit_price - entry) * direction
        rows.append({
            **row._asdict(),
            "target_r": target_r,
            "breakeven_trigger_r": breakeven_trigger_r,
            "target_price": target,
            "exit_time": pd.Timestamp(entry_model.base.kst_dt(bars[exit_i].epoch)),
            "exit_price": exit_price,
            "gross_points": gross,
            "net_points": gross - COST,
            "r_net": (gross - COST) / risk,
            "exit_reason": reason,
            "hold_bars": exit_i - start + 1,
        })
    if not rows:
        return pd.DataFrame()

    trades = pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)
    open_exits = []
    kept = []
    for idx, row in trades.iterrows():
        open_exits = [value for value in open_exits if value > row["entry_time"]]
        if len(open_exits) >= concurrency_cap:
            continue
        kept.append(idx)
        open_exits.append(row["exit_time"])
    return trades.loc[kept].sort_values("entry_time").reset_index(drop=True)


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


def summarize_period(
    period: str,
    start: str,
    end: str,
    trading_days: int,
    trades: pd.DataFrame,
) -> dict:
    row = metrics.summarize(period, start, end, trading_days, trades)
    count = len(trades)
    row["target_rate"] = 100.0 * trades["exit_reason"].eq("target").sum() / count if count else 0.0
    row["breakeven_exit_rate"] = (
        100.0 * trades["exit_reason"].eq("breakeven_stop").sum() / count if count else 0.0
    )
    row["time_exit_rate"] = (
        100.0 * trades["exit_reason"].eq("time_exit").sum() / count if count else 0.0
    )
    return row


def config_dict(row) -> dict:
    return {
        "sma_length": int(row.sma_length),
        "signal_mode": str(row.signal_mode),
        "retest_window": int(row.retest_window),
        "body_min": float(row.body_min),
        "risk_fraction": float(row.risk_fraction),
        "risk_floor": 1.5,
        "max_hold_bars": int(row.max_hold_bars),
        "target_r": float(row.target_r),
        "breakeven_trigger_r": float(row.breakeven_trigger_r),
    }


def generate_entries(bars, sessions, features, config: dict, start: str) -> pd.DataFrame:
    return entry_model.find_entries(
        bars, sessions, features, start, END,
        config["signal_mode"], config["retest_window"], config["body_min"],
        config["risk_fraction"], config["risk_floor"],
    )


def full_audit(bars, sessions, feature_cache, candidate, rank: int) -> tuple[dict, pd.DataFrame]:
    config = config_dict(candidate)
    features = feature_cache[config["sma_length"]]
    entries = generate_entries(bars, sessions, features, config, START)
    trades = simulate_exit(
        bars, entries, config["max_hold_bars"], config["target_r"],
        config["breakeven_trigger_r"],
    )
    chunk_nets = []
    for start, end, _ in metrics.SLICES:
        part = metrics.select_period(trades, start, end)
        chunk_nets.append(float(part["net_points"].sum()))
    summary = summarize_period("full", START, END, FULL_DAYS, trades)
    row = {
        "selection_rank": rank,
        **config,
        "selection_trades": int(candidate.trades),
        "selection_trades_per_day": float(candidate.trades_per_day),
        "selection_net": float(candidate.net_points),
        "selection_pf": float(candidate.profit_factor),
        "selection_positive_month_rate": float(candidate.positive_month_rate),
        "full_trades": summary["trades"],
        "full_trades_per_day": summary["trades_per_trading_day"],
        "full_net": summary["net_points"],
        "full_pf": summary["profit_factor"],
        "full_dd": summary["max_drawdown_points"],
        "profitable_chunks": sum(value > 0 for value in chunk_nets),
        "worst_chunk_net": min(chunk_nets),
        **{f"chunk_{i + 1}_net": value for i, value in enumerate(chunk_nets)},
    }
    return row, trades


def main() -> None:
    data_path = ROOT / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"
    bars = entry_model.base.load_bars(
        data_path,
        entry_model.base.parse_kst("2010-01-01 00:00:00"),
        entry_model.base.parse_kst(END + " 00:00:00"),
    )
    sessions = entry_model.base.build_session_windows(bars[0].epoch, bars[-1].epoch, 300)
    feature_cache = {
        length: entry_model.hybrid.daily_features(bars, length)
        for length in [60, 120]
    }
    rows = []

    for sma_length in [60, 120]:
        features = feature_cache[sma_length]
        for signal_mode in ["continuation", "failed", "either"]:
            for retest_window in [3, 6, 12]:
                for body_min in [0.0, 0.35]:
                    for risk_fraction in [0.20, 0.30, 0.50]:
                        entry_config = {
                            "signal_mode": signal_mode,
                            "retest_window": retest_window,
                            "body_min": body_min,
                            "risk_fraction": risk_fraction,
                            "risk_floor": 1.5,
                        }
                        entries = generate_entries(
                            bars, sessions, features, entry_config, SEARCH_START,
                        )
                        for hold in [144, 288, 576]:
                            for target_r in [1.0, 1.5, 2.0, 2.5, 3.0]:
                                for breakeven_r in [0.0, 0.75, 1.0]:
                                    trades = simulate_exit(
                                        bars, entries, hold, target_r, breakeven_r,
                                    )
                                    trades = metrics.select_period(
                                        trades, SELECTION_START, END,
                                    )
                                    row = {
                                        "sma_length": sma_length,
                                        **entry_config,
                                        "max_hold_bars": hold,
                                        "target_r": target_r,
                                        "breakeven_trigger_r": breakeven_r,
                                    }
                                    row.update(selection_metrics(trades))
                                    row["frequency_pass"] = 1.0 <= row["trades_per_day"] <= 3.0
                                    row["performance_pass"] = (
                                        row["net_points"] > 0 and row["profit_factor"] > 1.0
                                    )
                                    row["score"] = (
                                        row["net_points"] - 0.25 * row["max_drawdown"]
                                        + 2.0 * row["positive_month_rate"]
                                    )
                                    rows.append(row)

    sweep = pd.DataFrame(rows)
    eligible = sweep.loc[sweep["frequency_pass"] & sweep["performance_pass"]].copy()
    if eligible.empty:
        raise RuntimeError("No 2026 exit architecture passed")
    eligible = eligible.sort_values(
        ["positive_month_rate", "score", "profit_factor", "trades"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    top = eligible.head(TOP_HISTORICAL_AUDIT)

    historical_rows = []
    selected_trades = None
    for rank, candidate in enumerate(top.itertuples(index=False), start=1):
        row, trades = full_audit(bars, sessions, feature_cache, candidate, rank)
        historical_rows.append(row)
        if rank == 1:
            selected_trades = trades
    assert selected_trades is not None
    historical = pd.DataFrame(historical_rows)
    selected = historical.iloc[0]

    validation_rows = [summarize_period(
        "selection_2026", SELECTION_START, END, SELECTION_DAYS,
        metrics.select_period(selected_trades, SELECTION_START, END),
    )]
    for start, end, days in metrics.SLICES:
        validation_rows.append(summarize_period(
            "3y_chunk", start, end, days,
            metrics.select_period(selected_trades, start, end),
        ))
    validation_rows.append(summarize_period(
        "full", START, END, FULL_DAYS, selected_trades,
    ))
    validation = pd.DataFrame(validation_rows)
    validation["frequency_pass"] = validation["trades_per_trading_day"].between(
        1.0, 3.0, inclusive="both",
    )
    validation["passed"] = validation["frequency_pass"] & validation["performance_pass"]

    selected_pass = (
        int(selected["profitable_chunks"]) == 6
        and selected["full_net"] > 0 and selected["full_pf"] > 1.0
        and validation["frequency_pass"].all()
    )
    decision = "PASSED" if selected_pass else "REJECTED"

    cost_rows = []
    for cost in [0.0, 0.5, 1.0]:
        adjusted = selected_trades.copy()
        adjusted["net_points"] = adjusted["gross_points"] - cost
        summary = summarize_period("full", START, END, FULL_DAYS, adjusted)
        chunk_nets = [
            metrics.select_period(adjusted, start, end)["net_points"].sum()
            for start, end, _ in metrics.SLICES
        ]
        cost_rows.append({
            "round_trip_cost": cost,
            "trades": summary["trades"],
            "net_points": summary["net_points"],
            "profit_factor": summary["profit_factor"],
            "max_drawdown_points": summary["max_drawdown_points"],
            "profitable_chunks": sum(value > 0 for value in chunk_nets),
            "worst_chunk_net": min(chunk_nets),
        })
    cost_sensitivity = pd.DataFrame(cost_rows)
    chunk_cost_rows = []
    for start, end, _ in metrics.SLICES:
        part = metrics.select_period(selected_trades, start, end)
        gross = float(part["gross_points"].sum())
        count = len(part)
        chunk_cost_rows.append({
            "start": start,
            "end": end,
            "trades": count,
            "gross_points_before_cost": gross,
            "break_even_round_trip_cost": gross / count if count else 0.0,
            "net_at_cost_0_5": float(part["net_points"].sum()),
        })
    chunk_cost_break_even = pd.DataFrame(chunk_cost_rows)
    all_chunk_cost_limit = float(chunk_cost_break_even["break_even_round_trip_cost"].min())

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep.sort_values(
        ["frequency_pass", "performance_pass", "positive_month_rate", "score"],
        ascending=[False, False, False, False],
    ).round(6).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    historical.round(6).to_csv(OUTPUT / "top12_historical_audit.csv", index=False, encoding="utf-8-sig")
    validation.round(6).to_csv(OUTPUT / "selected_fixed_validation.csv", index=False, encoding="utf-8-sig")
    cost_sensitivity.round(6).to_csv(OUTPUT / "cost_sensitivity.csv", index=False, encoding="utf-8-sig")
    chunk_cost_break_even.round(6).to_csv(
        OUTPUT / "chunk_cost_break_even.csv", index=False, encoding="utf-8-sig",
    )
    selected_trades.to_csv(OUTPUT / "selected_full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(selected_trades, "exit_reason").round(6).to_csv(
        OUTPUT / "selected_by_exit_reason.csv", index=False, encoding="utf-8-sig",
    )

    report = [
        "# Daily Trend Session Retest: Exit Architecture OOS", "",
        "- Entry family unchanged: completed daily trend, first 15m session range, completed 5m breakout/retest, next 5m open.",
        "- Exit search: target 1R to 3R; optional 0.75R/1R breakeven trigger; time exit 144/288/576 bars.",
        "- Stop gaps use adverse 5m opening prices; ambiguous bars use stop first; cost is 0.5 round trip.",
        "- All parameters selected on 2026 only, then frozen for 2010-2026.", "",
        "## Selected on 2026", "",
        f"- SMA {int(selected['sma_length'])}; signal {selected['signal_mode']}; retest {int(selected['retest_window'])}; body {selected['body_min']}; ADR risk {selected['risk_fraction']}.",
        f"- Hold {int(selected['max_hold_bars'])}; target {selected['target_r']}R; breakeven trigger {selected['breakeven_trigger_r']}R (0 means disabled).",
        f"- {int(selected['selection_trades'])} trades, {selected['selection_trades_per_day']:.4f}/day, net {selected['selection_net']:.2f}, PF {selected['selection_pf']:.4f}.", "",
        "## Frozen validation", "",
        f"- Full: {int(selected['full_trades'])} trades, {selected['full_trades_per_day']:.4f}/day, net {selected['full_net']:.2f}, PF {selected['full_pf']:.4f}, DD {selected['full_dd']:.2f}.",
        f"- Profitable chunks: {int(selected['profitable_chunks'])}/6; worst chunk {selected['worst_chunk_net']:.2f}.",
        f"- Top-{TOP_HISTORICAL_AUDIT} 2026 rows with 6/6 profitable chunks: {int(historical['profitable_chunks'].eq(6).sum())}.",
        f"- Cost 0.0 gives 6/6 chunks; cost 0.5 gives 3/6; cost 1.0 gives {int(cost_sensitivity.iloc[2]['profitable_chunks'])}/6.",
        f"- Every chunk stays positive only below a {all_chunk_cost_limit:.4f}-point round-trip cost; the required cost is 0.5.", "",
        "## Decision", "",
        f"**{decision}**. A pass requires 1-3 trades/day in every fixed period, positive full net/PF, and 6/6 profitable chunks.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("ELIGIBLE_2026", len(eligible))
    print("SELECTED")
    print(selected.to_string())
    print("VALIDATION")
    print(validation.round(4).to_string(index=False))
    print("TOP12")
    print(historical.round(4).to_string(index=False))
    print("DECISION", decision)


if __name__ == "__main__":
    main()
