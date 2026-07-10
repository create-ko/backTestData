# -*- coding: utf-8 -*-
"""Walk-forward monthly regime check for the fixed RR2 2m BB20 wick setup.

Uses script 105 monthly results as the strategy outcome table. For each test
month after a warmup window, it chooses the best one-condition regime filter
from prior months only, then applies that filter to the next month.
"""
from __future__ import annotations

import contextlib
import io
import math
import os
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gold_data_prep as prep  # noqa: E402


BASE_RESULT_DIR = ROOT / "result" / "bb20_wick_bb4_rr2_2m_20230101_20260617"
MONTHLY_PATH = BASE_RESULT_DIR / "bb20_wick_bb4_rr2_monthly.csv"
OUTPUT_DIR = ROOT / "result" / "bb20_wick_rr2_walkforward_regime"
DATA_PATH = ROOT / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"

MIN_TRAIN_MONTHS = 12
MIN_SELECTED_TRAIN_MONTHS = 4
MIN_TRAIN_ACTIVE_TPD = 10.0
MAX_TRAIN_ACTIVE_TPD = 25.0
FEATURE_COLUMNS = os.environ.get("FEATURE_COLUMNS", "ret20,ret60,ret240,adr20,adr60,close").split(",")
QUANTILES = [float(x) for x in os.environ.get("REGIME_QUANTILES", "0.20,0.35,0.50,0.65,0.80").split(",")]


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def load_base_monthly() -> pd.DataFrame:
    if not MONTHLY_PATH.exists():
        raise FileNotFoundError("Missing monthly RR2 result: %s" % MONTHLY_PATH)
    monthly = pd.read_csv(MONTHLY_PATH)
    monthly["month"] = monthly["month"].astype(str)
    return monthly


def build_prior_month_features() -> pd.DataFrame:
    bars = quiet_call(prep.load_gold_data, DATA_PATH, timeframe="5m")
    daily = bars.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    daily["range"] = daily["high"] - daily["low"]
    rows = []
    for month in pd.period_range("2023-01", "2026-06", freq="M"):
        month_start = pd.Timestamp(month.start_time, tz="Asia/Seoul")
        prior = daily[daily.index < month_start]
        if len(prior) < 260:
            continue
        close = prior["close"]
        rows.append({
            "month": str(month),
            "ret5": float(close.iloc[-1] / close.iloc[-5] - 1.0),
            "ret20": float(close.iloc[-1] / close.iloc[-20] - 1.0),
            "ret60": float(close.iloc[-1] / close.iloc[-60] - 1.0),
            "ret120": float(close.iloc[-1] / close.iloc[-120] - 1.0),
            "ret240": float(close.iloc[-1] / close.iloc[-240] - 1.0),
            "adr5": float(prior["range"].iloc[-5:].mean()),
            "adr20": float(prior["range"].iloc[-20:].mean()),
            "adr60": float(prior["range"].iloc[-60:].mean()),
            "close": float(close.iloc[-1]),
            "above20": bool(close.iloc[-1] > close.iloc[-20:].mean()),
            "above60": bool(close.iloc[-1] > close.iloc[-60:].mean()),
            "above120": bool(close.iloc[-1] > close.iloc[-120:].mean()),
        })
    return pd.DataFrame(rows)


def candidate_conditions(data: pd.DataFrame) -> list[tuple[str, str, object]]:
    conditions: list[tuple[str, str, object]] = []
    for col in [x.strip() for x in FEATURE_COLUMNS if x.strip()]:
        vals = data[col].dropna()
        if vals.empty:
            continue
        for q in QUANTILES:
            cut = float(vals.quantile(q))
            conditions.append((col, "<=", cut))
            conditions.append((col, ">=", cut))
    for col in ["above20", "above60", "above120"]:
        conditions.append((col, "==", True))
        conditions.append((col, "==", False))
    return conditions


def condition_mask(df: pd.DataFrame, condition: tuple[str, str, object]) -> pd.Series:
    col, op, value = condition
    if op == "<=":
        return df[col] <= float(value)
    if op == ">=":
        return df[col] >= float(value)
    if op == "==":
        return df[col] == bool(value)
    raise ValueError("unknown op: %s" % op)


