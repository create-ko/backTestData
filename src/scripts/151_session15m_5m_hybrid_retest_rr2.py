# -*- coding: utf-8 -*-
"""15m session range plus 5m continuation/failed-retest hybrid at fixed 2R."""
from __future__ import annotations

import bisect
import importlib.util
import math
import sys
from collections import deque
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "session15m_5m_hybrid_retest_rr2"
COST = 0.5
SELECTION_START = "2026-01-01"
END = "2026-06-17"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


base97 = load_module("base97_for_151", SCRIPT_DIR / "97_strategy_session_15m_range_retest_once.py")
metrics = load_module("metrics144_for_151", SCRIPT_DIR / "144_bb20_rr2_daily2_validation.py")


def daily_features(bars, sma_length: int) -> dict:
    daily = {}
    for bar in bars:
        day = str(base97.kst_day(bar.epoch))
        row = daily.setdefault(day, {"high": bar.high, "low": bar.low, "close": bar.close})
        row["high"] = max(row["high"], bar.high)
        row["low"] = min(row["low"], bar.low)
        row["close"] = bar.close
    days = sorted(daily)
    closes = deque(maxlen=sma_length)
    ranges = deque(maxlen=20)
    out = {}
    for day in days:
        if len(closes) == sma_length and len(ranges) == 20:
            out[day] = {
                "previous_close": closes[-1],
                "sma": sum(closes) / len(closes),
                "adr20": sum(ranges) / len(ranges),
            }
        row = daily[day]
        closes.append(row["close"])
        ranges.append(row["high"] - row["low"])
    return out


def body_ratio(bar) -> float:
    span = bar.high - bar.low
    return abs(bar.close - bar.open) / span if span > 0 else 0.0


def trend_direction(feature: dict) -> str:
    return "long" if feature["previous_close"] >= feature["sma"] else "short"


def find_session_entry(
    bars,
    epochs,
    session,
    feature: dict,
    retest_window: int,
    body_min: float,
    buffer_fraction: float,
    min_risk: float,
):
    opening = base97.opening_range(bars, epochs, session)
    if opening is None:
        return None
    range_high = float(opening["range_high"])
    range_low = float(opening["range_low"])
    scan_start = int(opening["end_i"])
    scan_end = bisect.bisect_left(epochs, session.next_reset_epoch)
    allowed = trend_direction(feature)
    breakout = None
    i = scan_start
    while i < scan_end - 1:
        bar = bars[i]
        if breakout is None:
            direction = None
            level = None
            if bar.close > range_high and body_ratio(bar) >= body_min:
                direction, level = "long", range_high
            elif bar.close < range_low and body_ratio(bar) >= body_min:
                direction, level = "short", range_low
            if direction is not None:
                breakout = {"index": i, "direction": direction, "level": level}
            i += 1
            continue

        if i - breakout["index"] > retest_window:
            breakout = None
            continue
        breakout_direction = breakout["direction"]
        level = float(breakout["level"])
        continuation = False
        failed = False
        if breakout_direction == "long":
            continuation = bar.low <= level and bar.close >= level
            failed = bar.close < range_high
            candidate_direction = "short" if failed else "long"
        else:
            continuation = bar.high >= level and bar.close <= level
            failed = bar.close > range_low
            candidate_direction = "long" if failed else "short"
        if not (continuation or failed):
            i += 1
            continue
        signal_type = "failed_breakout" if failed else "continuation_retest"
        if candidate_direction != allowed:
            breakout = None
            i += 1
            continue
        entry_i = i + 1
        if entry_i >= scan_end:
            return None
        entry = float(bars[entry_i].open)
        buffer_points = max(0.2, float(feature["adr20"]) * buffer_fraction)
        if candidate_direction == "long":
            stop = float(bar.low - buffer_points)
            risk = entry - stop
            target = entry + 2.0 * risk
        else:
            stop = float(bar.high + buffer_points)
            risk = stop - entry
            target = entry - 2.0 * risk
        if not math.isfinite(risk) or risk < min_risk or risk > float(feature["adr20"]) * 0.75:
            breakout = None
            i += 1
            continue
        ts = pd.Timestamp(base97.kst_dt(bars[entry_i].epoch))
        return {
            "entry_i": entry_i,
            "entry_time": ts,
            "entry_price": entry,
            "direction": candidate_direction,
            "stop_price": stop,
            "target_price": target,
            "risk_points": risk,
            "signal_type": signal_type,
            "session": session.name,
            "day": str(base97.kst_day(session.reset_epoch)),
            "year": ts.year,
            "month": ts.strftime("%Y-%m"),
            "session_end_i": scan_end,
        }
    return None


