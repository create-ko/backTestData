# -*- coding: utf-8 -*-
"""Filter diagnostics for 2m session-liquidity RR2 trades.

Reads the selected target-frequency trades from script 115 and checks whether
simple pre-entry filters can keep 10-20 trades/day while improving expectancy.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "result" / "session_liquidity_rr2_sweep" / "session_liquidity_rr2_best_trades.csv"
OUTPUT_DIR = ROOT / "result" / "session_liquidity_rr2_filter_diagnostics"
TRADING_DAYS = 1075
TRADING_DAYS_2026 = 142


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


def summarize(trades: pd.DataFrame, trading_days: int, label: str) -> dict:
    pnl = trades["net_points"].astype(float) if len(trades) else pd.Series(dtype=float)
    return {
        "filter": label,
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
        "avg_risk": float(trades["risk_points"].mean()) if len(trades) else 0.0,
    }


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def add_features(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"])
    out["entry_hour"] = out["entry_time"].dt.hour
    out["weekday"] = out["entry_time"].dt.day_name()
    out["risk_bucket"] = pd.cut(
        out["risk_points"].astype(float),
        bins=[0.0, 1.0, 1.5, 2.0, 3.0, 5.0, 99.0],
        labels=["0-1", "1-1.5", "1.5-2", "2-3", "3-5", "5+"],
        include_lowest=True,
    ).astype(str)
    out["level_family"] = out["level_name"].astype(str).replace({
        "or_high": "opening_range",
        "or_low": "opening_range",
        "pdh": "prev_day",
        "pdl": "prev_day",
        "prev_session_high": "prev_session",
        "prev_session_low": "prev_session",
        "session_prior_high": "session_dynamic",
        "session_prior_low": "session_dynamic",
    })
    out["entry_to_level_abs"] = (out["entry_price"].astype(float) - out["level"].astype(float)).abs()
    out["entry_to_level_bucket"] = pd.cut(
        out["entry_to_level_abs"],
        bins=[0.0, 0.2, 0.5, 1.0, 2.0, 99.0],
        labels=["0-0.2", "0.2-0.5", "0.5-1", "1-2", "2+"],
        include_lowest=True,
    ).astype(str)
    return out


def candidate_masks(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    candidates: list[tuple[str, pd.Series]] = [("baseline", pd.Series(True, index=df.index))]
    for col in ["session", "direction", "level_name", "level_family", "entry_hour", "weekday", "risk_bucket", "entry_to_level_bucket"]:
        for value in sorted(df[col].dropna().unique()):
            candidates.append((f"{col} == {value}", df[col] == value))

    # Thresholds that are known before entry.
    for threshold in [1.0, 1.5, 2.0, 2.5, 3.0]:
        candidates.append((f"risk_points <= {threshold:.1f}", df["risk_points"].astype(float) <= threshold))
        candidates.append((f"risk_points >= {threshold:.1f}", df["risk_points"].astype(float) >= threshold))
    for threshold in [0.2, 0.5, 1.0, 1.5]:
        candidates.append((f"entry_to_level_abs <= {threshold:.1f}", df["entry_to_level_abs"].astype(float) <= threshold))
        candidates.append((f"entry_to_level_abs >= {threshold:.1f}", df["entry_to_level_abs"].astype(float) >= threshold))

    # Two-way combinations from high-signal categorical features.
    combo_cols = ["session", "direction", "level_family", "risk_bucket"]
    for i, col_a in enumerate(combo_cols):
        for col_b in combo_cols[i + 1 :]:
            for value_a in sorted(df[col_a].dropna().unique()):
                for value_b in sorted(df[col_b].dropna().unique()):
                    candidates.append((
                        f"{col_a} == {value_a} & {col_b} == {value_b}",
                        (df[col_a] == value_a) & (df[col_b] == value_b),
                    ))
    return candidates


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join("<th>%s</th>" % c for c in show.columns)
    rows = []
    for _, row in show.iterrows():
        cells = []
        for col, value in row.items():
            cls = ""
            if col in {"net_points", "profit_factor", "score", "sample2026_net_points", "sample2026_profit_factor"}:
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


def write_html(results: pd.DataFrame) -> None:
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#1f2937;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#d1d5db}
    main{max-width:1800px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child{text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    target = results[results["target_frequency"]].sort_values("net_points", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Session Liquidity RR2 Filter Diagnostics</title><style>%s</style></head>
<body><header><h1>Session Liquidity RR2 Filter Diagnostics</h1><p>Pre-entry filter slices for the selected script 115 target-frequency trade set.</p></header><main>
%s%s
</main></body></html>""" % (
        css,
        table_html(target, "Filters Within 10-20 Trades/Day", 160),
        table_html(results.sort_values("score", ascending=False), "All Filters Ranked", 260),
    )
    (OUTPUT_DIR / "session_liquidity_rr2_filter_diagnostics_report.html").write_text(html, encoding="utf-8")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trades = add_features(pd.read_csv(INPUT))
    rows = []
    sample2026 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz=trades["entry_time"].dt.tz)]
    for label, mask in candidate_masks(trades):
        subset = trades[mask].copy()
        if subset.empty:
            continue
        sample_subset = sample2026[mask.loc[sample2026.index]].copy()
        row = summarize(subset, TRADING_DAYS, label)
        sample_row = summarize(sample_subset, TRADING_DAYS_2026, label)
        row["sample2026_trades"] = sample_row["trades"]
        row["sample2026_trades_per_day"] = sample_row["trades_per_day"]
        row["sample2026_net_points"] = sample_row["net_points"]
        row["sample2026_profit_factor"] = sample_row["profit_factor"]
        row["sample2026_target_rate"] = sample_row["target_rate"]
        row["target_frequency"] = 10.0 <= row["trades_per_day"] <= 20.0
        row["sample2026_target_frequency"] = 10.0 <= row["sample2026_trades_per_day"] <= 20.0
        row["score"] = (
            row["net_points"]
            - row["max_drawdown_points"] * 0.20
            + row["target_rate"] * 8.0
            + (1000.0 if row["target_frequency"] else 0.0)
            + row["sample2026_net_points"] * 0.10
        )
        rows.append(row)

    results = round_floats(pd.DataFrame(rows).sort_values(["target_frequency", "net_points"], ascending=[False, False]))
    results.to_csv(OUTPUT_DIR / "session_liquidity_rr2_filter_diagnostics.csv", index=False, encoding="utf-8-sig")
    write_html(results)
    print("=== SESSION LIQUIDITY RR2 FILTER DIAGNOSTICS ===")
    print("Input trades:", len(trades), "Candidates:", len(results))
    print(results.head(60).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
