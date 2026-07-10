# -*- coding: utf-8 -*-
"""2m extreme BB / structure sweep reversal fixed 1:2 RR sweep.

This branch tests a narrower add-on component for the profitable reversal
basket. It only trades failed extremes:
- price wicks outside BB20/2 and/or sweeps a rolling structural high/low
- the same candle closes back inside the reference level
- entry is the next 2m open in the reversal direction
- stop is beyond the sweep candle, target is exactly 2R
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
BASE115 = SCRIPT_DIR / "115_2m_session_liquidity_rr2_sweep.py"

TEST_START = os.environ.get("TEST_START", "2023-01-01")
TEST_END = os.environ.get("TEST_END", "2026-06-17")
OUTPUT_DIR = ROOT / "result" / "extreme_bb_structure_reversal_rr2"


spec115 = importlib.util.spec_from_file_location("base115_for_126", BASE115)
base115 = importlib.util.module_from_spec(spec115)
sys.modules["base115_for_126"] = base115
assert spec115.loader is not None
spec115.loader.exec_module(base115)


def env_int_list(name: str, default: list[int]) -> list[int]:
    raw = os.environ.get(name)
    return [int(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def env_float_list(name: str, default: list[float]) -> list[float]:
    raw = os.environ.get(name)
    return [float(x.strip()) for x in raw.split(",") if x.strip()] if raw else default


def env_str_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else default


LOOKBACKS = env_int_list("LOOKBACKS", [12, 24, 48])
EXTREME_MODES = env_str_list("EXTREME_MODES", ["bb_only", "structure_only", "bb_and_structure"])
FAILURE_MODES = env_str_list("FAILURE_MODES", ["inside_level", "inside_band", "inside_both"])
BIAS_MODES = env_str_list("BIAS_MODES", ["none", "price_follow"])
DISPLACEMENT_MODES = env_str_list("DISPLACEMENT_MODES", ["close_extreme", "body35_close_extreme"])
COOLDOWN_BARS_SET = env_int_list("COOLDOWN_BARS_SET", [0, 3])
STOP_BUFFERS = env_float_list("STOP_BUFFERS", [0.2, 0.5])
MIN_RISKS = env_float_list("MIN_RISKS", [0.8, 1.5, 2.0, 3.0])
MAX_RISKS = env_float_list("MAX_RISKS", [5.0, 8.0])
MAX_HOLD_BARS_SET = env_int_list("MAX_HOLD_BARS_SET", [20, 30, 45])
CONCURRENCY_CAPS = env_int_list("CONCURRENCY_CAPS", [5])


def load_data() -> pd.DataFrame:
    old_start = base115.TEST_START
    old_end = base115.TEST_END
    base115.TEST_START = TEST_START
    base115.TEST_END = TEST_END
    try:
        return base115.load_data()
    finally:
        base115.TEST_START = old_start
        base115.TEST_END = old_end


def reference_satisfied(mode: str, has_bb: bool, has_structure: bool) -> bool:
    if mode == "bb_only":
        return has_bb
    if mode == "structure_only":
        return has_structure
    if mode == "bb_and_structure":
        return has_bb and has_structure
    raise ValueError("unknown extreme mode: %s" % mode)


def failure_satisfied(
    mode: str,
    direction: str,
    close: float,
    structure_level: float,
    band_level: float,
    has_structure: bool,
    has_bb: bool,
) -> bool:
    inside_structure = (close < structure_level if direction == "short" else close > structure_level) if has_structure else True
    inside_band = (close < band_level if direction == "short" else close > band_level) if has_bb else True
    if mode == "inside_level":
        return inside_structure
    if mode == "inside_band":
        return inside_band
    if mode == "inside_both":
        return inside_structure and inside_band
    raise ValueError("unknown failure mode: %s" % mode)


def find_entries(
    df: pd.DataFrame,
    lookback: int,
    extreme_mode: str,
    failure_mode: str,
    bias_mode: str,
    displacement_mode: str,
    cooldown_bars: int,
) -> pd.DataFrame:
    idx = df.index
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    upper = df["bb20_2_upper_close"].to_numpy(float)
    lower = df["bb20_2_lower_close"].to_numpy(float)
    sessions = df["session_name"].astype(str).to_numpy()
    session_id = df["session_id"].to_numpy(int)
    kst_date = df["kst_date"].astype(str).to_numpy()
    prior_high = df["high"].shift(1).rolling(lookback, min_periods=lookback).max().to_numpy(float)
    prior_low = df["low"].shift(1).rolling(lookback, min_periods=lookback).min().to_numpy(float)
    rows = []
    next_allowed = max(120, lookback + 1)

    for signal_pos in range(max(120, lookback + 1), len(df) - 2):
        if signal_pos < next_allowed:
            continue

        candidates = []
        has_upper_bb = math.isfinite(upper[signal_pos]) and high[signal_pos] > upper[signal_pos]
        has_lower_bb = math.isfinite(lower[signal_pos]) and low[signal_pos] < lower[signal_pos]
        has_upper_structure = math.isfinite(prior_high[signal_pos]) and high[signal_pos] > prior_high[signal_pos]
        has_lower_structure = math.isfinite(prior_low[signal_pos]) and low[signal_pos] < prior_low[signal_pos]

        if reference_satisfied(extreme_mode, has_upper_bb, has_upper_structure):
            level = float(prior_high[signal_pos] if has_upper_structure else upper[signal_pos])
            band = float(upper[signal_pos])
            if failure_satisfied(failure_mode, "short", close[signal_pos], level, band, has_upper_structure, has_upper_bb):
                candidates.append(("short", level, band, "upper"))
        if reference_satisfied(extreme_mode, has_lower_bb, has_lower_structure):
            level = float(prior_low[signal_pos] if has_lower_structure else lower[signal_pos])
            band = float(lower[signal_pos])
            if failure_satisfied(failure_mode, "long", close[signal_pos], level, band, has_lower_structure, has_lower_bb):
                candidates.append(("long", level, band, "lower"))

        if len(candidates) != 1:
            continue

        direction, level, band, side = candidates[0]
        entry_pos = signal_pos + 1
        if session_id[entry_pos] != session_id[signal_pos]:
            continue
        if not base115.bias_allowed(df, entry_pos, direction, bias_mode):
            continue
        if not base115.displacement_allowed(df, signal_pos, direction, displacement_mode):
            continue
        if not base115.entry_time_allowed(idx[entry_pos]):
            continue

        ts = idx[entry_pos]
        rows.append({
            "lookback": lookback,
            "extreme_mode": extreme_mode,
            "failure_mode": failure_mode,
            "bias_mode": bias_mode,
            "displacement_mode": displacement_mode,
            "level_name": "%s_%s" % (side, extreme_mode),
            "direction": direction,
            "breakout_pos": signal_pos,
            "retest_pos": signal_pos,
            "entry_pos": entry_pos,
            "breakout_time": idx[signal_pos],
            "retest_time": idx[signal_pos],
            "entry_time": ts,
            "level": level,
            "band_level": band,
            "entry_price": float(open_[entry_pos]),
            "breakout_high": float(high[signal_pos]),
            "breakout_low": float(low[signal_pos]),
            "retest_high": float(high[signal_pos]),
            "retest_low": float(low[signal_pos]),
            "session": str(sessions[entry_pos]),
            "session_id": int(session_id[entry_pos]),
            "year": int(ts.year),
            "month": ts.strftime("%Y-%m"),
            "day": str(kst_date[entry_pos]),
        })
        next_allowed = signal_pos + cooldown_bars + 1

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def prefix_metrics(prefix: str, metrics: dict) -> dict:
    return {prefix + "_" + key: value for key, value in metrics.items()}


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    return base115.round_floats(df)


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


def write_reports(summary: pd.DataFrame, best_target: pd.DataFrame | None, best_quality: pd.DataFrame | None) -> None:
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#2f3437;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#d8e7e2}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    target = summary[summary["full_target_frequency"]].sort_values("full_net_points", ascending=False)
    profitable = summary[summary["full_net_points"] > 0].sort_values("full_trades_per_day", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m Extreme BB Structure Reversal RR2</title><style>%s</style></head>
<body><header><h1>2m Extreme BB Structure Reversal RR2</h1><p>Fixed 1:2 RR reversal after failed BB/structure extremes.</p></header><main>
%s%s%s
</main></body></html>""" % (
        css,
        table_html(target, "Configs Within 10-20 Trades/Day On Full Period", 160),
        table_html(profitable, "Profitable Full-Period Configs", 160),
        table_html(summary.sort_values("score", ascending=False), "All Configs Ranked", 240),
    )
    (OUTPUT_DIR / "extreme_bb_structure_reversal_rr2_report.html").write_text(html, encoding="utf-8")

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

    write_period("best_target_frequency", best_target)
    write_period("best_quality", best_quality)


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data()
    trading_days = int(pd.Series(df.index.date).nunique())
    trading_days_2026 = int(pd.Series(df[df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")].index.date).nunique())
    rows = []
    best_target = None
    best_target_key = None
    best_target_net = -math.inf
    best_quality = None
    best_quality_key = None
    best_quality_net = -math.inf

    for lookback in LOOKBACKS:
        for extreme_mode in EXTREME_MODES:
            for failure_mode in FAILURE_MODES:
                if extreme_mode == "bb_only" and failure_mode == "inside_level":
                    continue
                if extreme_mode == "structure_only" and failure_mode == "inside_band":
                    continue
                for bias_mode in BIAS_MODES:
                    for displacement_mode in DISPLACEMENT_MODES:
                        for cooldown_bars in COOLDOWN_BARS_SET:
                            entries = find_entries(df, lookback, extreme_mode, failure_mode, bias_mode, displacement_mode, cooldown_bars)
                            print(
                                "ENTRIES",
                                "lb", lookback,
                                "extreme", extreme_mode,
                                "fail", failure_mode,
                                "bias", bias_mode,
                                "disp", displacement_mode,
                                "cooldown", cooldown_bars,
                                len(entries),
                                flush=True,
                            )
                            if entries.empty:
                                continue
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
                                                    "retest",
                                                    stop_buffer,
                                                    min_risk,
                                                    max_risk,
                                                    max_hold_bars,
                                                    cap,
                                                )
                                                if trades.empty:
                                                    continue
                                                trades2026 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
                                                config_id = "lb%s_%s_%s_%s_%s_cd%s_sb%s_min%s_max%s_hold%s_cap%s" % (
                                                    lookback,
                                                    extreme_mode,
                                                    failure_mode,
                                                    bias_mode,
                                                    displacement_mode,
                                                    cooldown_bars,
                                                    str(stop_buffer).replace(".", "p"),
                                                    str(min_risk).replace(".", "p"),
                                                    str(max_risk).replace(".", "p"),
                                                    max_hold_bars,
                                                    cap,
                                                )
                                                row = {
                                                    "config_id": config_id,
                                                    "lookback": lookback,
                                                    "extreme_mode": extreme_mode,
                                                    "failure_mode": failure_mode,
                                                    "bias_mode": bias_mode,
                                                    "displacement_mode": displacement_mode,
                                                    "cooldown_bars": cooldown_bars,
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
                                                    - row["full_max_drawdown_points"] * 0.15
                                                    + row["full_positive_month_rate"] * 5.0
                                                    + row["full_trades_per_day"] * 35.0
                                                    + row["sample2026_net_points"] * 0.05
                                                )
                                                rows.append(row)
                                                if row["full_target_frequency"] and row["full_net_points"] > best_target_net:
                                                    best_target_net = row["full_net_points"]
                                                    best_target_key = config_id
                                                    best_target = trades.copy()
                                                if row["full_net_points"] > best_quality_net:
                                                    best_quality_net = row["full_net_points"]
                                                    best_quality_key = config_id
                                                    best_quality = trades.copy()

    summary = round_floats(pd.DataFrame(rows).sort_values(["full_target_frequency", "full_net_points"], ascending=[False, False]))
    summary.to_csv(OUTPUT_DIR / "extreme_bb_structure_reversal_rr2_summary.csv", index=False, encoding="utf-8-sig")
    write_reports(summary, best_target, best_quality)
    print("=== 2M EXTREME BB STRUCTURE REVERSAL RR2 ===")
    print("Configs:", len(summary), "Trading days:", trading_days, "2026 days:", trading_days_2026)
    print("Best target-frequency config:", best_target_key)
    print("Best quality config:", best_quality_key)
    print(summary.head(80).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
