# -*- coding: utf-8 -*-
"""Validate the 2026 BB20/BB4 RR2 candidate at two to three trades per day."""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "result" / "bb20_wick_bb4_rr2_2m_20100101_20260617" / "bb20_wick_bb4_rr2_trades.csv"
OUTPUT = ROOT / "result" / "bb20_rr2_daily2_validation"
ROUND_TRIP_COST = 0.5
DAILY_CAP = 3
MIN_DAILY_AVERAGE = 2.0

SLICES = [
    ("2010-01-01", "2013-01-01", 939),
    ("2013-01-01", "2016-01-01", 935),
    ("2016-01-01", "2019-01-01", 931),
    ("2019-01-01", "2022-01-01", 934),
    ("2022-01-01", "2025-01-01", 932),
    ("2025-01-01", "2026-06-17", 454),
]


def load_trades() -> pd.DataFrame:
    trades = pd.read_csv(INPUT)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    trades["day"] = trades["day"].astype(str)
    trades["month"] = trades["month"].astype(str)
    for col in ["entry_price", "target_price", "risk_points", "gross_points", "net_points"]:
        trades[col] = pd.to_numeric(trades[col], errors="raise")
    return trades.sort_values("entry_time").reset_index(drop=True)


def audit_orders(trades: pd.DataFrame) -> None:
    expected_net = trades["gross_points"] - ROUND_TRIP_COST
    if not (expected_net - trades["net_points"]).abs().lt(1e-8).all():
        raise ValueError("Round-trip cost audit failed")
    long_target = trades["entry_price"] + 2.0 * trades["risk_points"]
    short_target = trades["entry_price"] - 2.0 * trades["risk_points"]
    expected_target = long_target.where(trades["direction"].eq("long"), short_target)
    if not (expected_target - trades["target_price"]).abs().lt(1e-8).all():
        raise ValueError("Fixed 2R target audit failed")


def select_period(raw: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start, tz="Asia/Seoul")
    end_ts = pd.Timestamp(end, tz="Asia/Seoul")
    period = raw[(raw["entry_time"] >= start_ts) & (raw["entry_time"] < end_ts)].copy()
    capped = period.groupby("day", sort=False).head(DAILY_CAP)
    return capped.sort_values("entry_time").reset_index(drop=True)


def profit_factor(pnl: pd.Series) -> float:
    gain = pnl[pnl > 0].sum()
    loss = abs(pnl[pnl < 0].sum())
    return float(gain / loss) if loss else (math.inf if gain else 0.0)


def max_drawdown(pnl: pd.Series) -> float:
    equity = pnl.cumsum()
    return float((equity.cummax() - equity).max()) if len(equity) else 0.0


def summarize(label: str, start: str, end: str, trading_days: int, trades: pd.DataFrame) -> dict:
    pnl = trades["net_points"]
    active_days = int(trades["day"].nunique())
    daily_counts = trades.groupby("day").size()
    days_with_2plus = int((daily_counts >= 2).sum())
    frequency = len(trades) / trading_days
    pf = profit_factor(pnl)
    return {
        "period": label,
        "start": start,
        "end": end,
        "trading_days": trading_days,
        "trades": len(trades),
        "active_days": active_days,
        "zero_entry_days": trading_days - active_days,
        "days_with_2plus": days_with_2plus,
        "days_with_2plus_rate": days_with_2plus / trading_days * 100,
        "trades_per_trading_day": frequency,
        "trades_per_active_day": len(trades) / active_days if active_days else 0.0,
        "net_points": pnl.sum(),
        "avg_points": pnl.mean(),
        "profit_factor": pf,
        "win_rate": (pnl > 0).mean() * 100,
        "target_rate": (trades["exit_reason"] == "target_2r").mean() * 100,
        "time_exit_rate": (trades["exit_reason"] == "time_exit").mean() * 100,
        "max_drawdown_points": max_drawdown(pnl),
        "frequency_pass": bool(MIN_DAILY_AVERAGE <= frequency <= DAILY_CAP),
        "every_day_2plus": bool(days_with_2plus == trading_days),
        "performance_pass": bool(pnl.sum() > 0 and pf > 1.0),
        "passed": bool(MIN_DAILY_AVERAGE <= frequency <= DAILY_CAP and pnl.sum() > 0 and pf > 1.0),
    }


def breakdown(trades: pd.DataFrame, key: str) -> pd.DataFrame:
    rows = []
    for label, frame in trades.groupby(key, sort=True):
        pnl = frame["net_points"]
        rows.append({
            key: label,
            "trades": len(frame),
            "active_days": frame["day"].nunique(),
            "net_points": pnl.sum(),
            "profit_factor": profit_factor(pnl),
            "win_rate": (pnl > 0).mean() * 100,
            "max_drawdown_points": max_drawdown(pnl),
        })
    return pd.DataFrame(rows)


def markdown_table(summary: pd.DataFrame) -> str:
    cols = [
        "period", "start", "end", "trades", "trades_per_trading_day",
        "net_points", "profit_factor", "max_drawdown_points", "passed",
    ]
    shown = summary[cols].round(4).astype(str)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in shown.to_numpy().tolist())
    return "\n".join(lines)


def main() -> None:
    raw = load_trades()
    audit_orders(raw)
    sample = select_period(raw, "2026-01-01", "2026-06-17")
    full = select_period(raw, "2010-01-01", "2026-06-17")
    if sample.groupby("day").size().max() > DAILY_CAP or full.groupby("day").size().max() > DAILY_CAP:
        raise ValueError("Daily cap audit failed")

    rows = [summarize("selection_2026", "2026-01-01", "2026-06-17", 142, sample)]
    for start, end, days in SLICES:
        rows.append(summarize("3y_chunk", start, end, days, select_period(raw, start, end)))
    rows.append(summarize("full", "2010-01-01", "2026-06-17", 5125, full))
    summary = pd.DataFrame(rows)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary.round(4).to_csv(OUTPUT / "summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")

    selection_pass = bool(summary.loc[summary["period"] == "selection_2026", "passed"].iloc[0])
    full_pass = bool(summary.loc[summary["period"] == "full", "passed"].iloc[0])
    final = "PASSED" if selection_pass and full_pass else "REJECTED"
    report = [
        "# BB20/BB4 RR2 Daily-2 Validation",
        "",
        "- Signal: 2-minute BB20 wick breakout followed by opposite BB4 pullback entry",
        "- Exit: structural stop, fixed 2R target, maximum hold 20 bars",
        "- Cost: 0.5 points round trip",
        "- Frequency control: keep the first three entries of each trading day",
        "- Pass rule: 2.0-3.0 entries per full trading day, positive net points, PF above 1.0",
        "- Frequency interpretation: average across all trading days; every-day 2+ is reported separately",
        "",
        f"Final decision: **{final}**.",
        "",
        markdown_table(summary),
        "",
        "No parameters are re-selected inside the historical chunks.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(summary.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
