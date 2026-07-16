# -*- coding: utf-8 -*-
"""Daily-trend, prior-ADR session entries with fixed 2R exits."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_trend_adr_session_rr2"
TARGET_SESSIONS = {"asia", "europe", "us_open"}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


base = load_module("base147_for_149", SCRIPT_DIR / "147_three_session_atr_rr2_search.py")
metrics = load_module("metrics144_for_149", SCRIPT_DIR / "144_bb20_rr2_daily2_validation.py")


def build_daily_features(df: pd.DataFrame, sma_length: int) -> pd.DataFrame:
    daily = df.groupby("kst_date", sort=True).agg(
        close=("close", "last"),
        high=("high", "max"),
        low=("low", "min"),
    )
    daily["range"] = daily["high"] - daily["low"]
    daily["sma"] = daily["close"].rolling(sma_length, min_periods=sma_length).mean()
    daily["adr20"] = daily["range"].rolling(20, min_periods=20).mean()
    # Only the previous completed trading day may inform today's entries.
    daily[["close", "sma", "adr20"]] = daily[["close", "sma", "adr20"]].shift(1)
    return daily[["close", "sma", "adr20"]]


def make_entries(
    df: pd.DataFrame,
    daily: pd.DataFrame,
    direction_mode: str,
    risk_fraction: float,
    risk_floor: float,
) -> pd.DataFrame:
    idx = df.index
    open_ = df["open"].to_numpy(float)
    session_id = df["session_id"].to_numpy(int)
    session_name = df["session_name"].astype(str).to_numpy()
    days = df["kst_date"].astype(str).to_numpy()
    starts = np.flatnonzero(np.r_[True, session_id[1:] != session_id[:-1]])
    seen = set()
    rows = []
    for start in starts:
        session = session_name[start]
        day = days[start]
        key = (day, session)
        if session not in TARGET_SESSIONS or key in seen or day not in daily.index:
            continue
        seen.add(key)
        feature = daily.loc[day]
        if not all(math.isfinite(float(feature[col])) for col in ["close", "sma", "adr20"]):
            continue
        pos = start + 1
        if pos >= len(df) or session_id[pos] != session_id[start]:
            continue
        direction = "long" if float(feature["close"]) >= float(feature["sma"]) else "short"
        if direction_mode == "fade":
            direction = "short" if direction == "long" else "long"
        risk = max(risk_floor, float(feature["adr20"]) * risk_fraction)
        entry = float(open_[pos])
        stop = entry - risk if direction == "long" else entry + risk
        target = entry + 2.0 * risk if direction == "long" else entry - 2.0 * risk
        rows.append({
            "entry_pos": pos,
            "entry_time": idx[pos],
            "entry_price": entry,
            "direction": direction,
            "risk_points": risk,
            "stop_price": stop,
            "target_price": target,
            "session_id": int(session_id[pos]),
            "session": session,
            "day": day,
            "year": int(idx[pos].year),
            "month": idx[pos].strftime("%Y-%m"),
        })
    return pd.DataFrame(rows)


def evaluate_selection(trades: pd.DataFrame) -> dict:
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
    df = base.load_data()
    sample_df = df[(df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")) & (df.index < pd.Timestamp("2026-06-17", tz="Asia/Seoul"))].copy()
    rows = []
    best = None
    for sma_length in [20, 60, 120]:
        daily = build_daily_features(df, sma_length)
        for direction_mode in ["trend", "fade"]:
            for risk_fraction in [0.10, 0.20, 0.30, 0.50]:
                for risk_floor in [0.8, 1.5]:
                    entries = make_entries(sample_df, daily, direction_mode, risk_fraction, risk_floor)
                    for hold in [240, 720, 1440]:
                        for cap in [5, 10]:
                            trades = base.simulate(sample_df, entries, hold, concurrency_cap=cap)
                            row = {
                                "sma_length": sma_length,
                                "direction_mode": direction_mode,
                                "risk_fraction": risk_fraction,
                                "risk_floor": risk_floor,
                                "max_hold_bars": hold,
                                "concurrency_cap": cap,
                            }
                            row.update(evaluate_selection(trades))
                            row["frequency_pass"] = 2.0 <= row["trades_per_day"] <= 3.0
                            row["score"] = row["net_points"] - 0.2 * row["max_drawdown"] + 2.0 * row["positive_month_rate"]
                            rows.append(row)
                            if row["frequency_pass"] and row["net_points"] > 0 and row["profit_factor"] > 1.0:
                                if best is None or (row["positive_month_rate"], row["score"]) > (best["positive_month_rate"], best["score"]):
                                    best = row.copy()

    sweep = pd.DataFrame(rows).sort_values(["frequency_pass", "score"], ascending=[False, False])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        (OUTPUT / "REPORT.md").write_text("# Daily Trend ADR Session RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8")
        print(sweep.head(30).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    daily = build_daily_features(df, int(best["sma_length"]))
    entries = make_entries(df, daily, str(best["direction_mode"]), float(best["risk_fraction"]), float(best["risk_floor"]))
    raw = base.simulate(df, entries, int(best["max_hold_bars"]), concurrency_cap=int(best["concurrency_cap"]))
    metrics.audit_orders(raw)
    sample = metrics.select_period(raw, "2026-01-01", "2026-06-17")
    full = metrics.select_period(raw, "2010-01-01", "2026-06-17")
    result_rows = [metrics.summarize("selection_2026", "2026-01-01", "2026-06-17", 142, sample)]
    for start, end, days in metrics.SLICES:
        result_rows.append(metrics.summarize("3y_chunk", start, end, days, metrics.select_period(raw, start, end)))
    result_rows.append(metrics.summarize("full", "2010-01-01", "2026-06-17", 5125, full))
    result = pd.DataFrame(result_rows)
    result.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")
    full_pass = bool(result.loc[result["period"] == "full", "passed"].iloc[0])
    chunk_passes = int(result.loc[result["period"] == "3y_chunk", "performance_pass"].sum())
    final = "CONDITIONAL_PASS" if full_pass and chunk_passes < 6 else ("PASSED" if full_pass else "REJECTED")
    report = [
        "# Daily Trend ADR Session RR2",
        "",
        "- Direction: prior completed day close versus prior daily SMA",
        "- Risk: prior 20-day ADR times a fixed fraction, with a fixed floor",
        "- Entries: first Asia, Europe, and US-open opportunity",
        "- Exit: exact 2R target, 0.5-point cost, stop-first ambiguity handling",
        "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in ["sma_length", "direction_mode", "risk_fraction", "risk_floor", "max_hold_bars", "concurrency_cap"]) + "`",
        "",
        f"Final decision: **{final}**.",
        f"Profitable three-year slices: {chunk_passes}/6.",
        "",
        metrics.markdown_table(result),
        "",
        "Daily features are shifted by one completed trading day; parameters stay fixed in all historical slices.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
