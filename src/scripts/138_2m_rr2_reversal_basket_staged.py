# -*- coding: utf-8 -*-
"""Fast staged reports for the validated low-frequency RR2 reversal basket.

Component trade files are generated once by the component research scripts.
This runner filters those trades to 2026, 2024-2026, or 2023-2026, then
deduplicates and applies the same five-position portfolio cap.
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE127 = SCRIPT_DIR / "127_2m_rr2_reversal_basket_with_extreme.py"
TEST_START = os.environ.get("TEST_START", "2026-01-01")
TEST_END = os.environ.get("TEST_END", "2026-06-17")
STAGE = os.environ.get("STAGE", TEST_START[:10].replace("-", "") + "_" + TEST_END[:10].replace("-", ""))
OUTPUT_DIR = ROOT / "result" / "rr2_reversal_basket_staged" / STAGE
MAX_TRADES_PER_DAY = int(os.environ.get("MAX_TRADES_PER_DAY", "3"))
BASKET_ONLY = os.environ.get("BASKET_ONLY", "")

spec = importlib.util.spec_from_file_location("base127_for_138", BASE127)
base127 = importlib.util.module_from_spec(spec)
sys.modules["base127_for_138"] = base127
assert spec.loader is not None
spec.loader.exec_module(base127)


def filter_period(trades: pd.DataFrame) -> pd.DataFrame:
    start = pd.Timestamp(TEST_START, tz="Asia/Seoul")
    end = pd.Timestamp(TEST_END, tz="Asia/Seoul")
    return trades[(trades["entry_time"] >= start) & (trades["entry_time"] < end)].copy()


def period_days(features: pd.DataFrame) -> int:
    start_day = TEST_START[:10]
    end_day = TEST_END[:10]
    days = features[(features["day"] >= start_day) & (features["day"] < end_day)]["day"]
    return int(days.nunique())


def write_period(prefix: str, trades: pd.DataFrame) -> None:
    if trades.empty:
        return
    trades.to_csv(OUTPUT_DIR / f"{prefix}_trades.csv", index=False, encoding="utf-8-sig")
    yearly = trades.groupby("year").agg(trades=("net_points", "size"), net_points=("net_points", "sum"), avg_points=("net_points", "mean"), target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)), avg_risk=("risk_points", "mean")).reset_index()
    monthly = trades.groupby("month").agg(trades=("net_points", "size"), net_points=("net_points", "sum"), avg_points=("net_points", "mean"), target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)), avg_risk=("risk_points", "mean")).reset_index()
    base127.base125.round_floats(yearly).to_csv(OUTPUT_DIR / f"{prefix}_yearly.csv", index=False, encoding="utf-8-sig")
    base127.base125.round_floats(monthly).to_csv(OUTPUT_DIR / f"{prefix}_monthly.csv", index=False, encoding="utf-8-sig")


def apply_daily_cap(trades: pd.DataFrame, cap: int) -> pd.DataFrame:
    if trades.empty or cap <= 0:
        return trades
    ordered = trades.sort_values("entry_time")
    kept = ordered.groupby("day", sort=False).head(cap)
    return kept.sort_values("entry_time").reset_index(drop=True)


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    features = base127.base125.daily_features()
    immediate = filter_period(base127.base125.add_regime(base127.base125.load_component(base127.base125.IMMEDIATE_INPUT, "immediate_sweep"), features))
    or_failed = filter_period(base127.base125.add_regime(base127.base125.load_component(base127.base125.OR_FAILED_INPUT, "or_failed"), features))
    pdh = filter_period(base127.base125.add_regime(base127.base125.load_component(base127.base125.PDH_PDL_INPUT, "pdh_pdl_double"), features))
    extreme = filter_period(base127.load_extreme(features))
    days = period_days(features)
    rows = []
    best_score = -math.inf
    best_trades = pd.DataFrame()
    baskets = base127.make_baskets(immediate, or_failed, pdh, extreme)
    if BASKET_ONLY:
        baskets = [(name, raw) for name, raw in baskets if name == BASKET_ONLY]
    for name, raw in baskets:
        deduped = base127.base125.dedupe(raw)
        capped = base127.base125.apply_portfolio_cap(deduped, base127.base125.PORTFOLIO_CAP)
        capped = apply_daily_cap(capped, MAX_TRADES_PER_DAY)
        metrics = base127.base125.summarize(capped, days)
        row = {"basket": name, "raw_trades": len(raw), "deduped_trades": len(deduped)}
        row.update(metrics)
        row["target_frequency"] = 1.0 <= row["trades_per_day"] <= 3.0
        row["score"] = row["net_points"] - row["max_drawdown_points"] * 0.10 + row["positive_month_rate"] * 2.0 + (100 if row["target_frequency"] else 0)
        rows.append(row)
        if row["score"] > best_score:
            best_score = row["score"]
            best_trades = capped.copy()

    summary = base127.base125.round_floats(pd.DataFrame(rows).sort_values("score", ascending=False))
    summary.to_csv(OUTPUT_DIR / "rr2_reversal_basket_staged_summary.csv", index=False, encoding="utf-8-sig")
    write_period("best", best_trades)
    summary.head(80).to_html(OUTPUT_DIR / "rr2_reversal_basket_staged_report.html", index=False)
    print("STAGE", STAGE, "DAYS", days)
    print(summary.to_string(index=False), flush=True)


if __name__ == "__main__":
    run()
