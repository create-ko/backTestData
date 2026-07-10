# -*- coding: utf-8 -*-
"""Immediate-entry 2m session-liquidity fixed 1:2 RR sweep.

This branch keeps the same session liquidity levels as script 115, but does
not wait for a retest. It enters on the next 2m open after either:
- a close breakout through a level in the breakout direction, or
- a sweep through a level and close back inside in the reversal direction.

The hypothesis is that avoiding late retests may improve 2R follow-through
while keeping the requested 10-20 trades/day frequency band.
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
OUTPUT_DIR = ROOT / "result" / "session_liquidity_immediate_rr2_sweep"


spec = importlib.util.spec_from_file_location("base115_for_119", BASE115)
base115 = importlib.util.module_from_spec(spec)
sys.modules["base115_for_119"] = base115
assert spec.loader is not None
spec.loader.exec_module(base115)


LEVEL_SETS = ["or,pdhpdl,prev_session,session_dynamic"]
OR_BARS_SET = [8]
SIGNAL_MODES = ["breakout_momentum", "sweep_reversal_immediate", "combined_immediate"]
BIAS_MODES = ["price_follow"]
DISPLACEMENT_MODES = ["close_extreme", "body35_close_extreme"]
COOLDOWN_BARS_SET = [0, 3]
STOP_MODES = ["retest"]
STOP_BUFFERS = [0.2]
MIN_RISKS = [0.8]
MAX_RISKS = [5.0]
MAX_HOLD_BARS_SET = [20, 30]
CONCURRENCY_CAPS = [5]


def find_immediate_entries(
    df: pd.DataFrame,
    level_set: str,
    signal_mode: str,
    bias_mode: str,
    displacement_mode: str,
    cooldown_bars: int,
) -> pd.DataFrame:
    if signal_mode == "combined_immediate":
        parts = [
            find_immediate_entries(df, level_set, "breakout_momentum", bias_mode, displacement_mode, cooldown_bars),
            find_immediate_entries(df, level_set, "sweep_reversal_immediate", bias_mode, displacement_mode, cooldown_bars),
        ]
        parts = [part for part in parts if not part.empty]
        return pd.concat(parts, ignore_index=True).sort_values("entry_time").reset_index(drop=True) if parts else pd.DataFrame()

    idx = df.index
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    prev_close = df["close"].shift(1).to_numpy(float)
    session_id = df["session_id"].to_numpy(int)
    session_name = df["session_name"].astype(str).to_numpy()
    kst_date = df["kst_date"].astype(str).to_numpy()
    levels = {name: df[name].to_numpy(float) for name, _, _ in base115.level_specs(level_set)}
    rows = []
    last_signal_pos: dict[tuple[str, str, str], int] = {}

    for level_col, direction, level_name in base115.level_specs(level_set):
        values = levels[level_col]
        for signal_pos in range(1, len(df) - 2):
            level = float(values[signal_pos])
            if not math.isfinite(level):
                continue
            trade_direction = direction
            if signal_mode == "breakout_momentum":
                if direction == "long":
                    triggered = close[signal_pos] > level and prev_close[signal_pos] <= level
                else:
                    triggered = close[signal_pos] < level and prev_close[signal_pos] >= level
            elif signal_mode == "sweep_reversal_immediate":
                if direction == "long":
                    triggered = high[signal_pos] >= level and close[signal_pos] < level
                    trade_direction = "short"
                else:
                    triggered = low[signal_pos] <= level and close[signal_pos] > level
                    trade_direction = "long"
            else:
                raise ValueError("unknown signal mode: %s" % signal_mode)
            if not triggered:
                continue

            key = (signal_mode, level_name, trade_direction)
            if cooldown_bars and signal_pos - last_signal_pos.get(key, -10**9) < cooldown_bars:
                continue
            entry_pos = signal_pos + 1
            if entry_pos >= len(df) or session_id[entry_pos] != session_id[signal_pos]:
                continue
            if not base115.bias_allowed(df, entry_pos, trade_direction, bias_mode):
                continue
            if not base115.displacement_allowed(df, signal_pos, trade_direction, displacement_mode):
                continue
            if not base115.entry_time_allowed(idx[entry_pos]):
                continue

            last_signal_pos[key] = signal_pos
            ts = idx[entry_pos]
            rows.append({
                "level_set": level_set,
                "signal_mode": signal_mode,
                "bias_mode": bias_mode,
                "displacement_mode": displacement_mode,
                "level_name": level_name,
                "direction": trade_direction,
                "breakout_pos": signal_pos,
                "retest_pos": signal_pos,
                "entry_pos": entry_pos,
                "breakout_time": idx[signal_pos],
                "retest_time": idx[signal_pos],
                "entry_time": ts,
                "level": level,
                "entry_price": float(open_[entry_pos]),
                "breakout_high": float(high[signal_pos]),
                "breakout_low": float(low[signal_pos]),
                "retest_high": float(high[signal_pos]),
                "retest_low": float(low[signal_pos]),
                "session": str(session_name[entry_pos]),
                "session_id": int(session_id[entry_pos]),
                "year": int(ts.year),
                "month": ts.strftime("%Y-%m"),
                "day": str(kst_date[entry_pos]),
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


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


def write_reports(summary: pd.DataFrame, best_trades: pd.DataFrame | None) -> None:
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#1f2937;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#dbe4ef}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    target = summary[summary["full_target_frequency"]].sort_values("full_net_points", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m Session Liquidity Immediate RR2 Sweep</title><style>%s</style></head>
<body><header><h1>2m Session Liquidity Immediate RR2 Sweep</h1><p>Fixed 1:2 RR immediate-entry level break and sweep candidates.</p></header><main>
%s%s
</main></body></html>""" % (
        css,
        table_html(target, "Configs Within 10-20 Trades/Day On Full Period", 180),
        table_html(summary.sort_values("score", ascending=False), "All Configs Ranked", 240),
    )
    (OUTPUT_DIR / "session_liquidity_immediate_rr2_sweep_report.html").write_text(html, encoding="utf-8")

    if best_trades is None or best_trades.empty:
        return
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
    yearly.to_csv(OUTPUT_DIR / "session_liquidity_immediate_rr2_best_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "session_liquidity_immediate_rr2_best_monthly.csv", index=False, encoding="utf-8-sig")
    period_html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m Session Liquidity Immediate RR2 Period Report</title><style>%s</style></head>
<body><header><h1>2m Session Liquidity Immediate RR2 Period Report</h1><p>Yearly and monthly report for the selected target-frequency configuration.</p></header><main>
%s%s
</main></body></html>""" % (css, table_html(yearly, "Yearly Report"), table_html(monthly, "Monthly Report"))
    (OUTPUT_DIR / "session_liquidity_immediate_rr2_best_period_report.html").write_text(period_html, encoding="utf-8")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_df = base115.load_data()
    trading_days = int(pd.Series(raw_df.index.date).nunique())
    trading_days_2026 = int(pd.Series(raw_df[raw_df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")].index.date).nunique())
    rows = []
    best_trades = None
    best_key = None
    best_net = -math.inf

    for or_bars in OR_BARS_SET:
        df = base115.add_level_columns(raw_df, or_bars)
        for level_set in LEVEL_SETS:
            for signal_mode in SIGNAL_MODES:
                for bias_mode in BIAS_MODES:
                    for displacement_mode in DISPLACEMENT_MODES:
                        for cooldown_bars in COOLDOWN_BARS_SET:
                            entries = find_immediate_entries(df, level_set, signal_mode, bias_mode, displacement_mode, cooldown_bars)
                            print(
                                "ENTRIES",
                                "or", or_bars,
                                "levels", level_set,
                                "mode", signal_mode,
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
                                            for max_hold_bars in MAX_HOLD_BARS_SET:
                                                for cap in CONCURRENCY_CAPS:
                                                    trades = base115.simulate_rr2(df, entries, stop_mode, stop_buffer, min_risk, max_risk, max_hold_bars, cap)
                                                    if trades.empty:
                                                        continue
                                                    trades2026 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
                                                    config_id = "or%s_%s_%s_%s_%s_cd%s_%s_sb%s_min%s_max%s_hold%s_cap%s" % (
                                                        or_bars,
                                                        level_set.replace(",", "-"),
                                                        signal_mode,
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
                                                        "signal_mode": signal_mode,
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
                                                    if row["full_target_frequency"] and row["full_net_points"] > best_net:
                                                        best_net = row["full_net_points"]
                                                        best_key = config_id
                                                        best_trades = trades.copy()

    summary = round_floats(pd.DataFrame(rows).sort_values(["full_target_frequency", "full_net_points"], ascending=[False, False]))
    summary.to_csv(OUTPUT_DIR / "session_liquidity_immediate_rr2_sweep_summary.csv", index=False, encoding="utf-8-sig")
    if best_trades is not None:
        best_trades.to_csv(OUTPUT_DIR / "session_liquidity_immediate_rr2_best_trades.csv", index=False, encoding="utf-8-sig")
    write_reports(summary, best_trades)
    print("=== 2M SESSION LIQUIDITY IMMEDIATE RR2 SWEEP ===")
    print("Configs:", len(summary), "Trading days:", trading_days, "2026 days:", trading_days_2026)
    print("Best target-frequency config:", best_key)
    print(summary.head(60).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
