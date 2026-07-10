# -*- coding: utf-8 -*-
"""Slice diagnostics for opening-range failed-breakout reversal RR2."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import math
import sys
from itertools import combinations
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_SCRIPT = SCRIPT_DIR / "100_strategy2_grid_multitimeframe_month_filter.py"
INPUT = ROOT / "result" / "opening_range_failed_breakout_reversal_rr2" / "opening_range_failed_breakout_reversal_rr2_best_trades.csv"
OUTPUT_DIR = ROOT / "result" / "or_failed_breakout_slice_diagnostics"
TRADING_DAYS = 1075
TRADING_DAYS_2026 = 142


spec = importlib.util.spec_from_file_location("base100_for_124", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
sys.modules["base100_for_124"] = base
assert spec.loader is not None
spec.loader.exec_module(base)


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


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
    yearly = trades.groupby("year")["net_points"].sum() if len(trades) else pd.Series(dtype=float)
    monthly = trades.groupby("month")["net_points"].sum() if len(trades) else pd.Series(dtype=float)
    return {
        "slice": label,
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
    daily["sma20"] = daily["close"].rolling(20, min_periods=20).mean()
    daily["sma60"] = daily["close"].rolling(60, min_periods=60).mean()
    daily["sma20_gt_sma60"] = daily["sma20"] > daily["sma60"]
    cols = ["day", "close", "ret20", "ret60", "adr20", "adr60", "vol20", "sma20_gt_sma60"]
    shifted = daily[cols].copy()
    shifted[cols[1:]] = shifted[cols[1:]].shift(1)
    return shifted


def add_features(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"])
    out["day"] = out["day"].astype(str)
    out["month"] = out["month"].astype(str)
    out["hour"] = out["entry_time"].dt.hour
    out["weekday"] = out["entry_time"].dt.weekday
    out["entry_level_distance"] = (out["entry_price"].astype(float) - out["level"].astype(float)).abs()
    out["entry_level_distance_r"] = out["entry_level_distance"] / out["risk_points"].replace(0, math.nan)
    out = out.merge(daily_features(), on="day", how="left")
    return out


def bucketize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["risk_bucket"] = pd.cut(out["risk_points"], bins=[0, 1.0, 1.5, 2.0, 3.0, 99], labels=["<=1", "1-1.5", "1.5-2", "2-3", ">3"])
    out["distance_r_bucket"] = pd.cut(out["entry_level_distance_r"], bins=[-1, 0.1, 0.2, 0.4, 0.8, 99], labels=["<=0.1", "0.1-0.2", "0.2-0.4", "0.4-0.8", ">0.8"])
    out["adr60_bucket"] = pd.cut(out["adr60"], bins=[0, 20, 30, 40, 50, 99], labels=["<=20", "20-30", "30-40", "40-50", ">50"])
    out["vol20_bucket"] = pd.cut(out["vol20"], bins=[0, 0.006, 0.008, 0.010, 0.012, 99], labels=["<=.006", ".006-.008", ".008-.010", ".010-.012", ">.012"])
    out["ret60_bucket"] = pd.cut(out["ret60"], bins=[-99, -0.08, -0.04, 0, 0.04, 0.08, 99], labels=["<=-.08", "-.08--.04", "-.04-0", "0-.04", ".04-.08", ">.08"])
    out["body_bucket"] = pd.cut(out["breakout_body_ratio"], bins=[0, 0.4, 0.55, 0.7, 0.85, 1.01], labels=["<=.40", ".40-.55", ".55-.70", ".70-.85", ">.85"])
    return out


def candidate_masks(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    candidates: list[tuple[str, pd.Series]] = [("baseline", pd.Series(True, index=df.index))]
    categorical = [
        "year",
        "session",
        "level_name",
        "direction",
        "hour",
        "weekday",
        "fail_bars",
        "risk_bucket",
        "distance_r_bucket",
        "adr60_bucket",
        "vol20_bucket",
        "ret60_bucket",
        "body_bucket",
    ]
    for col in categorical:
        for value in sorted(df[col].dropna().unique(), key=lambda x: str(x)):
            candidates.append((f"{col} == {value}", df[col].astype(str) == str(value)))

    thresholds = {
        "risk_points": [1.0, 1.5, 2.0, 3.0],
        "entry_level_distance_r": [0.1, 0.2, 0.4, 0.8],
        "breakout_body_ratio": [0.4, 0.55, 0.7, 0.85],
        "ret20": [-0.04, -0.02, 0.0, 0.02, 0.04],
        "ret60": [-0.08, -0.04, 0.0, 0.04, 0.08],
        "adr20": [20.0, 30.0, 40.0, 50.0],
        "adr60": [20.0, 30.0, 40.0, 50.0],
        "vol20": [0.006, 0.008, 0.010, 0.012],
    }
    for col, values in thresholds.items():
        vals = pd.to_numeric(df[col], errors="coerce")
        for value in values:
            candidates.append((f"{col} >= {value:.4f}", vals >= value))
            candidates.append((f"{col} < {value:.4f}", vals < value))

    atoms: list[tuple[str, pd.Series]] = []
    for col in ["session", "level_name", "direction", "risk_bucket", "adr60_bucket", "ret60_bucket", "body_bucket"]:
        for value in sorted(df[col].dropna().unique(), key=lambda x: str(x)):
            mask = df[col].astype(str) == str(value)
            if 80 <= int(mask.sum()) <= 2500:
                atoms.append((f"{col} == {value}", mask))
    for (label_a, mask_a), (label_b, mask_b) in combinations(atoms, 2):
        mask = mask_a & mask_b
        if 80 <= int(mask.sum()) <= 2500:
            candidates.append((f"{label_a} & {label_b}", mask))
    return [(label, mask.fillna(False).astype(bool)) for label, mask in candidates]


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
    header{background:#3d405b;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#f4f1de}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child{text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    profitable = results[results["net_points"] > 0].sort_values("trades_per_day", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>OR Failed Breakout Slice Diagnostics</title><style>%s</style></head>
<body><header><h1>OR Failed Breakout Slice Diagnostics</h1><p>Pre-entry slices for the best OR failed-breakout reversal RR2 branch.</p></header><main>
%s%s%s
</main></body></html>""" % (
        css,
        table_html(profitable, "Profitable Slices Ranked By Frequency", 180),
        table_html(results.sort_values("net_points", ascending=False), "All Slices By Net", 220),
        table_html(results.sort_values("score", ascending=False), "All Slices By Score", 220),
    )
    (OUTPUT_DIR / "or_failed_breakout_slice_diagnostics_report.html").write_text(html, encoding="utf-8")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trades = bucketize(add_features(pd.read_csv(INPUT)))
    sample2026 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz=trades["entry_time"].dt.tz)]
    rows = []
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
        row["score"] = (
            row["net_points"]
            - row["max_drawdown_points"] * 0.20
            + row["positive_month_rate"] * 5.0
            + row["sample2026_net_points"] * 0.10
            + row["trades_per_day"] * 20.0
        )
        rows.append(row)
    results = round_floats(pd.DataFrame(rows).sort_values("net_points", ascending=False))
    results.to_csv(OUTPUT_DIR / "or_failed_breakout_slice_diagnostics.csv", index=False, encoding="utf-8-sig")
    write_html(results)
    print("=== OR FAILED BREAKOUT SLICE DIAGNOSTICS ===")
    print("Input trades:", len(trades), "Slices:", len(results))
    print(results.head(100).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
