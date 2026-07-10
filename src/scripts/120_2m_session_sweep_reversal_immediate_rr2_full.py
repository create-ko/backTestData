# -*- coding: utf-8 -*-
"""Full-period check for immediate session-liquidity sweep reversal RR2.

Script 119 showed that immediate sweep reversal is the only immediate-entry
branch with positive expectancy in the 2026 sample, while breakout momentum
destroys the edge. This focused script expands only that branch to 2023-2026.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE115 = SCRIPT_DIR / "115_2m_session_liquidity_rr2_sweep.py"
BASE119 = SCRIPT_DIR / "119_2m_session_liquidity_immediate_rr2_sweep.py"
OUTPUT_DIR = ROOT / "result" / "session_sweep_reversal_immediate_rr2_full"


spec115 = importlib.util.spec_from_file_location("base115_for_120", BASE115)
base115 = importlib.util.module_from_spec(spec115)
sys.modules["base115_for_120"] = base115
assert spec115.loader is not None
spec115.loader.exec_module(base115)

spec119 = importlib.util.spec_from_file_location("base119_for_120", BASE119)
base119 = importlib.util.module_from_spec(spec119)
sys.modules["base119_for_120"] = base119
assert spec119.loader is not None
spec119.loader.exec_module(base119)


OR_BARS_SET = [8]
LEVEL_SETS = ["or,pdhpdl,prev_session,session_dynamic"]
BIAS_MODES = ["price_follow"]
DISPLACEMENT_MODES = ["close_extreme", "body35_close_extreme"]
COOLDOWN_BARS_SET = [0, 3]
STOP_MODES = ["retest"]
STOP_BUFFERS = [0.2]
MIN_RISKS = [0.8]
MAX_RISKS = [5.0]
MAX_HOLD_BARS_SET = [20, 30]
CONCURRENCY_CAPS = [5]


def prefix_metrics(prefix: str, metrics: dict) -> dict:
    return {prefix + "_" + key: value for key, value in metrics.items()}


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


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


def write_reports(summary: pd.DataFrame, best_trades: pd.DataFrame | None, best_quality_trades: pd.DataFrame | None) -> None:
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#263238;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#d8e7e2}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    target = summary[summary["full_target_frequency"]].sort_values("full_net_points", ascending=False)
    profitable = summary[summary["full_net_points"] > 0].sort_values("full_trades_per_day", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m Immediate Sweep Reversal RR2 Full Check</title><style>%s</style></head>
<body><header><h1>2m Immediate Sweep Reversal RR2 Full Check</h1><p>Focused fixed 1:2 RR full-period check for immediate sweep reversal only.</p></header><main>
%s%s%s
</main></body></html>""" % (
        css,
        table_html(target, "Configs Within 10-20 Trades/Day On Full Period", 160),
        table_html(profitable, "Profitable Full-Period Configs", 160),
        table_html(summary.sort_values("score", ascending=False), "All Configs Ranked", 240),
    )
    (OUTPUT_DIR / "session_sweep_reversal_immediate_rr2_full_report.html").write_text(html, encoding="utf-8")

    def write_period(prefix: str, trades: pd.DataFrame | None) -> None:
        if trades is None or trades.empty:
            return
        trades.to_csv(OUTPUT_DIR / f"{prefix}_trades.csv", index=False, encoding="utf-8-sig")
        yearly = round_floats(trades.groupby("year").agg(
            trades=("net_points", "size"),
            net_points=("net_points", "sum"),
            avg_points=("net_points", "mean"),
            target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
            avg_risk=("risk_points", "mean"),
        ).reset_index())
        monthly = round_floats(trades.groupby("month").agg(
            trades=("net_points", "size"),
            net_points=("net_points", "sum"),
            avg_points=("net_points", "mean"),
            target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
            avg_risk=("risk_points", "mean"),
        ).reset_index())
        yearly.to_csv(OUTPUT_DIR / f"{prefix}_yearly.csv", index=False, encoding="utf-8-sig")
        monthly.to_csv(OUTPUT_DIR / f"{prefix}_monthly.csv", index=False, encoding="utf-8-sig")
        period_html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>%s Period Report</title><style>%s</style></head>
