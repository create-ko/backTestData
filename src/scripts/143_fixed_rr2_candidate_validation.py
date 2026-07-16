# -*- coding: utf-8 -*-
"""Validate the single RR2 basket selected on 2026 across fixed time slices."""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = ROOT / "result"
OUTPUT = RESULT_ROOT / "fixed_rr2_candidate_validation"
ROUND_TRIP_COST = 0.5
PORTFOLIO_CAP = 5
DAILY_CAP = 3

INPUTS = {
    "immediate_sweep": RESULT_ROOT / "session_sweep_reversal_immediate_rr2_full" / "best_quality_trades.csv",
    "or_failed": RESULT_ROOT / "opening_range_failed_breakout_reversal_rr2" / "opening_range_failed_breakout_reversal_rr2_best_trades.csv",
    "pdh_pdl_double": RESULT_ROOT / "pdh_pdl_double_sweep_reversal_rr2" / "pdh_pdl_double_sweep_reversal_rr2_best_trades.csv",
}

SLICES = [
    ("2010-01-01", "2013-01-01", 939),
    ("2013-01-01", "2016-01-01", 935),
    ("2016-01-01", "2019-01-01", 931),
    ("2019-01-01", "2022-01-01", 934),
    ("2022-01-01", "2025-01-01", 932),
    ("2025-01-01", "2026-06-17", 454),
]


def load_component(name: str, path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["component"] = name
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    trades["day"] = trades["day"].astype(str)
    trades["month"] = trades["month"].astype(str)
    trades["net_points"] = pd.to_numeric(trades["net_points"], errors="raise")
    # Component simulators already deduct the requested 0.5 points.
    expected = trades["gross_points"].astype(float) - ROUND_TRIP_COST
    if not (expected - trades["net_points"]).abs().lt(1e-8).all():
        raise ValueError(f"Cost audit failed for {name}")
    return trades


def candidate_trades() -> pd.DataFrame:
    immediate = load_component("immediate_sweep", INPUTS["immediate_sweep"])
    immediate = immediate[immediate["risk_points"].astype(float) >= 2.0]
    or_failed = load_component("or_failed", INPUTS["or_failed"])
    or_failed = or_failed[or_failed["risk_points"].astype(float) >= 1.5]
    pdh = load_component("pdh_pdl_double", INPUTS["pdh_pdl_double"])
    return pd.concat([immediate, or_failed, pdh], ignore_index=True)


def dedupe(trades: pd.DataFrame) -> pd.DataFrame:
    priority = {"immediate_sweep": 0, "or_failed": 1, "pdh_pdl_double": 2}
    out = trades.copy()
    out["component_priority"] = out["component"].map(priority).astype(int)
    out["entry_key_time"] = out["entry_time"].dt.floor("2min")
    out["entry_key_price"] = out["entry_price"].astype(float).round(3)
    out["stop_key_price"] = out["stop_price"].astype(float).round(3)
    out = out.sort_values(["entry_time", "component_priority", "net_points"], ascending=[True, True, False])
    out = out.drop_duplicates(
        subset=["entry_key_time", "direction", "entry_key_price", "stop_key_price"],
        keep="first",
    )
    return out.drop(columns=["component_priority", "entry_key_time", "entry_key_price", "stop_key_price"])


def apply_portfolio_cap(trades: pd.DataFrame) -> pd.DataFrame:
    open_exits = []
    kept = []
    for idx, row in trades.sort_values("entry_time").iterrows():
        open_exits = [exit_time for exit_time in open_exits if exit_time > row["entry_time"]]
        if len(open_exits) >= PORTFOLIO_CAP:
            continue
        kept.append(idx)
        open_exits.append(row["exit_time"])
    return trades.loc[kept].sort_values("entry_time").reset_index(drop=True)


def apply_daily_cap(trades: pd.DataFrame) -> pd.DataFrame:
    ordered = trades.sort_values("entry_time")
    return ordered.groupby("day", sort=False).head(DAILY_CAP).sort_values("entry_time").reset_index(drop=True)


def select_period(raw: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start, tz="Asia/Seoul")
    end_ts = pd.Timestamp(end, tz="Asia/Seoul")
    period = raw[(raw["entry_time"] >= start_ts) & (raw["entry_time"] < end_ts)].copy()
    return apply_daily_cap(apply_portfolio_cap(dedupe(period)))


def profit_factor(pnl: pd.Series) -> float:
    gain = pnl[pnl > 0].sum()
    loss = abs(pnl[pnl < 0].sum())
    return float(gain / loss) if loss else (math.inf if gain else 0.0)


def max_drawdown(pnl: pd.Series) -> float:
    equity = pnl.cumsum()
    return float((equity.cummax() - equity).max()) if len(equity) else 0.0


def summarize(label: str, start: str, end: str, trading_days: int, trades: pd.DataFrame) -> dict:
    pnl = trades["net_points"].astype(float)
    active_days = int(trades["day"].nunique())
    return {
        "period": label,
        "start": start,
        "end": end,
        "trading_days": trading_days,
        "trades": len(trades),
        "active_days": active_days,
        "trades_per_trading_day": len(trades) / trading_days,
        "trades_per_active_day": len(trades) / active_days if active_days else 0.0,
        "net_points": pnl.sum(),
        "avg_points": pnl.mean(),
        "profit_factor": profit_factor(pnl),
        "win_rate": (pnl > 0).mean() * 100,
        "target_rate": (trades["exit_reason"] == "target_2r").mean() * 100,
        "time_exit_rate": (trades["exit_reason"] == "time_exit").mean() * 100,
        "max_drawdown_points": max_drawdown(pnl),
        "passed": bool(pnl.sum() > 0 and profit_factor(pnl) > 1.0 and 1.0 <= len(trades) / trading_days <= 3.0),
    }


def markdown_summary(summary: pd.DataFrame) -> str:
    cols = [
        "period", "start", "end", "trades", "trades_per_trading_day",
        "net_points", "profit_factor", "max_drawdown_points", "passed",
    ]
    shown = summary[cols].round(4).astype(str)
    header = "| " + " | ".join(cols) + " |"
    separator = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in shown.to_numpy().tolist()]
    return "\n".join([header, separator, *rows])


