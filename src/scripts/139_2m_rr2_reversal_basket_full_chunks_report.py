# -*- coding: utf-8 -*-
"""Combine 3-year chunk reports for the fixed RR2 reversal basket."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = ROOT / "result" / "rr2_reversal_basket_staged"
STAGES = [
    ("2010-01-01", "2013-01-01", "20100101_20130101_cap3", 939),
    ("2013-01-01", "2016-01-01", "20130101_20160101_cap3", 935),
    ("2016-01-01", "2019-01-01", "20160101_20190101_cap3", 931),
    ("2019-01-01", "2022-01-01", "20190101_20220101_cap3", 934),
    ("2022-01-01", "2025-01-01", "20220101_20250101_cap3", 932),
    ("2025-01-01", "2026-06-17", "20250101_20260617_cap3", 454),
]
OUTPUT = RESULT_ROOT / "full_20100101_20260617_cap3"


def profit_factor(pnl: pd.Series) -> float:
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    return float(gross_profit / gross_loss) if gross_loss else float("inf")


def max_drawdown(pnl: pd.Series) -> float:
    equity = pnl.cumsum()
    return float((equity.cummax() - equity).max()) if len(equity) else 0.0


def main() -> None:
    frames = []
    chunks = []
    for start, end, stage, trading_days in STAGES:
        path = RESULT_ROOT / stage / "best_trades.csv"
        frame = pd.read_csv(path)
        frame["entry_time"] = pd.to_datetime(frame["entry_time"])
        frames.append(frame)
        pnl = pd.to_numeric(frame["net_points"], errors="coerce").fillna(0.0)
        chunks.append({
            "start": start,
            "end": end,
            "trades": len(frame),
            "trading_days": trading_days,
            "trades_per_day": len(frame) / trading_days,
            "net_points": pnl.sum(),
            "profit_factor": profit_factor(pnl),
            "max_drawdown_points": max_drawdown(pnl),
        })

    trades = pd.concat(frames, ignore_index=True).sort_values("entry_time").reset_index(drop=True)
    pnl = pd.to_numeric(trades["net_points"], errors="coerce").fillna(0.0)
    days = sum(row["trading_days"] for row in chunks)
    overall = pd.DataFrame([{
        "start": STAGES[0][0],
        "end": STAGES[-1][1],
        "trades": len(trades),
        "trading_days": days,
        "trades_per_day": len(trades) / days,
        "net_points": pnl.sum(),
        "avg_points": pnl.mean(),
        "profit_factor": profit_factor(pnl),
        "win_rate": (pnl > 0).mean() * 100,
        "target_rate": (trades["exit_reason"] == "target_2r").mean() * 100,
        "max_drawdown_points": max_drawdown(pnl),
        "positive_year_rate": (trades.groupby("year")["net_points"].sum() > 0).mean() * 100,
        "positive_month_rate": (trades.groupby("month")["net_points"].sum() > 0).mean() * 100,
    }])
    yearly = trades.groupby("year").agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        target_rate=("exit_reason", lambda s: (s == "target_2r").mean() * 100),
    ).reset_index()
    monthly = trades.groupby("month").agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        target_rate=("exit_reason", lambda s: (s == "target_2r").mean() * 100),
    ).reset_index()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUTPUT / "combined_best_trades.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(chunks).round(4).to_csv(OUTPUT / "chunk_summary.csv", index=False, encoding="utf-8-sig")
    overall.round(4).to_csv(OUTPUT / "overall_summary.csv", index=False, encoding="utf-8-sig")
    yearly.round(4).to_csv(OUTPUT / "overall_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.round(4).to_csv(OUTPUT / "overall_monthly.csv", index=False, encoding="utf-8-sig")
    print("CHUNKS")
    print(pd.DataFrame(chunks).round(4).to_string(index=False))
    print("OVERALL")
    print(overall.round(4).to_string(index=False))
    print("YEARLY")
    print(yearly.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
