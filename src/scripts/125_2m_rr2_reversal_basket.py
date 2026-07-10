# -*- coding: utf-8 -*-
"""Basket combination for positive low-frequency 2m fixed-RR reversal components.

This script combines already-tested component trade files:
- immediate session sweep reversal filtered by ADR60 / risk
- opening-range failed-breakout reversal filtered by risk / ADR60
- PDH/PDL double-sweep reversal best config

It removes near-duplicate entries and applies a portfolio concurrency cap.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_SCRIPT = SCRIPT_DIR / "100_strategy2_grid_multitimeframe_month_filter.py"
OUTPUT_DIR = ROOT / "result" / "rr2_reversal_basket"
TRADING_DAYS = 1075
TRADING_DAYS_2026 = 142
PORTFOLIO_CAP = 5

IMMEDIATE_INPUT = ROOT / "result" / "session_sweep_reversal_immediate_rr2_full" / "best_quality_trades.csv"
OR_FAILED_INPUT = ROOT / "result" / "opening_range_failed_breakout_reversal_rr2" / "opening_range_failed_breakout_reversal_rr2_best_trades.csv"
PDH_PDL_INPUT = ROOT / "result" / "pdh_pdl_double_sweep_reversal_rr2" / "pdh_pdl_double_sweep_reversal_rr2_best_trades.csv"


spec = importlib.util.spec_from_file_location("base100_for_125", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(base)


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def daily_features() -> pd.DataFrame:
    df = quiet_call(base.load_tf, "2m").copy()
    daily = df.resample("1D").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    daily = daily.dropna().copy()
    daily["day"] = [ts.date().isoformat() for ts in daily.index]
    daily["range"] = daily["high"] - daily["low"]
    daily["ret1"] = daily["close"].pct_change()
    daily["ret20"] = daily["close"].pct_change(20)
    daily["ret60"] = daily["close"].pct_change(60)
    daily["adr20"] = daily["range"].rolling(20, min_periods=20).mean()
    daily["adr60"] = daily["range"].rolling(60, min_periods=60).mean()
    daily["vol20"] = daily["ret1"].rolling(20, min_periods=20).std()
    cols = ["day", "ret20", "ret60", "adr20", "adr60", "vol20"]
    shifted = daily[cols].copy()
    shifted[cols[1:]] = shifted[cols[1:]].shift(1)
    return shifted


def load_component(path: Path, component: str) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["component"] = component
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    trades["day"] = trades["day"].astype(str)
    trades["month"] = trades["month"].astype(str)
    return trades


def add_regime(trades: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    return trades.merge(features, on="day", how="left")


def profit_factor(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").fillna(0.0)
    gp = vals[vals > 0].sum()
    gl = abs(vals[vals < 0].sum())
    if gl == 0:
        return math.inf if gp > 0 else 0.0
    return float(gp / gl)


def max_drawdown(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").fillna(0.0)
    eq = vals.cumsum()
    dd = eq.cummax() - eq
    return float(dd.max()) if len(vals) else 0.0


def summarize(trades: pd.DataFrame, trading_days: int) -> dict:
    pnl = trades["net_points"].astype(float) if len(trades) else pd.Series(dtype=float)
    yearly = trades.groupby("year")["net_points"].sum() if len(trades) else pd.Series(dtype=float)
    monthly = trades.groupby("month")["net_points"].sum() if len(trades) else pd.Series(dtype=float)
    return {
        "trades": int(len(trades)),
        "active_days": int(trades["day"].nunique()) if len(trades) else 0,
        "trades_per_day": float(len(trades) / trading_days) if trading_days else 0.0,
        "trades_per_active_day": float(len(trades) / trades["day"].nunique()) if len(trades) and trades["day"].nunique() else 0.0,
        "net_points": float(pnl.sum()) if len(pnl) else 0.0,
        "avg_points": float(pnl.mean()) if len(pnl) else 0.0,
        "profit_factor": profit_factor(pnl),
        "win_rate": float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
        "target_rate": float((trades["exit_reason"] == "target_2r").mean() * 100) if len(trades) else 0.0,
        "max_drawdown_points": max_drawdown(pnl),
        "positive_years": int((yearly > 0).sum()) if len(yearly) else 0,
        "years": int(yearly.size),
        "positive_month_rate": float((monthly > 0).mean() * 100) if len(monthly) else 0.0,
        "avg_risk": float(trades["risk_points"].mean()) if len(trades) else 0.0,
    }


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def dedupe(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    priority = {"immediate_sweep": 0, "or_failed": 1, "pdh_pdl_double": 2}
    out = trades.copy()
    out["component_priority"] = out["component"].map(priority).fillna(99).astype(int)
    out["entry_key_time"] = out["entry_time"].dt.floor("2min")
    out["entry_key_price"] = out["entry_price"].astype(float).round(3)
    out["stop_key_price"] = out["stop_price"].astype(float).round(3)
    out = out.sort_values(["entry_time", "component_priority", "net_points"], ascending=[True, True, False])
    out = out.drop_duplicates(subset=["entry_key_time", "direction", "entry_key_price", "stop_key_price"], keep="first")
    return out.drop(columns=["component_priority", "entry_key_time", "entry_key_price", "stop_key_price"])


def apply_portfolio_cap(trades: pd.DataFrame, cap: int) -> pd.DataFrame:
    if trades.empty:
        return trades
    open_exits = []
    kept = []
    ordered = trades.sort_values("entry_time")
    for idx, row in ordered.iterrows():
        entry_time = row["entry_time"]
        open_exits = [exit_time for exit_time in open_exits if exit_time > entry_time]
        if len(open_exits) >= cap:
            continue
        kept.append(idx)
        open_exits.append(row["exit_time"])
    return trades.loc[kept].sort_values("entry_time").reset_index(drop=True)


def make_baskets(immediate: pd.DataFrame, or_failed: pd.DataFrame, pdh: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    baskets = []
    components = {
        "immediate_adr60_ge_30": immediate[pd.to_numeric(immediate["adr60"], errors="coerce") >= 30.0],
        "immediate_adr20_ge_30": immediate[pd.to_numeric(immediate["adr20"], errors="coerce") >= 30.0],
        "immediate_risk_ge_2": immediate[pd.to_numeric(immediate["risk_points"], errors="coerce") >= 2.0],
        "or_risk_ge_1p5": or_failed[pd.to_numeric(or_failed["risk_points"], errors="coerce") >= 1.5],
        "or_adr60_ge_30": or_failed[pd.to_numeric(or_failed["adr60"], errors="coerce") >= 30.0],
        "or_adr20_ge_30": or_failed[pd.to_numeric(or_failed["adr20"], errors="coerce") >= 30.0],
        "pdh_pdl_best": pdh,
    }
    combos = [
        ["immediate_adr60_ge_30"],
        ["or_risk_ge_1p5"],
        ["or_adr60_ge_30"],
        ["pdh_pdl_best"],
        ["immediate_adr60_ge_30", "or_risk_ge_1p5"],
        ["immediate_adr60_ge_30", "or_adr60_ge_30"],
        ["immediate_adr60_ge_30", "or_risk_ge_1p5", "pdh_pdl_best"],
        ["immediate_adr60_ge_30", "or_adr60_ge_30", "pdh_pdl_best"],
        ["immediate_adr20_ge_30", "or_risk_ge_1p5", "pdh_pdl_best"],
        ["immediate_risk_ge_2", "or_risk_ge_1p5", "pdh_pdl_best"],
        ["immediate_adr60_ge_30", "or_adr20_ge_30", "pdh_pdl_best"],
    ]
    for combo in combos:
        frames = [components[name].copy() for name in combo]
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        baskets.append((" + ".join(combo), combined))
    return baskets


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


def write_reports(summary: pd.DataFrame, best_trades: pd.DataFrame) -> None:
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#1d3557;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#d9e2ec}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m RR2 Reversal Basket</title><style>%s</style></head>
<body><header><h1>2m RR2 Reversal Basket</h1><p>Combined low-frequency fixed 1:2 reversal components with dedupe and portfolio cap.</p></header><main>
%s
</main></body></html>""" % (css, table_html(summary.sort_values("score", ascending=False), "Basket Summary", 80))
    (OUTPUT_DIR / "rr2_reversal_basket_report.html").write_text(html, encoding="utf-8")
    best_trades.to_csv(OUTPUT_DIR / "rr2_reversal_basket_best_trades.csv", index=False, encoding="utf-8-sig")
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
    yearly.to_csv(OUTPUT_DIR / "rr2_reversal_basket_best_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "rr2_reversal_basket_best_monthly.csv", index=False, encoding="utf-8-sig")
    period_html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>RR2 Basket Period Report</title><style>%s</style></head>
<body><header><h1>RR2 Basket Period Report</h1><p>Yearly and monthly report for best basket.</p></header><main>
%s%s%s
</main></body></html>""" % (
        css,
        table_html(yearly, "Yearly Report"),
        table_html(monthly, "Monthly Report"),
        table_html(round_floats(best_trades.groupby("component").agg(
            trades=("net_points", "size"),
            net_points=("net_points", "sum"),
            avg_points=("net_points", "mean"),
            target_rate=("exit_reason", lambda s: float((s == "target_2r").mean() * 100)),
        ).reset_index()), "Component Report"),
    )
    (OUTPUT_DIR / "rr2_reversal_basket_best_period_report.html").write_text(period_html, encoding="utf-8")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    features = daily_features()
    immediate = add_regime(load_component(IMMEDIATE_INPUT, "immediate_sweep"), features)
    or_failed = add_regime(load_component(OR_FAILED_INPUT, "or_failed"), features)
    pdh = add_regime(load_component(PDH_PDL_INPUT, "pdh_pdl_double"), features)

    rows = []
    best_trades = pd.DataFrame()
    best_score = -math.inf
    for name, raw in make_baskets(immediate, or_failed, pdh):
        deduped = dedupe(raw)
        capped = apply_portfolio_cap(deduped, PORTFOLIO_CAP)
        sample2026 = capped[capped["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
        full = summarize(capped, TRADING_DAYS)
        sample = summarize(sample2026, TRADING_DAYS_2026)
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

    summary = round_floats(pd.DataFrame(rows).sort_values("score", ascending=False))
    summary.to_csv(OUTPUT_DIR / "rr2_reversal_basket_summary.csv", index=False, encoding="utf-8-sig")
    write_reports(summary, best_trades)
    print("=== 2M RR2 REVERSAL BASKET ===")
    print(summary.to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