def find_entries(
    bars,
    sessions,
    features: dict,
    start_day: str,
    end_day: str,
    retest_window: int,
    body_min: float,
    buffer_fraction: float,
    min_risk: float,
) -> pd.DataFrame:
    epochs = [bar.epoch for bar in bars]
    rows = []
    for session in sessions:
        day = str(base97.kst_day(session.reset_epoch))
        if day < start_day or day >= end_day or day not in features:
            continue
        row = find_session_entry(
            bars, epochs, session, features[day], retest_window,
            body_min, buffer_fraction, min_risk,
        )
        if row is not None:
            rows.append(row)
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def simulate(bars, entries: pd.DataFrame, max_hold_bars: int, concurrency_cap: int) -> pd.DataFrame:
    rows = []
    for row in entries.itertuples(index=False):
        start = int(row.entry_i)
        end = min(len(bars) - 1, int(row.session_end_i) - 1, start + max_hold_bars)
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
            "exit_time": pd.Timestamp(base97.kst_dt(bars[exit_i].epoch)),
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
        return {"trades": 0, "trades_per_day": 0.0, "net_points": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0, "positive_month_rate": 0.0}
    pnl = trades["net_points"]
    monthly = trades.groupby("month")["net_points"].sum()
    return {
        "trades": len(trades),
        "active_days": trades["day"].nunique(),
        "trades_per_day": len(trades) / 142,
        "net_points": pnl.sum(),
        "profit_factor": metrics.profit_factor(pnl),
        "max_drawdown": metrics.max_drawdown(pnl),
        "win_rate": (pnl > 0).mean() * 100,
        "positive_month_rate": (monthly > 0).mean() * 100,
    }


def main() -> None:
    data_path = ROOT / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"
    start_epoch = base97.parse_kst("2010-01-01 00:00:00")
    end_epoch = base97.parse_kst("2026-06-17 00:00:00")
    bars = base97.load_bars(data_path, start_epoch, end_epoch)
    sessions = base97.build_session_windows(bars[0].epoch, bars[-1].epoch, 300)
    rows = []
    best = None
    feature_cache = {}
    for sma_length in [60, 120]:
        features = daily_features(bars, sma_length)
        feature_cache[sma_length] = features
        for retest_window in [3, 6, 12]:
            for body_min in [0.0, 0.35, 0.50]:
                for buffer_fraction in [0.0, 0.005, 0.01]:
                    for min_risk in [0.8, 1.5]:
                        entries = find_entries(
                            bars, sessions, features, SELECTION_START, END,
                            retest_window, body_min, buffer_fraction, min_risk,
                        )
                        for hold in [24, 48, 96]:
                            trades = simulate(bars, entries, hold, 5)
                            row = {
                                "sma_length": sma_length,
                                "retest_window": retest_window,
                                "body_min": body_min,
                                "buffer_fraction": buffer_fraction,
                                "min_risk": min_risk,
                                "max_hold_bars": hold,
                            }
                            row.update(selection_metrics(trades))
                            row["frequency_pass"] = 2.0 <= row["trades_per_day"] <= 3.0
                            row["score"] = row["net_points"] - 0.2 * row["max_drawdown"] + 2.0 * row["positive_month_rate"]
                            rows.append(row)
                            if row["frequency_pass"] and row["net_points"] > 0 and row["profit_factor"] > 1.0:
                                if best is None or (row["positive_month_rate"], row["score"]) > (best["positive_month_rate"], best["score"]):
                                    best = row.copy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep = pd.DataFrame(rows).sort_values(["frequency_pass", "score"], ascending=[False, False])
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        (OUTPUT / "REPORT.md").write_text("# 15m/5m Hybrid Session Retest RR2\n\nNo 2026 candidate passed frequency and performance gates.\n", encoding="utf-8")
        print(sweep.head(40).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    features = feature_cache[int(best["sma_length"])]
    entries = find_entries(
        bars, sessions, features, "2010-01-01", END,
        int(best["retest_window"]), float(best["body_min"]),
        float(best["buffer_fraction"]), float(best["min_risk"]),
    )
    raw = simulate(bars, entries, int(best["max_hold_bars"]), 5)
    metrics.audit_orders(raw)
    sample = metrics.select_period(raw, SELECTION_START, END)
    full = metrics.select_period(raw, "2010-01-01", END)
    result_rows = [metrics.summarize("selection_2026", SELECTION_START, END, 142, sample)]
    for start, end, days in metrics.SLICES:
        result_rows.append(metrics.summarize("3y_chunk", start, end, days, metrics.select_period(raw, start, end)))
    result_rows.append(metrics.summarize("full", "2010-01-01", END, 5125, full))
    result = pd.DataFrame(result_rows)
    result.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")
    by_type = full.groupby("signal_type").agg(trades=("net_points", "size"), net_points=("net_points", "sum"), avg_points=("net_points", "mean")).reset_index()
    by_type.round(4).to_csv(OUTPUT / "full_by_signal_type.csv", index=False, encoding="utf-8-sig")
    full_pass = bool(result.loc[result["period"] == "full", "passed"].iloc[0])
    chunk_passes = int(result.loc[result["period"] == "3y_chunk", "performance_pass"].sum())
    final = "CONDITIONAL_PASS" if full_pass and chunk_passes < 6 else ("PASSED" if full_pass else "REJECTED")
    report = [
        "# 15m Range + 5m Hybrid Retest RR2",
        "",
        "- Session range: first completed 15 minutes",
        "- Trigger: 5m close outside the range",
        "- Entry signal: continuation retest or failed-break return, whichever first matches prior-day trend",
        "- Entry: next 5m open; stop: signal wick plus ADR-scaled buffer; target: exact 2R",
        "- Direction: previous completed daily close versus shifted daily SMA",
        "- Cost: 0.5 points; same-bar ambiguity: stop-first; one trade per session",
        "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in ["sma_length", "retest_window", "body_min", "buffer_fraction", "min_risk", "max_hold_bars"]) + "`",
        "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.",
        "",
        metrics.markdown_table(result),
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("BY SIGNAL TYPE")
    print(by_type.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
