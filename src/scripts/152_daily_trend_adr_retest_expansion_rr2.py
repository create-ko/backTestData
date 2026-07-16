# -*- coding: utf-8 -*-
"""Expand daily-trend ADR entries with 15m range and 5m retest confirmation."""
from __future__ import annotations

import bisect
import importlib.util
import math
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_trend_adr_retest_expansion_rr2"
COST = 0.5
SELECTION_START = "2026-01-01"
END = "2026-06-17"
TRADING_DAYS_2026 = 142


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


hybrid = load_module("hybrid151_for_152", SCRIPT_DIR / "151_session15m_5m_hybrid_retest_rr2.py")
base = hybrid.base97
metrics = hybrid.metrics


def find_session_entry(
    bars,
    epochs,
    session,
    feature: dict,
    signal_mode: str,
    retest_window: int,
    body_min: float,
    risk_fraction: float,
    risk_floor: float,
):
    opening = base.opening_range(bars, epochs, session)
    if opening is None:
        return None
    range_high = float(opening["range_high"])
    range_low = float(opening["range_low"])
    scan_start = int(opening["end_i"])
    scan_end = bisect.bisect_left(epochs, session.next_reset_epoch)
    allowed = hybrid.trend_direction(feature)
    breakout = None
    i = scan_start
    while i < scan_end - 1:
        bar = bars[i]
        if breakout is None:
            direction = None
            level = None
            if bar.close > range_high and hybrid.body_ratio(bar) >= body_min:
                direction, level = "long", range_high
            elif bar.close < range_low and hybrid.body_ratio(bar) >= body_min:
                direction, level = "short", range_low
            if direction is not None:
                breakout = {"index": i, "direction": direction, "level": level}
            i += 1
            continue

        if i - breakout["index"] > retest_window:
            breakout = None
            continue
        breakout_direction = str(breakout["direction"])
        level = float(breakout["level"])
        if breakout_direction == "long":
            continuation = bar.low <= level and bar.close >= level
            failed = bar.close < range_high
        else:
            continuation = bar.high >= level and bar.close <= level
            failed = bar.close > range_low

        candidate_direction = None
        signal_type = None
        if continuation and breakout_direction == allowed and signal_mode in {"continuation", "either"}:
            candidate_direction = allowed
            signal_type = "continuation_retest"
        elif failed and breakout_direction != allowed and signal_mode in {"failed", "either"}:
            candidate_direction = allowed
            signal_type = "counter_break_failure"
        if candidate_direction is None:
            if failed or continuation:
                breakout = None
            i += 1
            continue

        entry_i = i + 1
        if entry_i >= scan_end:
            return None
        entry = float(bars[entry_i].open)
        risk = max(risk_floor, float(feature["adr20"]) * risk_fraction)
        if not math.isfinite(risk) or risk <= 0:
            return None
        stop = entry - risk if allowed == "long" else entry + risk
        target = entry + 2.0 * risk if allowed == "long" else entry - 2.0 * risk
        ts = pd.Timestamp(base.kst_dt(bars[entry_i].epoch))
        return {
            "entry_i": entry_i,
            "entry_time": ts,
            "entry_price": entry,
            "direction": allowed,
            "stop_price": stop,
            "target_price": target,
            "risk_points": risk,
            "signal_type": signal_type,
            "session": session.name,
            "day": str(base.kst_day(session.reset_epoch)),
            "year": ts.year,
            "month": ts.strftime("%Y-%m"),
        }
    return None


def find_entries(
    bars,
    sessions,
    features: dict,
    start_day: str,
    end_day: str,
    signal_mode: str,
    retest_window: int,
    body_min: float,
    risk_fraction: float,
    risk_floor: float,
) -> pd.DataFrame:
    epochs = [bar.epoch for bar in bars]
    rows = []
    for session in sessions:
        day = str(base.kst_day(session.reset_epoch))
        if day < start_day or day >= end_day or day not in features:
            continue
        row = find_session_entry(
            bars, epochs, session, features[day], signal_mode, retest_window,
            body_min, risk_fraction, risk_floor,
        )
        if row is not None:
            rows.append(row)
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def simulate(bars, entries: pd.DataFrame, max_hold_bars: int, concurrency_cap: int = 10) -> pd.DataFrame:
    rows = []
    for row in entries.itertuples(index=False):
        start = int(row.entry_i)
        end = min(len(bars) - 1, start + max_hold_bars)
        exit_i = end
        exit_price = float(bars[end].close)
        reason = "time_exit"
        for i in range(start, end + 1):
            bar = bars[i]
            if row.direction == "long":
                if bar.low <= row.stop_price:
                    exit_i, exit_price, reason = i, row.stop_price, "stop"
                    break
                if bar.high >= row.target_price:
                    exit_i, exit_price, reason = i, row.target_price, "target_2r"
                    break
            else:
                if bar.high >= row.stop_price:
                    exit_i, exit_price, reason = i, row.stop_price, "stop"
                    break
                if bar.low <= row.target_price:
                    exit_i, exit_price, reason = i, row.target_price, "target_2r"
                    break
        gross = exit_price - row.entry_price if row.direction == "long" else row.entry_price - exit_price
        rows.append({
            **row._asdict(),
            "exit_time": pd.Timestamp(base.kst_dt(bars[exit_i].epoch)),
            "gross_points": gross,
            "net_points": gross - COST,
            "r_net": (gross - COST) / row.risk_points,
            "exit_reason": reason,
            "hold_bars": exit_i - start + 1,
        })
    if not rows:
        return pd.DataFrame()
    trades = pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)
    open_exits = []
    kept = []
    for idx, row in trades.iterrows():
        open_exits = [exit_time for exit_time in open_exits if exit_time > row["entry_time"]]
        if len(open_exits) >= concurrency_cap:
            continue
        kept.append(idx)
        open_exits.append(row["exit_time"])
    return trades.loc[kept].sort_values("entry_time").reset_index(drop=True)