def period_breakdown(trades: pd.DataFrame, key: str) -> pd.DataFrame:
    grouped = trades.groupby(key, sort=True)
    rows = []
    for label, frame in grouped:
        pnl = frame["net_points"].astype(float)
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


def audit(trades: pd.DataFrame) -> None:
    if trades.groupby("day").size().max() > DAILY_CAP:
        raise ValueError("Daily entry cap audit failed")
    risk = trades["risk_points"].astype(float)
    long_target = trades["entry_price"].astype(float) + 2.0 * risk
    short_target = trades["entry_price"].astype(float) - 2.0 * risk
    expected_target = long_target.where(trades["direction"].eq("long"), short_target)
    if not (expected_target - trades["target_price"].astype(float)).abs().lt(1e-8).all():
        raise ValueError("Fixed 2R target audit failed")


def main() -> None:
    raw = candidate_trades()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = []
    all_frames = []
    for start, end, days in SLICES:
        trades = select_period(raw, start, end)
        rows.append(summarize("3y_chunk", start, end, days, trades))
        all_frames.append(trades)

    full = select_period(raw, "2010-01-01", "2026-06-17")
    rows.append(summarize("full", "2010-01-01", "2026-06-17", sum(x[2] for x in SLICES), full))
    sample = select_period(raw, "2026-01-01", "2026-06-17")
    rows.insert(0, summarize("selection_2026", "2026-01-01", "2026-06-17", 142, sample))

    summary = pd.DataFrame(rows)
    audit(sample)
    audit(full)
    summary.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    period_breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    period_breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_fixed_trades.csv", index=False, encoding="utf-8-sig")

    chunk_rows = summary[summary["period"] == "3y_chunk"]
    conclusion = "REJECTED" if not bool(summary.loc[summary["period"] == "full", "passed"].iloc[0]) else "PASSED"
    report = [
        "# Fixed RR2 Candidate Validation",
        "",
        "- Selection window: 2026-01-01 to 2026-06-17",
        "- Data: XAUUSD 2-minute signals with intrabar execution inherited from component tests",
        "- Orders: structural stop and fixed 2R target; round-trip cost 0.5 points",
        "- Controls: minimum risk 2.0 / 1.5 points, dedupe, max 5 concurrent positions, max 3 entries per day",
        "- Fixed candidate: immediate session sweep + opening-range failed breakout + PDH/PDL double sweep",
        "",
        "## Result",
        "",
        f"Final decision: **{conclusion}**. The candidate passed the 2026 selection window but failed fixed-parameter historical validation.",
        "",
        markdown_summary(summary),
        "",
        "## Interpretation",
        "",
        "The 2026 edge is concentrated in the recent high-volatility gold regime. Every earlier three-year chunk loses money, so the strategy is not accepted for live use. No parameters were re-selected inside the historical chunks.",
        "",
        f"Historical chunk pass count: {int(chunk_rows['passed'].sum())}/{len(chunk_rows)}.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(summary.round(4).to_string(index=False))
    print("FINAL", conclusion)


if __name__ == "__main__":
    main()
