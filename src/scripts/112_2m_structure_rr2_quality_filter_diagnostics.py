# -*- coding: utf-8 -*-
"""Quality-filter diagnostics for the structural breakout-pullback RR2 setup.

Reads script 111's best-trades output and ranks simple, implementation-friendly
filters. This is a diagnostic step, not a production walk-forward selector.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "result" / "structure_breakout_pullback_rr2_sweep"
SOURCE_TRADES = SOURCE_DIR / "structure_breakout_pullback_rr2_best_trades.csv"
OUTPUT_DIR = ROOT / "result" / "structure_rr2_quality_filters"


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


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def load_trades() -> tuple[pd.DataFrame, int, int]:
    if not SOURCE_TRADES.exists():
        raise FileNotFoundError("Run script 111 first so best-trades output exists: %s" % SOURCE_TRADES)
    trades = pd.read_csv(SOURCE_TRADES)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    trades["hour"] = trades["entry_time"].dt.hour
    trades["weekday"] = trades["entry_time"].dt.day_name()

    rng = trades["breakout_high"].astype(float) - trades["breakout_low"].astype(float)
    body = (trades["breakout_high"].astype(float) - trades["breakout_low"].astype(float)).where(rng == 0, (trades["level"].astype(float) - trades["breakout_low"].astype(float)).abs())
    # Direction-aware candle quality metrics.
    long_mask = trades["direction"].astype(str).eq("long")
    close_pos = pd.Series(index=trades.index, dtype=float)
    impulse = pd.Series(index=trades.index, dtype=float)
    close_pos.loc[long_mask] = (
        (trades.loc[long_mask, "entry_price"].astype(float) - trades.loc[long_mask, "breakout_low"].astype(float))
        / rng.loc[long_mask].replace(0, pd.NA)
    )
    close_pos.loc[~long_mask] = (
        (trades.loc[~long_mask, "breakout_high"].astype(float) - trades.loc[~long_mask, "entry_price"].astype(float))
        / rng.loc[~long_mask].replace(0, pd.NA)
    )
    impulse.loc[long_mask] = trades.loc[long_mask, "breakout_high"].astype(float) - trades.loc[long_mask, "level"].astype(float)
    impulse.loc[~long_mask] = trades.loc[~long_mask, "level"].astype(float) - trades.loc[~long_mask, "breakout_low"].astype(float)
    trades["breakout_close_position_proxy"] = close_pos.clip(lower=0.0, upper=1.0)
    trades["breakout_impulse_points"] = impulse
    trades["impulse_to_risk"] = trades["breakout_impulse_points"] / trades["risk_points"].replace(0, pd.NA)
    trades["body_proxy_points"] = body

    trades["risk_bucket"] = pd.cut(
        trades["risk_points"],
        bins=[0.0, 1.2, 2.0, 3.0, 4.0, 99.0],
        labels=["risk_0_1p2", "risk_1p2_2", "risk_2_3", "risk_3_4", "risk_4p"],
        include_lowest=True,
    ).astype(str)
    trades["impulse_bucket"] = pd.cut(
        trades["breakout_impulse_points"],
        bins=[-99.0, 0.2, 0.5, 1.0, 2.0, 99.0],
        labels=["imp_0_0p2", "imp_0p2_0p5", "imp_0p5_1", "imp_1_2", "imp_2p"],
    ).astype(str)
    trades["impulse_r_bucket"] = pd.cut(
        trades["impulse_to_risk"],
        bins=[-99.0, 0.1, 0.25, 0.5, 1.0, 99.0],
        labels=["impR_0_0p1", "impR_0p1_0p25", "impR_0p25_0p5", "impR_0p5_1", "impR_1p"],
    ).astype(str)
    trades["closepos_bucket"] = pd.cut(
        trades["breakout_close_position_proxy"],
        bins=[-0.01, 0.25, 0.50, 0.75, 1.01],
        labels=["closepos_0_25", "closepos_25_50", "closepos_50_75", "closepos_75_100"],
    ).astype(str)

    full_days = 1075
    days_2026 = 142
    return trades, full_days, days_2026


def summarize(group: pd.DataFrame, trading_days: int) -> dict:
    pnl = group["net_points"].astype(float)
    yearly = group.groupby("year")["net_points"].sum()
    monthly = group.groupby("month")["net_points"].sum()
    return {
        "trades": int(len(group)),
        "trading_days": int(trading_days),
        "active_days": int(group["day"].nunique()) if len(group) else 0,
        "trades_per_day": float(len(group) / trading_days) if trading_days else 0.0,
        "trades_per_active_day": float(len(group) / group["day"].nunique()) if group["day"].nunique() else 0.0,
        "net_points": float(pnl.sum()),
        "avg_points": float(pnl.mean()) if len(group) else 0.0,
        "profit_factor": profit_factor(pnl),
        "win_rate": float((pnl > 0).mean() * 100) if len(group) else 0.0,
        "target_rate": float((group["exit_reason"] == "target_2r").mean() * 100) if len(group) else 0.0,
        "max_drawdown_points": max_drawdown(pnl),
        "positive_years": int((yearly > 0).sum()),
        "years": int(yearly.size),
        "positive_month_rate": float((monthly > 0).mean() * 100) if monthly.size else 0.0,
        "avg_risk": float(group["risk_points"].mean()) if len(group) else 0.0,
        "avg_impulse": float(group["breakout_impulse_points"].mean()) if len(group) else 0.0,
    }


def filter_label(cols: list[str], key) -> str:
    if not isinstance(key, tuple):
        key = (key,)
    return " & ".join("%s=%s" % (col, value) for col, value in zip(cols, key))


def slice_table(trades: pd.DataFrame, cols: list[str], trading_days: int) -> pd.DataFrame:
    rows = []
    for key, group in trades.groupby(cols, dropna=False, sort=True):
        row = {"slice_type": "+".join(cols), "slice": filter_label(cols, key)}
        row.update(summarize(group, trading_days))
        rows.append(row)
    return pd.DataFrame(rows)


def condition_rows(trades: pd.DataFrame, trading_days: int) -> pd.DataFrame:
    rows = []
    numeric_conditions = [
        ("breakout_impulse_points", ">=", [0.2, 0.5, 1.0, 2.0]),
        ("impulse_to_risk", ">=", [0.1, 0.25, 0.5, 1.0]),
        ("risk_points", "<=", [1.2, 2.0, 3.0, 4.0]),
    ]
    for col, op, cuts in numeric_conditions:
        for cut in cuts:
            if op == ">=":
                group = trades[trades[col] >= cut]
            else:
                group = trades[trades[col] <= cut]
            if group.empty:
                continue
            row = {"slice_type": "condition", "slice": "%s %s %.4f" % (col, op, cut)}
            row.update(summarize(group, trading_days))
            rows.append(row)
    return pd.DataFrame(rows)


def build_diagnostics(trades: pd.DataFrame, trading_days: int) -> pd.DataFrame:
    parts = [pd.DataFrame([{"slice_type": "all", "slice": "all", **summarize(trades, trading_days)}])]
    for cols in [
        ["direction"],
        ["session"],
        ["hour"],
        ["weekday"],
        ["risk_bucket"],
        ["impulse_bucket"],
        ["impulse_r_bucket"],
        ["closepos_bucket"],
        ["direction", "session"],
        ["direction", "hour"],
        ["session", "hour"],
        ["direction", "risk_bucket"],
        ["direction", "impulse_bucket"],
        ["direction", "impulse_r_bucket"],
    ]:
        parts.append(slice_table(trades, cols, trading_days))
    parts.append(condition_rows(trades, trading_days))
    out = pd.concat(parts, ignore_index=True)
    out["target_frequency"] = out["trades_per_day"].between(10.0, 20.0)
    out["positive_all_years"] = out["positive_years"] == out["years"]
    out["score"] = (
        out["net_points"]
        - out["max_drawdown_points"] * 0.20
        + out["positive_month_rate"] * 5.0
        + out["target_frequency"].astype(int) * 1000.0
    )
    return round_floats(out.sort_values(["target_frequency", "net_points"], ascending=[False, False]))


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join("<th>%s</th>" % c for c in show.columns)
    body = []
    for _, row in show.iterrows():
        cells = []
        for col, value in row.items():
            cls = ""
            if col in {"net_points", "avg_points", "profit_factor", "score"}:
                try:
                    num = float(value)
                    cls = "pos" if (num >= 1 if col == "profit_factor" else num > 0) else "neg"
                except Exception:
                    pass
            text = "" if pd.isna(value) else ("%.4f" % value if isinstance(value, float) else str(value))
            cells.append("<td class='%s'>%s</td>" % (cls, text))
        body.append("<tr>%s</tr>" % "".join(cells))
    return "<section><h2>%s</h2><div><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></section>" % (
        title,
        headers,
        "".join(body),
    )


def write_html(diagnostics: pd.DataFrame) -> None:
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#101820;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#c9d3df}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Structure RR2 Quality Filter Diagnostics</title><style>%s</style></head>
<body><header><h1>Structure RR2 Quality Filter Diagnostics</h1><p>Post-hoc diagnostic slices for the best structural breakout-pullback RR2 candidate.</p></header><main>
%s%s
</main></body></html>""" % (
        css,
        table_html(diagnostics[diagnostics["target_frequency"]].sort_values("net_points", ascending=False), "Frequency-Fit Slices", 120),
        table_html(diagnostics.sort_values("score", ascending=False), "All Slices Ranked", 180),
    )
    (OUTPUT_DIR / "structure_rr2_quality_filter_report.html").write_text(html, encoding="utf-8")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trades, full_days, days_2026 = load_trades()
    diagnostics = build_diagnostics(trades, full_days)
    trades2026 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
    diagnostics2026 = build_diagnostics(trades2026, days_2026)

    trades.to_csv(OUTPUT_DIR / "structure_rr2_quality_enriched_trades.csv", index=False, encoding="utf-8-sig")
    diagnostics.to_csv(OUTPUT_DIR / "structure_rr2_quality_diagnostics.csv", index=False, encoding="utf-8-sig")
    diagnostics2026.to_csv(OUTPUT_DIR / "structure_rr2_quality_diagnostics_2026.csv", index=False, encoding="utf-8-sig")
    write_html(diagnostics)

    print("=== STRUCTURE RR2 QUALITY FILTER DIAGNOSTICS ===")
    print("Full-period top frequency-fit slices:")
    freq = diagnostics[diagnostics["target_frequency"]].sort_values("net_points", ascending=False)
    print(freq.head(25).to_string(index=False))
    print("2026 top frequency-fit slices:")
    freq2026 = diagnostics2026[diagnostics2026["target_frequency"]].sort_values("net_points", ascending=False)
    print(freq2026.head(25).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
