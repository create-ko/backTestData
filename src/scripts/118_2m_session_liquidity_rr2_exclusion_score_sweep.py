# -*- coding: utf-8 -*-
"""Exclusion-score sweep for the closest 2m session-liquidity RR2 candidate.

The best current 1:2 RR candidate already trades about 11.1 times per day.
To preserve the requested 10-20 trades/day, we can remove only about 10% of
the trades. This script searches for simple pre-entry exclusion rules that
remove the most damaging regimes/trade shapes while keeping target frequency.
"""
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
INPUT = ROOT / "result" / "session_liquidity_rr2_sweep" / "session_liquidity_rr2_best_trades.csv"
OUTPUT_DIR = ROOT / "result" / "session_liquidity_rr2_exclusion_score_sweep"
TRADING_DAYS = 1075
TRADING_DAYS_2026 = 142
MIN_TRADES_PER_DAY = 10.0
MAX_TRADES_PER_DAY = 20.0


spec = importlib.util.spec_from_file_location("base100_for_118", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
sys.modules["base100_for_118"] = base
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
    monthly = trades.groupby("month")["net_points"].sum() if len(trades) else pd.Series(dtype=float)
    return {
        "rule": label,
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
        "positive_month_rate": float((monthly > 0).mean() * 100) if len(monthly) else 0.0,
    }


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def daily_regime_features() -> pd.DataFrame:
    df = quiet_call(base.load_tf, "2m").copy()
    daily = df.resample("1D").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    daily = daily.dropna().copy()
    daily["day"] = [ts.date().isoformat() for ts in daily.index]
    daily["range"] = daily["high"] - daily["low"]
    daily["ret1"] = daily["close"].pct_change()
    daily["ret5"] = daily["close"].pct_change(5)
    daily["ret20"] = daily["close"].pct_change(20)
    daily["ret60"] = daily["close"].pct_change(60)
    daily["adr5"] = daily["range"].rolling(5, min_periods=5).mean()
    daily["adr20"] = daily["range"].rolling(20, min_periods=20).mean()
    daily["adr60"] = daily["range"].rolling(60, min_periods=60).mean()
    daily["vol20"] = daily["ret1"].rolling(20, min_periods=20).std()
    daily["sma20"] = daily["close"].rolling(20, min_periods=20).mean()
    daily["sma60"] = daily["close"].rolling(60, min_periods=60).mean()
    daily["close_to_sma20"] = daily["close"] / daily["sma20"] - 1.0
    daily["sma20_gt_sma60"] = daily["sma20"] > daily["sma60"]
    feature_cols = [
        "day",
        "close",
        "ret5",
        "ret20",
        "ret60",
        "adr5",
        "adr20",
        "adr60",
        "vol20",
        "close_to_sma20",
        "sma20_gt_sma60",
    ]
    shifted = daily[feature_cols].copy()
    shifted[feature_cols[1:]] = shifted[feature_cols[1:]].shift(1)
    return shifted


def monthly_regime_features() -> pd.DataFrame:
    df = quiet_call(base.load_tf, "2m").copy()
    monthly = df.resample("ME").agg(close=("close", "last"), high=("high", "max"), low=("low", "min"))
    monthly = monthly.dropna().copy()
    monthly["month"] = monthly.index.strftime("%Y-%m")
    monthly["monthly_ret"] = monthly["close"].pct_change()
    monthly["monthly_range"] = monthly["high"] - monthly["low"]
    monthly["prev_month_ret"] = monthly["monthly_ret"].shift(1)
    monthly["prev_month_range"] = monthly["monthly_range"].shift(1)
    monthly["prev_month_close"] = monthly["close"].shift(1)
    return monthly[["month", "prev_month_ret", "prev_month_range", "prev_month_close"]]


def add_features(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"])
    out["day"] = out["day"].astype(str)
    out["month"] = out["month"].astype(str)
    out["hour"] = out["entry_time"].dt.hour
    out["weekday"] = out["entry_time"].dt.weekday
    out["entry_level_distance"] = (out["entry_price"].astype(float) - out["level"].astype(float)).abs()
    out["entry_level_distance_r"] = out["entry_level_distance"] / out["risk_points"].replace(0, math.nan)
    out["is_long"] = out["direction"].astype(str).eq("long")
    out = out.merge(daily_regime_features(), on="day", how="left")
    out = out.merge(monthly_regime_features(), on="month", how="left")
    return out


def candidate_exclusions(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    candidates: list[tuple[str, pd.Series]] = []
    numeric_thresholds = {
        "ret5": [-0.03, -0.015, 0.0, 0.015, 0.03],
        "ret20": [-0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06],
        "ret60": [-0.10, -0.08, -0.04, 0.0, 0.04, 0.08, 0.12],
        "adr5": [15.0, 20.0, 30.0, 40.0, 55.0],
        "adr20": [15.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        "adr60": [15.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        "vol20": [0.004, 0.006, 0.008, 0.010, 0.012, 0.015],
        "close_to_sma20": [-0.04, -0.02, 0.0, 0.02, 0.04],
        "prev_month_ret": [-0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06],
        "prev_month_range": [80.0, 120.0, 160.0, 220.0, 300.0, 400.0],
        "prev_month_close": [1900.0, 2200.0, 2600.0, 3000.0, 3400.0, 3800.0],
        "risk_points": [1.0, 1.5, 2.0, 3.0, 4.0],
        "entry_level_distance": [0.2, 0.5, 1.0, 1.5, 2.0],
        "entry_level_distance_r": [0.1, 0.2, 0.4, 0.6, 1.0],
    }
    for col, thresholds in numeric_thresholds.items():
        vals = pd.to_numeric(df[col], errors="coerce")
        for threshold in thresholds:
            candidates.append((f"drop {col} < {threshold:.4f}", vals < threshold))
            candidates.append((f"drop {col} >= {threshold:.4f}", vals >= threshold))

    for col in ["session", "direction", "level_name", "hour", "weekday"]:
        for value in sorted(df[col].dropna().unique()):
            candidates.append((f"drop {col} == {value}", df[col] == value))

    candidates.append(("drop sma20_gt_sma60 == True", df["sma20_gt_sma60"] == True))
    candidates.append(("drop sma20_gt_sma60 == False", df["sma20_gt_sma60"] == False))

    # A few interpretable two-way exclusions; these often isolate a small bad pocket.
    candidates.extend([
        ("drop low_vol_and_low_adr", (df["vol20"] < 0.008) & (df["adr20"] < 30.0)),
        ("drop low_vol_and_compressed_month", (df["vol20"] < 0.008) & (df["prev_month_range"] < 160.0)),
        ("drop down_60d_low_adr", (df["ret60"] < 0.0) & (df["adr20"] < 30.0)),
        ("drop stretched_up_low_vol", (df["ret20"] > 0.04) & (df["vol20"] < 0.010)),
        ("drop tiny_distance_high_risk", (df["entry_level_distance_r"] < 0.2) & (df["risk_points"] >= 3.0)),
        ("drop large_distance_low_vol", (df["entry_level_distance"] >= 1.0) & (df["vol20"] < 0.010)),
    ])
    return [(label, mask.fillna(False).astype(bool)) for label, mask in candidates]


def score_row(full: dict, sample: dict) -> float:
    target_frequency = MIN_TRADES_PER_DAY <= full["trades_per_day"] <= MAX_TRADES_PER_DAY
    return (
        full["net_points"]
        - full["max_drawdown_points"] * 0.20
        + full["positive_month_rate"] * 6.0
        + (1000.0 if target_frequency else -1000.0)
        + sample["net_points"] * 0.10
    )


def evaluate_keep(df: pd.DataFrame, keep: pd.Series, label: str) -> dict | None:
    kept = df[keep].copy()
    if kept.empty:
        return None
    sample = kept[kept["entry_time"] >= pd.Timestamp("2026-01-01", tz=kept["entry_time"].dt.tz)]
    full_metrics = summarize(kept, TRADING_DAYS, label)
    sample_metrics = summarize(sample, TRADING_DAYS_2026, label)
    row = {
        "rule": label,
        "dropped_trades": int((~keep).sum()),
        "dropped_net_points": float(df.loc[~keep, "net_points"].sum()),
    }
    row.update({f"full_{key}": value for key, value in full_metrics.items() if key != "rule"})
    row.update({f"sample2026_{key}": value for key, value in sample_metrics.items() if key != "rule"})
    row["full_target_frequency"] = MIN_TRADES_PER_DAY <= full_metrics["trades_per_day"] <= MAX_TRADES_PER_DAY
    row["sample2026_target_frequency"] = MIN_TRADES_PER_DAY <= sample_metrics["trades_per_day"] <= MAX_TRADES_PER_DAY
    row["score"] = score_row(full_metrics, sample_metrics)
    return row


def build_score_rules(df: pd.DataFrame, exclusions: list[tuple[str, pd.Series]]) -> list[tuple[str, pd.Series]]:
    # Keep only small-to-medium exclusions with negative average PnL, then build
    # a count score. Thresholds allow overlapping weak warning signs.
    min_kept = int(TRADING_DAYS * MIN_TRADES_PER_DAY)
    max_drop = len(df) - min_kept
    scored = []
    for label, mask in exclusions:
        dropped = df[mask]
        if dropped.empty or len(dropped) > max_drop * 2:
            continue
        avg = float(dropped["net_points"].mean())
        net = float(dropped["net_points"].sum())
        if avg < -0.30 or net < -250.0:
            scored.append((label, mask, avg, net, len(dropped)))
    scored = sorted(scored, key=lambda x: (x[3], x[2]))[:24]
    rules: list[tuple[str, pd.Series]] = []
    if not scored:
        return rules
    score = pd.Series(0, index=df.index, dtype=int)
    for _, mask, _, _, _ in scored:
        score += mask.astype(int)
    for threshold in [1, 2, 3, 4]:
        rules.append((f"keep exclusion_score < {threshold}", score < threshold))
    return rules


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join("<th>%s</th>" % c for c in show.columns)
    rows = []
    for _, row in show.iterrows():
        cells = []
        for col, value in row.items():
            cls = ""
            if col in {"full_net_points", "sample2026_net_points", "full_profit_factor", "sample2026_profit_factor", "score", "dropped_net_points"}:
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
    header{background:#2b2d42;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#edf2f4}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child{text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    target = results[results["full_target_frequency"]].sort_values("full_net_points", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Session Liquidity RR2 Exclusion Score Sweep</title><style>%s</style></head>
<body><header><h1>Session Liquidity RR2 Exclusion Score Sweep</h1><p>Search for small pre-entry exclusions that preserve 10-20 trades/day.</p></header><main>
%s%s
</main></body></html>""" % (
        css,
        table_html(target, "Rules Within 10-20 Trades/Day", 180),
        table_html(results.sort_values("score", ascending=False), "All Rules Ranked", 260),
    )
    (OUTPUT_DIR / "session_liquidity_rr2_exclusion_score_sweep_report.html").write_text(html, encoding="utf-8")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trades = add_features(pd.read_csv(INPUT))
    exclusions = candidate_exclusions(trades)
    rows = []

    baseline = pd.Series(True, index=trades.index)
    baseline_row = evaluate_keep(trades, baseline, "baseline")
    if baseline_row:
        rows.append(baseline_row)

    min_kept = int(TRADING_DAYS * MIN_TRADES_PER_DAY)
    max_single_drop = len(trades) - min_kept
    useful_single: list[tuple[str, pd.Series, float, float]] = []
    for label, mask in exclusions:
        if mask.sum() == 0 or mask.sum() > max_single_drop:
            continue
        dropped_net = float(trades.loc[mask, "net_points"].sum())
        dropped_avg = float(trades.loc[mask, "net_points"].mean())
        if dropped_net >= 0:
            continue
        useful_single.append((label, mask, dropped_net, dropped_avg))
        row = evaluate_keep(trades, ~mask, label)
        if row:
            rows.append(row)

    # Combine only the best small exclusions by dropped net and dropped average.
    useful_single = sorted(useful_single, key=lambda x: (x[2], x[3]))[:36]
    for combo_size in [2, 3]:
        for combo in combinations(useful_single, combo_size):
            label = " + ".join(item[0].replace("drop ", "") for item in combo)
            drop_mask = pd.Series(False, index=trades.index)
            for _, mask, _, _ in combo:
                drop_mask |= mask
            if len(trades) - int(drop_mask.sum()) < min_kept:
                continue
            row = evaluate_keep(trades, ~drop_mask, "drop " + label)
            if row:
                rows.append(row)

    for label, keep in build_score_rules(trades, exclusions):
        if int(keep.sum()) >= min_kept:
            row = evaluate_keep(trades, keep, label)
            if row:
                rows.append(row)

    results = pd.DataFrame(rows)
    results = results.drop_duplicates(subset=["rule", "full_trades", "full_net_points"])
    results = round_floats(results.sort_values(["full_target_frequency", "full_net_points"], ascending=[False, False]))
    results.to_csv(OUTPUT_DIR / "session_liquidity_rr2_exclusion_score_sweep.csv", index=False, encoding="utf-8-sig")
    write_html(results)
    print("=== SESSION LIQUIDITY RR2 EXCLUSION SCORE SWEEP ===")
    print("Input trades:", len(trades), "Rules:", len(results), "Max drop to keep 10/day:", max_single_drop)
    print(results.head(80).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