def condition_label(condition: tuple[str, str, object]) -> str:
    col, op, value = condition
    if isinstance(value, bool):
        return "%s %s %s" % (col, op, value)
    return "%s %s %.6f" % (col, op, float(value))


def profit_factor(months: pd.DataFrame) -> float:
    gains = float(months.loc[months["net_points"] > 0, "net_points"].sum()) if len(months) else 0.0
    losses = abs(float(months.loc[months["net_points"] < 0, "net_points"].sum())) if len(months) else 0.0
    if losses == 0:
        return math.inf if gains > 0 else 0.0
    return gains / losses


def summarize(months: pd.DataFrame) -> dict:
    trades = int(months["trades"].sum()) if len(months) else 0
    active_days = int(months["active_days"].sum()) if len(months) else 0
    net = float(months["net_points"].sum()) if len(months) else 0.0
    return {
        "months": int(len(months)),
        "trades": trades,
        "active_days": active_days,
        "trades_per_active_day": float(trades / active_days) if active_days else 0.0,
        "net_points": net,
        "avg_points": float(net / trades) if trades else 0.0,
        "profit_factor": profit_factor(months),
        "positive_month_rate": float((months["net_points"] > 0).mean() * 100) if len(months) else 0.0,
    }


def choose_condition(train: pd.DataFrame, conditions: list[tuple[str, str, object]]) -> tuple[tuple[str, str, object] | None, dict]:
    best_condition = None
    best_summary: dict | None = None
    for condition in conditions:
        selected = train[condition_mask(train, condition)]
        summary = summarize(selected)
        if summary["months"] < MIN_SELECTED_TRAIN_MONTHS:
            continue
        if not (MIN_TRAIN_ACTIVE_TPD <= summary["trades_per_active_day"] <= MAX_TRAIN_ACTIVE_TPD):
            continue
        if summary["net_points"] <= 0:
            continue
        if best_summary is None or robust_score(summary) > robust_score(best_summary):
            best_condition = condition
            best_summary = summary
    return best_condition, (best_summary or {})


def robust_score(summary: dict) -> tuple:
    return (
        summary["net_points"],
        summary["profit_factor"],
        summary["positive_month_rate"],
        summary["months"],
    )


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    monthly = load_base_monthly()
    features = build_prior_month_features()
    data = monthly.merge(features, on="month", how="inner").sort_values("month").reset_index(drop=True)
    conditions = candidate_conditions(data)

    rows = []
    for i in range(MIN_TRAIN_MONTHS, len(data)):
        train = data.iloc[:i].copy()
        test = data.iloc[[i]].copy()
        condition, train_summary = choose_condition(train, conditions)
        if condition is None:
            active = False
            label = "no_positive_training_filter"
        else:
            active = bool(condition_mask(test, condition).iloc[0])
            label = condition_label(condition)
        test_row = test.iloc[0].to_dict()
        test_row.update({
            "walkforward_active": active,
            "selected_condition": label,
            "train_months": int(len(train)),
            "train_net_points": float(train_summary.get("net_points", 0.0)),
            "train_trades_per_active_day": float(train_summary.get("trades_per_active_day", 0.0)),
            "train_profit_factor": float(train_summary.get("profit_factor", 0.0)),
            "selected_net_points": float(test_row["net_points"]) if active else 0.0,
            "selected_trades": int(test_row["trades"]) if active else 0,
            "selected_active_days": int(test_row["active_days"]) if active else 0,
        })
        rows.append(test_row)

    wf = pd.DataFrame(rows)
    selected = wf[wf["walkforward_active"]].copy()
    selected_for_summary = pd.DataFrame({
        "month": selected["month"],
        "trades": selected["selected_trades"],
        "active_days": selected["selected_active_days"],
        "net_points": selected["selected_net_points"],
    })
    summary = pd.DataFrame([
        {"mode": "baseline_no_filter_after_warmup", **summarize(data.iloc[MIN_TRAIN_MONTHS:])},
        {"mode": "walkforward_selected_months", **summarize(selected_for_summary)},
    ])

    wf.to_csv(OUTPUT_DIR / "rr2_walkforward_monthly_decisions.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "rr2_walkforward_summary.csv", index=False, encoding="utf-8-sig")

    print("=== 2M BB20 WICK RR2 WALK-FORWARD REGIME ===")
    print(summary.round(4).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