def selection_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "trades": 0, "active_days": 0, "trades_per_day": 0.0,
            "net_points": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0,
            "win_rate": 0.0, "positive_month_rate": 0.0,
        }
    pnl = trades["net_points"]
    monthly = trades.groupby("month")["net_points"].sum()
    return {
        "trades": len(trades),
        "active_days": trades["day"].nunique(),
        "trades_per_day": len(trades) / TRADING_DAYS_2026,
        "net_points": pnl.sum(),
        "profit_factor": metrics.profit_factor(pnl),
        "max_drawdown": metrics.max_drawdown(pnl),
        "win_rate": (pnl > 0).mean() * 100,
        "positive_month_rate": (monthly > 0).mean() * 100,
    }


def main() -> None:
    data_path = ROOT / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"
    bars = base.load_bars(
        data_path,
        base.parse_kst("2010-01-01 00:00:00"),
        base.parse_kst("2026-06-17 00:00:00"),
    )
    sessions = base.build_session_windows(bars[0].epoch, bars[-1].epoch, 300)
    rows = []
    best = None
    feature_cache = {}
    for sma_length in [60, 120]:
        features = hybrid.daily_features(bars, sma_length)
        feature_cache[sma_length] = features
        for signal_mode in ["continuation", "failed", "either"]:
            for retest_window in [3, 6, 12]:
                for body_min in [0.0, 0.35]:
                    for risk_fraction in [0.20, 0.30, 0.50]:
                        entries = find_entries(
                            bars, sessions, features, "2025-12-31", END,
                            signal_mode, retest_window, body_min, risk_fraction, 1.5,
                        )
                        for hold in [144, 288, 576]:
                            trades = metrics.select_period(
                                simulate(bars, entries, hold), SELECTION_START, END,
                            )
                            row = {
                                "sma_length": sma_length,
                                "signal_mode": signal_mode,
                                "retest_window": retest_window,
                                "body_min": body_min,
                                "risk_fraction": risk_fraction,
                                "risk_floor": 1.5,
                                "max_hold_bars": hold,
                            }
                            row.update(selection_metrics(trades))
                            row["frequency_pass"] = 1.0 <= row["trades_per_day"] <= 3.0
                            row["score"] = row["net_points"] - 0.25 * row["max_drawdown"] + 2.0 * row["positive_month_rate"]
                            rows.append(row)
                            if row["frequency_pass"] and row["net_points"] > 0 and row["profit_factor"] > 1.0:
                                rank = (row["positive_month_rate"], row["score"], row["profit_factor"])
                                if best is None or rank > (best["positive_month_rate"], best["score"], best["profit_factor"]):
                                    best = row.copy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep = pd.DataFrame(rows).sort_values(["frequency_pass", "score"], ascending=[False, False])
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        (OUTPUT / "REPORT.md").write_text("# Daily Trend ADR Retest Expansion RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8")
        print(sweep.head(20).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    features = feature_cache[int(best["sma_length"])]
    entries = find_entries(
        bars, sessions, features, "2010-01-01", END,
        str(best["signal_mode"]), int(best["retest_window"]), float(best["body_min"]),
        float(best["risk_fraction"]), float(best["risk_floor"]),
    )
    raw = simulate(bars, entries, int(best["max_hold_bars"]))
    metrics.audit_orders(raw)
    sample = metrics.select_period(raw, SELECTION_START, END)
    full = metrics.select_period(raw, "2010-01-01", END)
    result_rows = [metrics.summarize("selection_2026", SELECTION_START, END, TRADING_DAYS_2026, sample)]
    for start, end, days in metrics.SLICES:
        result_rows.append(metrics.summarize("3y_chunk", start, end, days, metrics.select_period(raw, start, end)))
    result_rows.append(metrics.summarize("full", "2010-01-01", END, 5125, full))
    result = pd.DataFrame(result_rows)
    result["frequency_pass"] = result["trades_per_trading_day"].between(
        1.0, 3.0, inclusive="both",
    )
    result["passed"] = result["frequency_pass"] & result["performance_pass"]
    result.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "session").round(4).to_csv(OUTPUT / "full_by_session.csv", index=False, encoding="utf-8-sig")
    chunk_passes = int(result.loc[result["period"] == "3y_chunk", "performance_pass"].sum())
    full_pass = bool(result.loc[result["period"] == "full", "performance_pass"].iloc[0])
    final = "PASSED" if full_pass and chunk_passes == 6 else ("CONDITIONAL_PASS" if full_pass else "REJECTED")
    config_keys = ["sma_length", "signal_mode", "retest_window", "body_min", "risk_fraction", "risk_floor", "max_hold_bars"]
    report = [
        "# Daily Trend ADR Retest Expansion RR2", "",
        "- Direction: previous completed daily close versus shifted daily SMA",
        "- Confirmation: first 15m session range, then a completed 5m retest signal",
        "- Risk: prior 20-day ADR fraction; target: exact 2R; round-trip cost: 0.5",
        "- Selection frequency: average 1 to 3 trades per 2026 trading day", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in config_keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "Parameters are selected only on 2026 and remain fixed in every historical slice.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