<body><header><h1>%s Period Report</h1><p>Yearly and monthly report.</p></header><main>
%s%s
</main></body></html>""" % (prefix, css, prefix, table_html(yearly, "Yearly Report"), table_html(monthly, "Monthly Report"))
        (OUTPUT_DIR / f"{prefix}_period_report.html").write_text(period_html, encoding="utf-8")

    write_period("best_target_frequency", best_trades)
    write_period("best_quality", best_quality_trades)


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_df = base115.load_data()
    trading_days = int(pd.Series(raw_df.index.date).nunique())
    trading_days_2026 = int(pd.Series(raw_df[raw_df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")].index.date).nunique())
    rows = []
    best_target_trades = None
    best_target_key = None
    best_target_net = -math.inf
    best_quality_trades = None
    best_quality_key = None
    best_quality_net = -math.inf

    for or_bars in OR_BARS_SET:
        df = base115.add_level_columns(raw_df, or_bars)
        for level_set in LEVEL_SETS:
            for bias_mode in BIAS_MODES:
                for displacement_mode in DISPLACEMENT_MODES:
                    for cooldown_bars in COOLDOWN_BARS_SET:
                        entries = base119.find_immediate_entries(
                            df,
                            level_set,
                            "sweep_reversal_immediate",
                            bias_mode,
                            displacement_mode,
                            cooldown_bars,
                        )
                        print(
                            "ENTRIES",
                            "or", or_bars,
                            "levels", level_set,
                            "bias", bias_mode,
                            "disp", displacement_mode,
                            "cooldown", cooldown_bars,
                            len(entries),
                            flush=True,
                        )
                        if entries.empty:
                            continue
                        for stop_mode in STOP_MODES:
                            for stop_buffer in STOP_BUFFERS:
                                for min_risk in MIN_RISKS:
                                    for max_risk in MAX_RISKS:
                                        if min_risk >= max_risk:
                                            continue
                                        for max_hold_bars in MAX_HOLD_BARS_SET:
                                            for cap in CONCURRENCY_CAPS:
                                                trades = base115.simulate_rr2(
                                                    df,
                                                    entries,
                                                    stop_mode,
                                                    stop_buffer,
                                                    min_risk,
                                                    max_risk,
                                                    max_hold_bars,
                                                    cap,
                                                )
                                                if trades.empty:
                                                    continue
                                                trades2026 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
                                                config_id = "or%s_%s_sweep_reversal_immediate_%s_%s_cd%s_%s_sb%s_min%s_max%s_hold%s_cap%s" % (
                                                    or_bars,
                                                    level_set.replace(",", "-"),
                                                    bias_mode,
                                                    displacement_mode,
                                                    cooldown_bars,
                                                    stop_mode,
                                                    str(stop_buffer).replace(".", "p"),
                                                    str(min_risk).replace(".", "p"),
                                                    str(max_risk).replace(".", "p"),
                                                    max_hold_bars,
                                                    cap,
                                                )
                                                row = {
                                                    "config_id": config_id,
                                                    "or_bars": or_bars,
                                                    "level_set": level_set,
                                                    "signal_mode": "sweep_reversal_immediate",
                                                    "bias_mode": bias_mode,
                                                    "displacement_mode": displacement_mode,
                                                    "cooldown_bars": cooldown_bars,
                                                    "stop_mode": stop_mode,
                                                    "stop_buffer": stop_buffer,
                                                    "min_risk": min_risk,
                                                    "max_risk": max_risk,
                                                    "max_hold_bars": max_hold_bars,
                                                    "max_concurrent_positions": cap,
                                                }
                                                row.update(prefix_metrics("full", base115.summarize(trades, trading_days)))
                                                row.update(prefix_metrics("sample2026", base115.summarize(trades2026, trading_days_2026)))
                                                row["full_target_frequency"] = 10.0 <= row["full_trades_per_day"] <= 20.0
                                                row["sample2026_target_frequency"] = 10.0 <= row["sample2026_trades_per_day"] <= 20.0
                                                row["score"] = (
                                                    row["full_net_points"]
                                                    - row["full_max_drawdown_points"] * 0.20
                                                    + row["full_positive_month_rate"] * 5.0
                                                    + (1000.0 if row["full_target_frequency"] else 0.0)
                                                    + row["sample2026_net_points"] * 0.10
                                                )
                                                rows.append(row)
                                                if row["full_target_frequency"] and row["full_net_points"] > best_target_net:
                                                    best_target_net = row["full_net_points"]
                                                    best_target_key = config_id
                                                    best_target_trades = trades.copy()
                                                if row["full_net_points"] > best_quality_net:
                                                    best_quality_net = row["full_net_points"]
                                                    best_quality_key = config_id
                                                    best_quality_trades = trades.copy()

    summary = round_floats(pd.DataFrame(rows).sort_values(["full_target_frequency", "full_net_points"], ascending=[False, False]))
    summary.to_csv(OUTPUT_DIR / "session_sweep_reversal_immediate_rr2_full_summary.csv", index=False, encoding="utf-8-sig")
    write_reports(summary, best_target_trades, best_quality_trades)
    print("=== 2M IMMEDIATE SWEEP REVERSAL RR2 FULL CHECK ===")
    print("Configs:", len(summary), "Trading days:", trading_days, "2026 days:", trading_days_2026)
    print("Best target-frequency config:", best_target_key)
    print("Best quality config:", best_quality_key)
    print(summary.head(80).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
