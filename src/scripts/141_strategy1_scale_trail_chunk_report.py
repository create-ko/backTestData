# -*- coding: utf-8 -*-
"""Three-year validation report for the H1 120SMA scale-out trail candidate."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "result"
STAGES = [
    ("2010-01-01", "2013-01-01", 939),
    ("2013-01-01", "2016-01-01", 935),
    ("2016-01-01", "2019-01-01", 931),
    ("2019-01-01", "2022-01-01", 934),
    ("2022-01-01", "2025-01-01", 932),
    ("2025-01-01", "2026-06-17", 454),
]
FILES = {
    "10m_scale_trail": RESULT / "strategy1_h1_breakout_120sma_scale_trail" / "strategy1_120sma_3scale_10p_trail_trades.csv",
    "10m_sma60_scale_trail": RESULT / "strategy1_h1_breakout_sma60_scale_trail_10m" / "strategy1_120sma_3scale_10p_trail_trades.csv",
    "10m_sma120_wait24": RESULT / "strategy1_h1_breakout_sma120_wait24_scale_trail_10m" / "strategy1_120sma_3scale_10p_trail_trades.csv",
    "10m_sma120_wait48": RESULT / "strategy1_h1_breakout_sma120_wait48_scale_trail_10m" / "strategy1_120sma_3scale_10p_trail_trades.csv",
    "5m_scale_trail": RESULT / "strategy1_h1_breakout_120sma_scale_trail" / "strategy1_120sma_3scale_10p_trail_trades.csv",
    "2m_long_no_time_exit": RESULT / "strategy1_h1_breakout_120sma_3scale_stop_avg5p_trail_no_time_exit" / "strategy1_120sma_3scale_10p_stop5p_close_trail_trades.csv",
}


def metrics(frame: pd.DataFrame, days: int) -> dict:
    pnl = pd.to_numeric(frame["net_points_total"], errors="coerce").fillna(0.0)
    gain = pnl[pnl > 0].sum()
    loss = abs(pnl[pnl < 0].sum())
    equity = pnl.cumsum()
    return {
        "trades": len(frame),
        "trading_days": days,
        "trades_per_day": len(frame) / days,
        "net_points": pnl.sum(),
        "profit_factor": gain / loss if loss else float("inf"),
        "win_rate": (pnl > 0).mean() * 100 if len(pnl) else 0.0,
        "max_drawdown_points": (equity.cummax() - equity).max() if len(pnl) else 0.0,
    }


def main() -> None:
    rows = []
    for name, path in FILES.items():
        trades = pd.read_csv(path)
        trades["entry_time"] = pd.to_datetime(trades["entry_time"])
        if "entry_tf" in trades.columns:
            if name in {"10m_scale_trail", "10m_sma60_scale_trail", "10m_sma120_wait24", "10m_sma120_wait48"}:
                trades = trades[trades["entry_tf"] == "10m"]
            elif name == "5m_scale_trail":
                trades = trades[trades["entry_tf"] == "5m"]
            else:
                trades = trades[(trades["entry_tf"] == "2m") & (trades["direction"] == "long")]
        for start, end, days in STAGES:
            mask = (trades["entry_time"] >= pd.Timestamp(start, tz="Asia/Seoul")) & (trades["entry_time"] < pd.Timestamp(end, tz="Asia/Seoul"))
            row = {"strategy": name, "start": start, "end": end}
            row.update(metrics(trades.loc[mask].sort_values("entry_time"), days))
            rows.append(row)
        row = {"strategy": name, "start": STAGES[0][0], "end": STAGES[-1][1]}
        row.update(metrics(trades.sort_values("entry_time"), sum(x[2] for x in STAGES)))
        rows.append(row)
    out = pd.DataFrame(rows).round(4)
    output = RESULT / "strategy1_scale_trail_chunk_validation"
    output.mkdir(parents=True, exist_ok=True)
    out.to_csv(output / "chunk_summary.csv", index=False, encoding="utf-8-sig")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
