# -*- coding: utf-8 -*-
"""RR2 reversal basket check including the extreme structure reversal add-on."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE125 = SCRIPT_DIR / "125_2m_rr2_reversal_basket.py"
OUTPUT_DIR = ROOT / "result" / "rr2_reversal_basket_with_extreme"
EXTREME_INPUT = ROOT / "result" / "extreme_bb_structure_reversal_rr2" / "best_quality_trades.csv"


spec125 = importlib.util.spec_from_file_location("base125_for_127", BASE125)
base125 = importlib.util.module_from_spec(spec125)
sys.modules["base125_for_127"] = base125
assert spec125.loader is not None
spec125.loader.exec_module(base125)


def load_extreme(features: pd.DataFrame) -> pd.DataFrame:
    trades = base125.load_component(EXTREME_INPUT, "extreme_structure")
    return base125.add_regime(trades, features)


def make_baskets(immediate: pd.DataFrame, or_failed: pd.DataFrame, pdh: pd.DataFrame, extreme: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    components = {
        "immediate_adr60_ge_30": immediate[pd.to_numeric(immediate["adr60"], errors="coerce") >= 30.0],
        "immediate_risk_ge_2": immediate[pd.to_numeric(immediate["risk_points"], errors="coerce") >= 2.0],
        "or_risk_ge_1p5": or_failed[pd.to_numeric(or_failed["risk_points"], errors="coerce") >= 1.5],
        "or_adr60_ge_30": or_failed[pd.to_numeric(or_failed["adr60"], errors="coerce") >= 30.0],
        "pdh_pdl_best": pdh,
        "extreme_structure_best": extreme,
    }
    combos = [
        ["extreme_structure_best"],
        ["immediate_risk_ge_2", "or_risk_ge_1p5", "pdh_pdl_best"],
        ["immediate_risk_ge_2", "or_risk_ge_1p5", "pdh_pdl_best", "extreme_structure_best"],
        ["immediate_adr60_ge_30", "or_risk_ge_1p5", "pdh_pdl_best"],
        ["immediate_adr60_ge_30", "or_risk_ge_1p5", "pdh_pdl_best", "extreme_structure_best"],
        ["immediate_adr60_ge_30", "or_adr60_ge_30", "pdh_pdl_best", "extreme_structure_best"],
    ]
    baskets = []
    for combo in combos:
        frames = [components[name].copy() for name in combo]
        baskets.append((" + ".join(combo), pd.concat(frames, ignore_index=True)))
    return baskets


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    return base125.table_html(df, title, max_rows)


def write_reports(summary: pd.DataFrame, best_trades: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#1d3557;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#d9e2ec}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m RR2 Basket With Extreme Add-on</title><style>%s</style></head>
<body><header><h1>2m RR2 Basket With Extreme Add-on</h1><p>Combined fixed 1:2 reversal components plus extreme structure add-on.</p></header><main>
%s
</main></body></html>""" % (css, table_html(summary.sort_values("score", ascending=False), "Basket Summary", 80))
    (OUTPUT_DIR / "rr2_reversal_basket_with_extreme_report.html").write_text(html, encoding="utf-8")
    best_trades.to_csv(OUTPUT_DIR / "rr2_reversal_basket_with_extreme_best_trades.csv", index=False, encoding="utf-8-sig")
    yearly = base125.round_floats(best_trades.groupby("year").agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
        avg_risk=("risk_points", "mean"),
    ).reset_index())
    monthly = base125.round_floats(best_trades.groupby("month").agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
        avg_risk=("risk_points", "mean"),
    ).reset_index())
    component = base125.round_floats(best_trades.groupby("component").agg(
        trades=("net_points", "size"),
        net_points=("net_points", "sum"),
        avg_points=("net_points", "mean"),
        target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
    ).reset_index())
    yearly.to_csv(OUTPUT_DIR / "rr2_reversal_basket_with_extreme_best_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "rr2_reversal_basket_with_extreme_best_monthly.csv", index=False, encoding="utf-8-sig")
    period_html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>RR2 Basket With Extreme Period Report</title><style>%s</style></head>
<body><header><h1>RR2 Basket With Extreme Period Report</h1><p>Yearly, monthly, and component report for best basket.</p></header><main>
%s%s%s
</main></body></html>""" % (
        css,
        table_html(yearly, "Yearly Report"),
        table_html(monthly, "Monthly Report"),
        table_html(component, "Component Report"),
    )
    (OUTPUT_DIR / "rr2_reversal_basket_with_extreme_best_period_report.html").write_text(period_html, encoding="utf-8")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    features = base125.daily_features()
    immediate = base125.add_regime(base125.load_component(base125.IMMEDIATE_INPUT, "immediate_sweep"), features)
    or_failed = base125.add_regime(base125.load_component(base125.OR_FAILED_INPUT, "or_failed"), features)
    pdh = base125.add_regime(base125.load_component(base125.PDH_PDL_INPUT, "pdh_pdl_double"), features)
    extreme = load_extreme(features)

    rows = []
    best_trades = pd.DataFrame()
    best_score = -math.inf
    for name, raw in make_baskets(immediate, or_failed, pdh, extreme):
        deduped = base125.dedupe(raw)
        capped = base125.apply_portfolio_cap(deduped, base125.PORTFOLIO_CAP)
        sample2026 = capped[capped["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
        full = base125.summarize(capped, base125.TRADING_DAYS)
        sample = base125.summarize(sample2026, base125.TRADING_DAYS_2026)
        row = {"basket": name, "raw_trades": int(len(raw)), "deduped_trades": int(len(deduped))}
        row.update({f"full_{k}": v for k, v in full.items()})
        row.update({f"sample2026_{k}": v for k, v in sample.items()})
        row["full_target_frequency"] = 10.0 <= row["full_trades_per_day"] <= 20.0
        row["sample2026_target_frequency"] = 10.0 <= row["sample2026_trades_per_day"] <= 20.0
        row["score"] = (
            row["full_net_points"]
            - row["full_max_drawdown_points"] * 0.15
            + row["full_positive_month_rate"] * 5.0
            + row["full_trades_per_day"] * 50.0
            + row["sample2026_net_points"] * 0.05
        )
        rows.append(row)
        if row["score"] > best_score:
            best_score = row["score"]
            best_trades = capped.copy()

    summary = base125.round_floats(pd.DataFrame(rows).sort_values("score", ascending=False))
    summary.to_csv(OUTPUT_DIR / "rr2_reversal_basket_with_extreme_summary.csv", index=False, encoding="utf-8-sig")
    write_reports(summary, best_trades)
    print("=== 2M RR2 REVERSAL BASKET WITH EXTREME ===")
    print(summary.to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
