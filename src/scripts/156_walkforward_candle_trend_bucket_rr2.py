# -*- coding: utf-8 -*-
"""Monthly walk-forward selector for daily-trend 15m/5m retest signal buckets."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE = ROOT / "result" / "daily_trend_adr_retest_expansion_rr2" / "full_trades.csv"
OUTPUT = ROOT / "result" / "walkforward_candle_trend_bucket_rr2"
START = "2010-01-01"
SELECTION_START = "2026-01-01"
END = "2026-06-17"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


metrics = load_module("metrics144_for_156", SCRIPT_DIR / "144_bb20_rr2_daily2_validation.py")


def load_trades() -> pd.DataFrame:
    df = pd.read_csv(SOURCE)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True).dt.tz_convert("Asia/Seoul")
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True).dt.tz_convert("Asia/Seoul")
    df["month"] = df["entry_time"].dt.strftime("%Y-%m")
    df["day"] = df["entry_time"].dt.date.astype(str)
    return df.sort_values("entry_time").reset_index(drop=True)


def add_bucket(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    out = df.copy()
    if scope == "global":
        out["bucket"] = "all"
    elif scope == "session":
        out["bucket"] = out["session"].astype(str)
    elif scope == "signal":
        out["bucket"] = out["signal_type"].astype(str)
    elif scope == "session_signal":
        out["bucket"] = out["session"].astype(str) + "|" + out["signal_type"].astype(str)
    elif scope == "session_signal_direction":
        out["bucket"] = (
            out["session"].astype(str) + "|" + out["signal_type"].astype(str)
            + "|" + out["direction"].astype(str)
        )
    else:
        raise ValueError(scope)
    return out


def bucket_stats(history: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for bucket, group in history.groupby("bucket", sort=False):
        pnl = group["net_points"].to_numpy(float)
        profit = float(pnl[pnl > 0].sum())
        loss = float(-pnl[pnl < 0].sum())
        pf = profit / loss if loss > 0 else (float("inf") if profit > 0 else 0.0)
        rows.append({
            "bucket": bucket,
            "trades": len(group),
            "net_points": float(pnl.sum()),
            "avg_points": float(pnl.mean()),
            "profit_factor": pf,
        })
    return pd.DataFrame(rows)


def walkforward_filter(
    source: pd.DataFrame,
    scope: str,
    lookback_months: int,
    minimum_trades: int,
    pf_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = add_bucket(source, scope)
    first = df["entry_time"].min().to_period("M")
    last = df["entry_time"].max().to_period("M")
    selected = []
    decisions = []
    for period in pd.period_range(first, last, freq="M"):
        month_start = pd.Timestamp(period.start_time, tz="Asia/Seoul")
        month_end = month_start + pd.offsets.MonthBegin(1)
        history_start = month_start - pd.DateOffset(months=lookback_months)
        history = df[(df["entry_time"] >= history_start) & (df["entry_time"] < month_start)]
        current = df[(df["entry_time"] >= month_start) & (df["entry_time"] < month_end)]
        if history.empty or current.empty:
            continue
        stats = bucket_stats(history)
        eligible = stats[
            (stats["trades"] >= minimum_trades)
            & (stats["profit_factor"] >= pf_threshold)
            & (stats["avg_points"] > 0)
        ]
        enabled = set(eligible["bucket"].astype(str))
        if enabled:
            selected.append(current[current["bucket"].astype(str).isin(enabled)])
        for row in stats.itertuples(index=False):
            decisions.append({
                "month": str(period), "scope": scope, "bucket": row.bucket,
                "history_start": history_start, "history_end": month_start,
                "history_trades": row.trades, "history_net": row.net_points,
                "history_pf": row.profit_factor, "enabled": str(row.bucket) in enabled,
            })
    trades = pd.concat(selected, ignore_index=True) if selected else pd.DataFrame(columns=df.columns)
    decision_df = pd.DataFrame(decisions)
    return trades.sort_values("entry_time").reset_index(drop=True), decision_df


def concurrency_cap(trades: pd.DataFrame, cap: int) -> pd.DataFrame:
    open_exits = []
    kept = []
    for idx, row in trades.sort_values("entry_time").iterrows():
        open_exits = [exit_time for exit_time in open_exits if exit_time > row["entry_time"]]
        if len(open_exits) >= cap:
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
        "trades_per_day": len(trades) / 142,
        "net_points": float(pnl.sum()),
        "profit_factor": metrics.profit_factor(pnl),
        "max_drawdown": metrics.max_drawdown(pnl),
        "win_rate": float((pnl > 0).mean() * 100),
        "positive_month_rate": float((monthly > 0).mean() * 100),
    }


def main() -> None:
    source = load_trades()
    rows = []
    best = None
    best_full = None
    best_decisions = None
    for scope in ["global", "session", "signal", "session_signal", "session_signal_direction"]:
        for lookback in [12, 24]:
            for minimum_trades in [20]:
                for pf_threshold in [1.00, 1.05]:
                    filtered, decisions = walkforward_filter(
                        source, scope, lookback, minimum_trades, pf_threshold,
                    )
                    for cap in [3, 5]:
                        trades = concurrency_cap(filtered, cap)
                        sample = metrics.select_period(trades, SELECTION_START, END)
                        row = {
                            "scope": scope, "lookback_months": lookback,
                            "minimum_trades": minimum_trades,
                            "pf_threshold": pf_threshold, "concurrency_cap": cap,
                        }
                        row.update(selection_metrics(sample))
                        row["frequency_pass"] = 1.0 <= row["trades_per_day"] <= 3.0
                        row["score"] = row["net_points"] - 0.25 * row["max_drawdown"] + 2.0 * row["positive_month_rate"]
                        rows.append(row)
                        if row["frequency_pass"] and row["net_points"] > 0 and row["profit_factor"] > 1.0:
                            rank = (row["positive_month_rate"], row["score"], row["profit_factor"])
                            if best is None or rank > (best["positive_month_rate"], best["score"], best["profit_factor"]):
                                best = row.copy()
                                best_full = trades.copy()
                                best_decisions = decisions.copy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep = pd.DataFrame(rows).sort_values(["frequency_pass", "score"], ascending=[False, False])
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None or best_full is None:
        (OUTPUT / "REPORT.md").write_text("# Walk-Forward Candle Trend Bucket RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8")
        print(sweep.head(20).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    fixed = best_full
    metrics.audit_orders(fixed)
    sample = metrics.select_period(fixed, SELECTION_START, END)
    full = metrics.select_period(fixed, START, END)
    result_rows = [metrics.summarize("selection_2026", SELECTION_START, END, 142, sample)]
    for start, end, days in metrics.SLICES:
        result_rows.append(metrics.summarize("3y_chunk", start, end, days, metrics.select_period(fixed, start, end)))
    result_rows.append(metrics.summarize("full", START, END, 5125, full))
    result = pd.DataFrame(result_rows)
    result["frequency_pass"] = result["trades_per_trading_day"].between(1.0, 3.0, inclusive="both")
    result["passed"] = result["frequency_pass"] & result["performance_pass"]
    result.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    if best_decisions is not None:
        best_decisions.to_csv(OUTPUT / "monthly_bucket_decisions.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")
    chunk_passes = int(result.loc[result["period"] == "3y_chunk", "performance_pass"].sum())
    full_performance = bool(result.loc[result["period"] == "full", "performance_pass"].iloc[0])
    final = "PASSED" if full_performance and chunk_passes == 6 else ("CONDITIONAL_PASS" if full_performance else "REJECTED")
    keys = ["scope", "lookback_months", "minimum_trades", "pf_threshold", "concurrency_cap"]
    report = [
        "# Walk-Forward Candle Trend Bucket RR2", "",
        "- Base: shifted daily SMA trend, first-15m session range, completed 5m retest candle",
        "- Monthly selector: enable buckets using only the preceding fixed lookback outcomes",
        "- Exit: prior ADR20 risk, exact 2R, 0.5-point cost",
        "- The selector observes all prior hypothetical base signals, including disabled buckets", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "Meta-parameters are selected on 2026; every monthly decision uses only earlier trades.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
