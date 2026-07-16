# -*- coding: utf-8 -*-
"""NY17 completed-daily trend plus session opening-range close breakout OOS search."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "ny17_daily_trend_session_breakout_oos"
START = "2010-01-01"
SELECTION_START = "2026-01-01"
END = "2026-06-17"
SELECTION_DAYS = 142
FULL_DAYS = 5125
COST = 0.5
TARGET_SESSIONS = {"asia", "europe", "us_open"}
TOP_AUDIT = 12


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


boundary = load_module(
    "boundary173_for_182",
    SCRIPT_DIR / "173_daily_king_keltner_boundary_sensitivity.py",
)
intraday = boundary.intraday
metrics = intraday.metrics


def build_events(
    execution: pd.DataFrame,
    timeframe: str,
    opening_bars: int,
    body_min: float,
) -> pd.DataFrame:
    signal = intraday.resample_signal_bars(execution, timeframe)
    signal["session"] = execution["session"].reindex(signal.index, method="ffill").astype(str)
    signal["day"] = signal.index.tz_convert("Asia/Seoul").date.astype(str)
    signal = signal[signal["session"].isin(TARGET_SESSIONS)].copy()
    offset = pd.tseries.frequencies.to_offset(timeframe)
    exec_index = execution.index
    rows = []

    for (day, session_name), group in signal.groupby(["day", "session"], sort=True):
        group = group.sort_index()
        if len(group) <= opening_bars:
            continue
        opening = group.iloc[:opening_bars]
        opening_high = float(opening["high"].max())
        opening_low = float(opening["low"].min())
        session_start = group.index[0]
        found = set()
        for ts, bar in group.iloc[opening_bars:].iterrows():
            span = float(bar["high"] - bar["low"])
            body_ratio = abs(float(bar["close"] - bar["open"])) / span if span > 0 else 0.0
            if body_ratio < body_min:
                continue
            directions = []
            if float(bar["close"]) > opening_high:
                directions.append("long")
            if float(bar["close"]) < opening_low:
                directions.append("short")
            for direction in directions:
                if direction in found:
                    continue
                entry_time = ts + offset
                entry_pos = int(exec_index.searchsorted(entry_time, side="left"))
                if entry_pos >= len(execution) or exec_index[entry_pos] != entry_time:
                    continue
                if str(execution["session"].iloc[entry_pos]) != session_name:
                    continue
                found.add(direction)
                rows.append({
                    "session_key": f"{day}|{session_name}",
                    "session_start": session_start,
                    "signal_time": ts,
                    "entry_pos": entry_pos,
                    "entry_time": entry_time,
                    "breakout_direction": direction,
                    "session": session_name,
                    "day": day,
                    "opening_high": opening_high,
                    "opening_low": opening_low,
                    "signal_body_ratio": body_ratio,
                })
            if len(found) == 2:
                break
    return pd.DataFrame(rows).sort_values(["session_start", "signal_time"]).reset_index(drop=True)


def make_entries(
    execution: pd.DataFrame,
    daily: pd.DataFrame,
    events: pd.DataFrame,
    ma_length: int,
    tr_length: int,
    trend_mode: str,
    risk_fraction: float,
    start: str,
) -> pd.DataFrame:
    center = daily["typical"].rolling(ma_length, min_periods=ma_length).mean().to_numpy(float)
    tr_avg = daily["tr"].rolling(tr_length, min_periods=tr_length).mean().to_numpy(float)
    close = daily["close"].to_numpy(float)
    daily_time = pd.DatetimeIndex(daily["time"])
    open_ = execution["open"].to_numpy(float)
    start_ts = pd.Timestamp(start, tz="Asia/Seoul")
    end_ts = pd.Timestamp(END, tz="Asia/Seoul")
    work = events[(events["session_start"] >= start_ts) & (events["session_start"] < end_ts)]
    rows = []

    for session_key, group in work.groupby("session_key", sort=True):
        group = group.sort_values("signal_time")
        session_start = pd.Timestamp(group["session_start"].iloc[0])
        completed_i = int(daily_time.searchsorted(session_start.tz_convert("UTC"), side="right")) - 2
        if completed_i <= 0 or completed_i >= len(daily):
            continue
        if not (
            math.isfinite(center[completed_i])
            and math.isfinite(center[completed_i - 1])
            and math.isfinite(tr_avg[completed_i])
        ):
            continue
        price_up = close[completed_i] >= center[completed_i]
        slope_up = center[completed_i] > center[completed_i - 1]
        if trend_mode == "price":
            direction = "long" if price_up else "short"
        elif trend_mode == "slope":
            direction = "long" if slope_up else "short"
        elif trend_mode == "aligned":
            if price_up != slope_up:
                continue
            direction = "long" if price_up else "short"
        else:
            raise ValueError(f"Unknown trend mode: {trend_mode}")
        matched = group[group["breakout_direction"].eq(direction)]
        if matched.empty:
            continue
        event = matched.iloc[0]
        entry_pos = int(event["entry_pos"])
        entry_price = float(open_[entry_pos])
        risk = max(2.0, float(tr_avg[completed_i]) * risk_fraction)
        if not math.isfinite(risk) or risk <= 0:
            continue
        rows.append({
            **event.to_dict(),
            "entry_price": entry_price,
            "direction": direction,
            "risk_points": risk,
            "daily_completed_time": daily_time[completed_i],
            "daily_center": center[completed_i],
            "daily_tr_average": tr_avg[completed_i],
            "year": int(pd.Timestamp(event["entry_time"]).year),
            "month": pd.Timestamp(event["entry_time"]).strftime("%Y-%m"),
        })
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def simulate(
    execution: pd.DataFrame,
    entries: pd.DataFrame,
    target_r: float,
    max_hold_bars: int,
) -> pd.DataFrame:
    if entries.empty:
        return pd.DataFrame()
    open_ = execution["open"].to_numpy(float)
    high = execution["high"].to_numpy(float)
    low = execution["low"].to_numpy(float)
    close = execution["close"].to_numpy(float)
    rows = []
    active_exit = None
    day_counts = {}

    for row in entries.itertuples(index=False):
        if active_exit is not None and row.entry_time < active_exit:
            continue
        if day_counts.get(row.day, 0) >= 3:
            continue
        direction = 1 if row.direction == "long" else -1
        stop = float(row.entry_price - direction * row.risk_points)
        target = float(row.entry_price + direction * target_r * row.risk_points)
        pos = int(row.entry_pos)
        end = min(len(execution) - 1, pos + max_hold_bars)
        exit_pos = end
        exit_price = float(close[end])
        reason = "time_exit"
        for p in range(pos, end + 1):
            if direction == 1:
                if low[p] <= stop:
                    exit_pos, exit_price, reason = p, min(stop, float(open_[p])), "stop"
                    break
                if high[p] >= target:
                    exit_pos, exit_price, reason = p, target, "target"
                    break
            else:
                if high[p] >= stop:
                    exit_pos, exit_price, reason = p, max(stop, float(open_[p])), "stop"
                    break
                if low[p] <= target:
                    exit_pos, exit_price, reason = p, target, "target"
                    break
        active_exit = execution.index[exit_pos]
        day_counts[row.day] = day_counts.get(row.day, 0) + 1
        gross = (exit_price - row.entry_price) * direction
        rows.append({
            **row._asdict(),
            "stop_price": stop,
            "target_price": target,
            "target_r": target_r,
            "exit_time": active_exit,
            "exit_price": exit_price,
            "gross_points": gross,
            "net_points": gross - COST,
            "r_net": (gross - COST) / row.risk_points,
            "exit_reason": reason,
            "hold_bars": exit_pos - pos + 1,
        })
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


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


def summarize(period, start, end, days, trades) -> dict:
    row = metrics.summarize(period, start, end, days, trades)
    count = len(trades)
    row["target_rate"] = 100.0 * trades["exit_reason"].eq("target").sum() / count if count else 0.0
    row["time_exit_rate"] = 100.0 * trades["exit_reason"].eq("time_exit").sum() / count if count else 0.0
    return row


def config_from(row) -> dict:
    return {
        "timeframe": str(row.timeframe),
        "opening_bars": int(row.opening_bars),
        "body_min": float(row.body_min),
        "ma_length": int(row.ma_length),
        "tr_length": int(row.tr_length),
        "trend_mode": str(row.trend_mode),
        "risk_fraction": float(row.risk_fraction),
        "target_r": float(row.target_r),
        "max_hold_bars": int(row.max_hold_bars),
    }


def historical_audit(execution, daily, event_cache, candidate, rank):
    config = config_from(candidate)
    events = event_cache[(config["timeframe"], config["opening_bars"], config["body_min"])]
    entries = make_entries(
        execution, daily, events, config["ma_length"], config["tr_length"],
        config["trend_mode"], config["risk_fraction"], START,
    )
    trades = simulate(execution, entries, config["target_r"], config["max_hold_bars"])
    chunk_nets = []
    for start, end, _ in metrics.SLICES:
        part = metrics.select_period(trades, start, end)
        chunk_nets.append(float(part["net_points"].sum()))
    full = summarize("full", START, END, FULL_DAYS, trades)
    row = {
        "selection_rank": rank,
        **config,
        "selection_trades": int(candidate.trades),
        "selection_trades_per_day": float(candidate.trades_per_day),
        "selection_net": float(candidate.net_points),
        "selection_pf": float(candidate.profit_factor),
        "selection_positive_month_rate": float(candidate.positive_month_rate),
        "full_trades": full["trades"],
        "full_trades_per_day": full["trades_per_trading_day"],
        "full_net": full["net_points"],
        "full_pf": full["profit_factor"],
        "full_dd": full["max_drawdown_points"],
        "profitable_chunks": sum(value > 0 for value in chunk_nets),
        "worst_chunk_net": min(chunk_nets),
        **{f"chunk_{i + 1}_net": value for i, value in enumerate(chunk_nets)},
    }
    return row, trades


def main() -> None:
    execution = intraday.prepare()
    daily = boundary.aggregate_new_york(execution, 0)
    event_specs = [("5min", 1), ("5min", 3), ("15min", 1)]
    event_cache = {
        (timeframe, opening_bars, body_min): build_events(
            execution, timeframe, opening_bars, body_min,
        )
        for timeframe, opening_bars in event_specs
        for body_min in [0.0, 0.5]
    }
    rows = []

    for timeframe, opening_bars in event_specs:
        for body_min in [0.0, 0.5]:
            events = event_cache[(timeframe, opening_bars, body_min)]
            for ma_length in [20, 50, 100]:
                for tr_length in [20, 40]:
                    for trend_mode in ["price", "slope", "aligned"]:
                        for risk_fraction in [0.10, 0.20, 0.30]:
                            entries = make_entries(
                                execution, daily, events, ma_length, tr_length,
                                trend_mode, risk_fraction, SELECTION_START,
                            )
                            for target_r in [2.0, 3.0]:
                                for hold in [72, 144, 288]:
                                    trades = simulate(execution, entries, target_r, hold)
                                    row = {
                                        "timeframe": timeframe,
                                        "opening_bars": opening_bars,
                                        "body_min": body_min,
                                        "ma_length": ma_length,
                                        "tr_length": tr_length,
                                        "trend_mode": trend_mode,
                                        "risk_fraction": risk_fraction,
                                        "target_r": target_r,
                                        "max_hold_bars": hold,
                                    }
                                    row.update(selection_metrics(trades))
                                    row["frequency_pass"] = 1.0 <= row["trades_per_day"] <= 3.0
                                    row["performance_pass"] = row["net_points"] > 0 and row["profit_factor"] > 1.0
                                    row["score"] = (
                                        row["net_points"] - 0.25 * row["max_drawdown"]
                                        + 2.0 * row["positive_month_rate"]
                                    )
                                    rows.append(row)

    sweep = pd.DataFrame(rows)
    eligible = sweep[sweep["frequency_pass"] & sweep["performance_pass"]].copy()
    if eligible.empty:
        raise RuntimeError("No 2026 session breakout candidate passed")
    eligible = eligible.sort_values(
        ["positive_month_rate", "score", "profit_factor", "trades"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    top = eligible.head(TOP_AUDIT)

    audit_rows = []
    selected_trades = None
    for rank, candidate in enumerate(top.itertuples(index=False), start=1):
        row, trades = historical_audit(execution, daily, event_cache, candidate, rank)
        audit_rows.append(row)
        if rank == 1:
            selected_trades = trades
    assert selected_trades is not None
    audit = pd.DataFrame(audit_rows)
    selected = audit.iloc[0]

    validation_rows = [summarize(
        "selection_2026", SELECTION_START, END, SELECTION_DAYS,
        metrics.select_period(selected_trades, SELECTION_START, END),
    )]
    for start, end, days in metrics.SLICES:
        validation_rows.append(summarize(
            "3y_chunk", start, end, days,
            metrics.select_period(selected_trades, start, end),
        ))
    validation_rows.append(summarize("full", START, END, FULL_DAYS, selected_trades))
    validation = pd.DataFrame(validation_rows)
    validation["frequency_pass"] = validation["trades_per_trading_day"].between(1.0, 3.0, inclusive="both")
    validation["passed"] = validation["frequency_pass"] & validation["performance_pass"]

    cost_rows = []
    for cost in [0.0, 0.5, 1.0]:
        adjusted = selected_trades.copy()
        adjusted["net_points"] = adjusted["gross_points"] - cost
        chunk_nets = [
            metrics.select_period(adjusted, start, end)["net_points"].sum()
            for start, end, _ in metrics.SLICES
        ]
        full = summarize("full", START, END, FULL_DAYS, adjusted)
        cost_rows.append({
            "round_trip_cost": cost,
            "net_points": full["net_points"],
            "profit_factor": full["profit_factor"],
            "max_drawdown_points": full["max_drawdown_points"],
            "profitable_chunks": sum(value > 0 for value in chunk_nets),
            "worst_chunk_net": min(chunk_nets),
        })
    costs = pd.DataFrame(cost_rows)
    selected_pass = (
        int(selected["profitable_chunks"]) == 6
        and selected["full_net"] > 0 and selected["full_pf"] > 1.0
        and validation["frequency_pass"].all()
    )
    decision = "PASSED" if selected_pass else "REJECTED"

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep.sort_values(
        ["frequency_pass", "performance_pass", "positive_month_rate", "score"],
        ascending=[False, False, False, False],
    ).round(6).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    audit.round(6).to_csv(OUTPUT / "top12_historical_audit.csv", index=False, encoding="utf-8-sig")
    validation.round(6).to_csv(OUTPUT / "selected_fixed_validation.csv", index=False, encoding="utf-8-sig")
    costs.round(6).to_csv(OUTPUT / "cost_sensitivity.csv", index=False, encoding="utf-8-sig")
    selected_trades.to_csv(OUTPUT / "selected_full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(selected_trades, "direction").round(6).to_csv(
        OUTPUT / "selected_by_direction.csv", index=False, encoding="utf-8-sig",
    )
    metrics.breakdown(selected_trades, "session").round(6).to_csv(
        OUTPUT / "selected_by_session.csv", index=False, encoding="utf-8-sig",
    )

    report = [
        "# NY17 Daily Trend Session Close Breakout OOS", "",
        "- Trend uses only the latest completed 17:00 America/New_York daily candle.",
        "- Signal is a completed 5m/15m candle close beyond the session opening range in the daily trend direction.",
        "- Entry is the next 5m open; one position; maximum three entries per day.",
        "- Risk is completed simple daily TR average times a fraction; target 2R/3R; adverse gaps and stop-first ambiguity; cost 0.5.",
        "- Parameters selected on 2026 only and frozen historically.", "",
        "## Selected on 2026", "",
        f"- {selected['timeframe']} bars, opening {int(selected['opening_bars'])} bars, body {selected['body_min']}; NY17 SMA {int(selected['ma_length'])} {selected['trend_mode']} trend.",
        f"- TR {int(selected['tr_length'])} x {selected['risk_fraction']} risk; target {selected['target_r']}R; hold {int(selected['max_hold_bars'])} 5m bars.",
        f"- {int(selected['selection_trades'])} trades, {selected['selection_trades_per_day']:.4f}/day, net {selected['selection_net']:.2f}, PF {selected['selection_pf']:.4f}.", "",
        "## Frozen validation", "",
        f"- Full: {int(selected['full_trades'])} trades, {selected['full_trades_per_day']:.4f}/day, net {selected['full_net']:.2f}, PF {selected['full_pf']:.4f}, DD {selected['full_dd']:.2f}.",
        f"- Profitable chunks: {int(selected['profitable_chunks'])}/6; worst chunk {selected['worst_chunk_net']:.2f}.",
        f"- Top-{TOP_AUDIT} 2026 rows with 6/6 chunks: {int(audit['profitable_chunks'].eq(6).sum())}.",
        f"- Cost 0/0.5/1.0 profitable chunks: {int(costs.iloc[0]['profitable_chunks'])}/{int(costs.iloc[1]['profitable_chunks'])}/{int(costs.iloc[2]['profitable_chunks'])} of 6.", "",
        "## Decision", "",
        f"**{decision}**. A pass requires 1-3 trades/day in every fixed period, positive full net/PF, and 6/6 profitable chunks.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("EVENT_COUNTS", {str(key): len(value) for key, value in event_cache.items()})
    print("ELIGIBLE_2026", len(eligible))
    print("SELECTED")
    print(selected.to_string())
    print("VALIDATION")
    print(validation.round(4).to_string(index=False))
    print("TOP12")
    print(audit.round(4).to_string(index=False))
    print("COSTS")
    print(costs.round(4).to_string(index=False))
    print("DECISION", decision)


if __name__ == "__main__":
    main()
