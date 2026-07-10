# -*- coding: utf-8 -*-
"""Walk-forward bucket selector for high-frequency session-liquidity RR2 trades.

The raw session-liquidity candidate reaches the requested 10-20 trades/day but
is negative. This script tests whether a NinjaScript-friendly monthly adaptive
filter can rescue it without lookahead:
- use only the prior N months of trade outcomes
- rank simple buckets such as session/level/direction/hour/risk
- trade matching buckets in the next month
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
BASE125 = SCRIPT_DIR / "125_2m_rr2_reversal_basket.py"
INPUT = ROOT / "result" / "session_liquidity_rr2_sweep" / "session_liquidity_rr2_best_trades.csv"
OUTPUT_DIR = ROOT / "result" / "session_liquidity_walkforward_bucket_selector"


spec125 = importlib.util.spec_from_file_location("base125_for_128", BASE125)
base125 = importlib.util.module_from_spec(spec125)
sys.modules["base125_for_128"] = base125
assert spec125.loader is not None
spec125.loader.exec_module(base125)


TRADING_DAYS = 1075
TRADING_DAYS_2026 = 142


BUCKET_SETS = {
    "core": ["session", "level_name", "signal_mode", "direction"],
    "core_hour": ["session", "level_name", "signal_mode", "direction", "entry_hour"],
    "core_risk": ["session", "level_name", "signal_mode", "direction", "risk_bin"],
    "core_hour_risk": ["session", "level_name", "signal_mode", "direction", "entry_hour", "risk_bin"],
    "level_hour": ["level_name", "direction", "entry_hour"],
    "signal_hour": ["session", "signal_mode", "direction", "entry_hour"],
    "regime_core": ["session", "level_name", "signal_mode", "direction", "adr60_bin", "ret60_bin"],
    "regime_hour": ["session", "signal_mode", "direction", "entry_hour", "adr60_bin", "ret60_bin"],
}


def env_int_list(name: str, default: list[int]) -> list[int]:
    raw = os.environ.get(name)
    return [int(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def env_float_list(name: str, default: list[float]) -> list[float]:
    raw = os.environ.get(name)
    return [float(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def env_str_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else default


BUCKET_NAMES = env_str_list("BUCKET_NAMES", list(BUCKET_SETS.keys()))
LOOKBACK_MONTHS_SET = env_int_list("LOOKBACK_MONTHS_SET", [1, 2, 3, 6])
MIN_TRAIN_TRADES_SET = env_int_list("MIN_TRAIN_TRADES_SET", [5, 10, 20, 40])
MIN_PF_SET = env_float_list("MIN_PF_SET", [1.0, 1.1, 1.2, 1.4])
MIN_AVG_POINTS_SET = env_float_list("MIN_AVG_POINTS_SET", [0.0, 0.05, 0.10])
TOP_N_SET = env_int_list("TOP_N_SET", [0, 20, 50, 100])


def load_trades() -> pd.DataFrame:
    trades = pd.read_csv(INPUT)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    trades["month"] = trades["month"].astype(str)
    trades["day"] = trades["day"].astype(str)
    trades["entry_hour"] = trades["entry_time"].dt.hour.astype(int)
    trades["risk_bin"] = pd.cut(
        pd.to_numeric(trades["risk_points"], errors="coerce"),
        bins=[-math.inf, 1.2, 2.0, 3.0, math.inf],
        labels=["r_le_1p2", "r_1p2_2", "r_2_3", "r_gt_3"],
    ).astype(str)
    features = base125.daily_features()
    trades = base125.add_regime(trades, features)
    trades["adr60_bin"] = pd.cut(
        pd.to_numeric(trades["adr60"], errors="coerce"),
        bins=[-math.inf, 20.0, 30.0, 40.0, math.inf],
        labels=["adr60_low", "adr60_mid", "adr60_high", "adr60_very_high"],
    ).astype(str)
    ret60 = pd.to_numeric(trades["ret60"], errors="coerce")
    trades["ret60_bin"] = pd.Series("ret60_flat", index=trades.index)
    trades.loc[ret60 <= -0.02, "ret60_bin"] = "ret60_down"
    trades.loc[ret60 >= 0.02, "ret60_bin"] = "ret60_up"
    return trades


def profit_factor(values: pd.Series) -> float:
    return base125.profit_factor(values)


def summarize(trades: pd.DataFrame, trading_days: int) -> dict:
    return base125.summarize(trades, trading_days)


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    return base125.round_floats(df)


def months_between(months: list[str], end_index: int, lookback: int) -> list[str]:
    start = max(0, end_index - lookback)
    return months[start:end_index]


def bucket_key_frame(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    return df[cols].astype(str).agg("|".join, axis=1)


def select_buckets(
    train: pd.DataFrame,
    cols: list[str],
    min_train_trades: int,
    min_pf: float,
    min_avg_points: float,
    top_n: int,
) -> set[str]:
    if train.empty:
        return set()
    keyed = train.copy()
    keyed["bucket_key"] = bucket_key_frame(keyed, cols)
    grouped = keyed.groupby("bucket_key").agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        wins=("net_points", lambda s: int((s > 0).sum())),
        pf=("net_points", profit_factor),
    ).reset_index()
    selected = grouped[
        (grouped["trades"] >= min_train_trades)
        & (grouped["net_points"] > 0)
        & (grouped["avg_points"] >= min_avg_points)
        & (grouped["pf"] >= min_pf)
    ].copy()
    if selected.empty:
        return set()
    selected["score"] = selected["net_points"] + selected["avg_points"] * 50.0 + selected["pf"].clip(upper=3.0) * 10.0
    selected = selected.sort_values("score", ascending=False)
    if top_n > 0:
        selected = selected.head(top_n)
    return set(selected["bucket_key"].astype(str))


def run_walkforward(
    trades: pd.DataFrame,
    bucket_name: str,
    cols: list[str],
    lookback_months: int,
    min_train_trades: int,
    min_pf: float,
    min_avg_points: float,
    top_n: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    months = sorted(trades["month"].unique())
    kept = []
    decisions = []
    for month_index, month in enumerate(months):
        train_months = months_between(months, month_index, lookback_months)
        if len(train_months) < lookback_months:
            continue
        train = trades[trades["month"].isin(train_months)]
        current = trades[trades["month"] == month].copy()
        selected = select_buckets(train, cols, min_train_trades, min_pf, min_avg_points, top_n)
        if current.empty or not selected:
            decisions.append({
                "month": month,
                "train_months": ",".join(train_months),
                "selected_buckets": len(selected),
                "trades": 0,
                "net_points": 0.0,
            })
            continue
        current["bucket_key"] = bucket_key_frame(current, cols)
        month_kept = current[current["bucket_key"].isin(selected)].copy()
        if not month_kept.empty:
            kept.append(month_kept)
        decisions.append({
            "month": month,
            "train_months": ",".join(train_months),
            "selected_buckets": len(selected),
            "trades": int(len(month_kept)),
            "net_points": float(month_kept["net_points"].sum()) if len(month_kept) else 0.0,
            "profit_factor": profit_factor(month_kept["net_points"]) if len(month_kept) else 0.0,
        })
    out = pd.concat(kept, ignore_index=True) if kept else trades.iloc[0:0].copy()
    out["selector"] = bucket_name
    return out, pd.DataFrame(decisions)


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join("<th>%s</th>" % c for c in show.columns)
    rows = []
    for _, row in show.iterrows():
        cells = []
        for col, value in row.items():
            cls = ""
            if col in {"full_net_points", "sample2026_net_points", "full_profit_factor", "sample2026_profit_factor", "score"}:
                try:
                    num = float(value)
                    cls = "pos" if (num >= 1 if "profit_factor" in col else num > 0) else "neg"
                except Exception:
                    pass
            text = "" if pd.isna(value) else ("%.4f" % value if isinstance(value, float) else str(value))
            cells.append("<td class='%s'>%s</td>" % (cls, text))
        rows.append("<tr>%s</tr>" % "".join(cells))
    return "<section><h2>%s</h2><div><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></section>" % (
        title,
        headers,
        "".join(rows),
    )


def write_reports(summary: pd.DataFrame, best_trades: pd.DataFrame, best_decisions: pd.DataFrame) -> None:
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#202124;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#d9e2ec}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    target = summary[summary["full_target_frequency"]].sort_values("full_net_points", ascending=False)
    profitable = summary[summary["full_net_points"] > 0].sort_values("full_trades_per_day", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Session Liquidity Walk-Forward Bucket Selector</title><style>%s</style></head>
<body><header><h1>Session Liquidity Walk-Forward Bucket Selector</h1><p>Prior-month bucket selection over high-frequency fixed 1:2 RR trades.</p></header><main>
%s%s%s
</main></body></html>""" % (
        css,
        table_html(target, "Configs Within 10-20 Trades/Day", 120),
        table_html(profitable, "Profitable Full-Period Configs", 160),
        table_html(summary.sort_values("score", ascending=False), "All Configs Ranked", 240),
    )
    (OUTPUT_DIR / "session_liquidity_walkforward_bucket_selector_report.html").write_text(html, encoding="utf-8")
    best_trades.to_csv(OUTPUT_DIR / "best_trades.csv", index=False, encoding="utf-8-sig")
    best_decisions.to_csv(OUTPUT_DIR / "best_monthly_decisions.csv", index=False, encoding="utf-8-sig")
    yearly = round_floats(best_trades.groupby("year").agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
        avg_risk=("risk_points", "mean"),
    ).reset_index())
    monthly = round_floats(best_trades.groupby("month").agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
        avg_risk=("risk_points", "mean"),
    ).reset_index())
    yearly.to_csv(OUTPUT_DIR / "best_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "best_monthly.csv", index=False, encoding="utf-8-sig")
    period_html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Walk-Forward Selector Period Report</title><style>%s</style></head>
<body><header><h1>Walk-Forward Selector Period Report</h1><p>Yearly, monthly, and selection decision report.</p></header><main>
%s%s%s
</main></body></html>""" % (
        css,
        table_html(yearly, "Yearly Report"),
        table_html(monthly, "Monthly Report"),
        table_html(round_floats(best_decisions), "Monthly Decisions"),
    )
    (OUTPUT_DIR / "best_period_report.html").write_text(period_html, encoding="utf-8")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trades = load_trades()
    rows = []
    best_trades = pd.DataFrame()
    best_decisions = pd.DataFrame()
    best_score = -math.inf

    for bucket_name in BUCKET_NAMES:
        cols = BUCKET_SETS[bucket_name]
        for lookback in LOOKBACK_MONTHS_SET:
            for min_train_trades in MIN_TRAIN_TRADES_SET:
                for min_pf in MIN_PF_SET:
                    for min_avg_points in MIN_AVG_POINTS_SET:
                        for top_n in TOP_N_SET:
                            selected, decisions = run_walkforward(
                                trades,
                                bucket_name,
                                cols,
                                lookback,
                                min_train_trades,
                                min_pf,
                                min_avg_points,
                                top_n,
                            )
                            if selected.empty:
                                continue
                            sample2026 = selected[selected["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
                            full = summarize(selected, TRADING_DAYS)
                            sample = summarize(sample2026, TRADING_DAYS_2026)
                            row = {
                                "config_id": "bucket%s_lb%s_mintr%s_pf%s_avg%s_top%s" % (
                                    bucket_name,
                                    lookback,
                                    min_train_trades,
                                    str(min_pf).replace(".", "p"),
                                    str(min_avg_points).replace(".", "p"),
                                    top_n if top_n else "all",
                                ),
                                "bucket_set": bucket_name,
                                "bucket_cols": ",".join(cols),
                                "lookback_months": lookback,
                                "min_train_trades": min_train_trades,
                                "min_pf": min_pf,
                                "min_avg_points": min_avg_points,
                                "top_n": top_n,
                            }
                            row.update({f"full_{k}": v for k, v in full.items()})
                            row.update({f"sample2026_{k}": v for k, v in sample.items()})
                            row["full_target_frequency"] = 10.0 <= row["full_trades_per_day"] <= 20.0
                            row["sample2026_target_frequency"] = 10.0 <= row["sample2026_trades_per_day"] <= 20.0
                            row["score"] = (
                                row["full_net_points"]
                                - row["full_max_drawdown_points"] * 0.15
                                + row["full_positive_month_rate"] * 5.0
                                + row["full_trades_per_day"] * 40.0
                                + (1000.0 if row["full_target_frequency"] else 0.0)
                                + row["sample2026_net_points"] * 0.05
                            )
                            rows.append(row)
                            if row["score"] > best_score:
                                best_score = row["score"]
                                best_trades = selected.copy()
                                best_decisions = decisions.copy()

    summary = round_floats(pd.DataFrame(rows).sort_values(["full_target_frequency", "full_net_points"], ascending=[False, False]))
    summary.to_csv(OUTPUT_DIR / "session_liquidity_walkforward_bucket_selector_summary.csv", index=False, encoding="utf-8-sig")
    write_reports(summary, best_trades, best_decisions)
    print("=== SESSION LIQUIDITY WALK-FORWARD BUCKET SELECTOR ===")
    print("Configs:", len(summary))
    print(summary.head(80).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
