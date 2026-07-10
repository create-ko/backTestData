# -*- coding: utf-8 -*-
"""Previous-day high/low double-sweep reversal fixed 1:2 RR.

This tests a stricter add-on reversal family:
- Track previous-day high and low.
- A sweep event occurs when price pierces that level and closes back inside.
- Only the second or later same-day sweep of the same level can trigger.
- Enter next 2m open in the reversal direction, stop beyond the sweep candle,
  target exactly 2R.

The goal is not to force 10-20 trades/day from this single signal, but to find
another independently positive reversal component that can be combined later.
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
OUTPUT_DIR = ROOT / "result" / "pdh_pdl_double_sweep_reversal_rr2"


spec = importlib.util.spec_from_file_location("base115_for_122", BASE115)
base115 = importlib.util.module_from_spec(spec)
sys.modules["base115_for_122"] = base115
assert spec.loader is not None
spec.loader.exec_module(base115)


OR_BARS = 8
BIAS_MODES = ["none", "price_follow"]
DISPLACEMENT_MODES = ["none", "close_extreme", "body35_close_extreme"]
MIN_GAP_BARS_SET = [3, 6, 12]
MAX_GAP_BARS_SET = [60, 180, 360]
STOP_BUFFERS = [0.2, 0.5]
MIN_RISKS = [0.8]
MAX_RISKS = [3.0, 5.0, 8.0]
MAX_HOLD_BARS_SET = [20, 30, 45]
CONCURRENCY_CAPS = [5]


def find_double_sweep_entries(
    df: pd.DataFrame,
    bias_mode: str,
    displacement_mode: str,
    min_gap_bars: int,
    max_gap_bars: int,
) -> pd.DataFrame:
    idx = df.index
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    session_id = df["session_id"].to_numpy(int)
    session_name = df["session_name"].astype(str).to_numpy()
    kst_date = df["kst_date"].astype(str).to_numpy()
    levels = {
        "pdh": ("short", df["pdh"].to_numpy(float)),
        "pdl": ("long", df["pdl"].to_numpy(float)),
    }
    last_sweep_pos: dict[tuple[str, str], int] = {}
    sweep_count: dict[tuple[str, str], int] = {}
    rows = []

    for pos in range(1, len(df) - 2):
        day = kst_date[pos]
        for level_name, (direction, values) in levels.items():
            level = float(values[pos])
            if not math.isfinite(level):
                continue
            if level_name == "pdh":
                swept = high[pos] >= level and close[pos] < level
            else:
                swept = low[pos] <= level and close[pos] > level
            if not swept:
                continue
            key = (day, level_name)
            prior_pos = last_sweep_pos.get(key)
            count = sweep_count.get(key, 0) + 1
            sweep_count[key] = count
            last_sweep_pos[key] = pos
            if prior_pos is None or count < 2:
                continue
            gap = pos - prior_pos
            if gap < min_gap_bars or gap > max_gap_bars:
                continue
            entry_pos = pos + 1
            if entry_pos >= len(df) or session_id[entry_pos] != session_id[pos]:
                continue
            if not base115.entry_time_allowed(idx[entry_pos]):
                continue
            if not base115.bias_allowed(df, entry_pos, direction, bias_mode):
                continue
            if not base115.displacement_allowed(df, pos, direction, displacement_mode):
                continue
            ts = idx[entry_pos]
            rows.append({
                "level_set": "pdhpdl_double_sweep",
                "signal_mode": "double_sweep_reversal",
                "bias_mode": bias_mode,
                "displacement_mode": displacement_mode,
                "level_name": level_name,
                "direction": direction,
                "breakout_pos": pos,
                "retest_pos": pos,
                "entry_pos": entry_pos,
                "breakout_time": idx[pos],
                "retest_time": idx[pos],
                "entry_time": ts,
                "level": level,
                "entry_price": float(open_[entry_pos]),
                "breakout_high": float(high[pos]),
                "breakout_low": float(low[pos]),
                "retest_high": float(high[pos]),
                "retest_low": float(low[pos]),
                "session": str(session_name[entry_pos]),
                "session_id": int(session_id[entry_pos]),
                "year": int(ts.year),
                "month": ts.strftime("%Y-%m"),
                "day": str(day),
                "sweep_count": count,
                "gap_from_prior_sweep": gap,
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
    header{background:#344e41;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#e9edc9}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    profitable = summary[summary["full_net_points"] > 0].sort_values("full_trades_per_day", ascending=False)
    target = summary[summary["full_target_frequency"]].sort_values("full_net_points", ascending=False)
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>2m PDH/PDL Double Sweep Reversal RR2</title><style>%s</style></head>
<body><header><h1>2m PDH/PDL Double Sweep Reversal RR2</h1><p>Fixed 1:2 RR second-sweep reversal of previous-day high/low.</p></header><main>
%s%s%s
</main></body></html>""" % (
        css,
        table_html(target, "Configs Within 10-20 Trades/Day", 120),
        table_html(profitable, "Profitable Full-Period Configs", 160),
        table_html(summary.sort_values("score", ascending=False), "All Configs Ranked", 220),
    )
    (OUTPUT_DIR / "pdh_pdl_double_sweep_reversal_rr2_report.html").write_text(html, encoding="utf-8")
    if best_trades is None or best_trades.empty:
        return
    best_trades.to_csv(OUTPUT_DIR / "pdh_pdl_double_sweep_reversal_rr2_best_trades.csv", index=False, encoding="utf-8-sig")
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
    yearly.to_csv(OUTPUT_DIR / "pdh_pdl_double_sweep_reversal_rr2_best_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "pdh_pdl_double_sweep_reversal_rr2_best_monthly.csv", index=False, encoding="utf-8-sig")
    period_html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>PDH/PDL Double Sweep Period Report</title><style>%s</style></head>
<body><header><h1>PDH/PDL Double Sweep Period Report</h1><p>Yearly and monthly report for best full-period quality configuration.</p></header><main>
%s%s
</main></body></html>""" % (css, table_html(yearly, "Yearly Report"), table_html(monthly, "Monthly Report"))
    (OUTPUT_DIR / "pdh_pdl_double_sweep_reversal_rr2_best_period_report.html").write_text(period_html, encoding="utf-8")


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_df = base115.add_level_columns(base115.load_data(), OR_BARS)
    trading_days = int(pd.Series(raw_df.index.date).nunique())
    trading_days_2026 = int(pd.Series(raw_df[raw_df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")].index.date).nunique())
    rows = []
    best_trades = None
    best_key = None
    best_net = -math.inf

    for bias_mode in BIAS_MODES:
        for displacement_mode in DISPLACEMENT_MODES:
            for min_gap in MIN_GAP_BARS_SET:
                for max_gap in MAX_GAP_BARS_SET:
                    if min_gap >= max_gap:
                        continue
                    entries = find_double_sweep_entries(raw_df, bias_mode, displacement_mode, min_gap, max_gap)
                    print("ENTRIES", bias_mode, displacement_mode, "gap", min_gap, max_gap, len(entries), flush=True)
                    if entries.empty:
                        continue
                    for stop_buffer in STOP_BUFFERS:
                        for min_risk in MIN_RISKS:
                            for max_risk in MAX_RISKS:
                                if min_risk >= max_risk:
                                    continue
                                for max_hold in MAX_HOLD_BARS_SET:
                                    for cap in CONCURRENCY_CAPS:
                                        trades = base115.simulate_rr2(raw_df, entries, "retest", stop_buffer, min_risk, max_risk, max_hold, cap)
                                        if trades.empty:
                                            continue
                                        trades2026 = trades[trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")]
                                        config_id = "pdhpdl_double_%s_%s_gap%s-%s_sb%s_min%s_max%s_hold%s_cap%s" % (
                                            bias_mode,
                                            displacement_mode,
                                            min_gap,
                                            max_gap,
                                            str(stop_buffer).replace(".", "p"),
                                            str(min_risk).replace(".", "p"),
                                            str(max_risk).replace(".", "p"),
                                            max_hold,
                                            cap,
                                        )
                                        row = {
                                            "config_id": config_id,
                                            "bias_mode": bias_mode,
                                            "displacement_mode": displacement_mode,
                                            "min_gap_bars": min_gap,
                                            "max_gap_bars": max_gap,
                                            "stop_mode": "retest",
                                            "stop_buffer": stop_buffer,
                                            "min_risk": min_risk,
                                            "max_risk": max_risk,
                                            "max_hold_bars": max_hold,
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
                                            + row["full_trades_per_day"] * 30.0
                                            + row["sample2026_net_points"] * 0.10
                                            + (1000.0 if row["full_target_frequency"] else 0.0)
                                        )
                                        rows.append(row)
                                        if row["full_net_points"] > best_net:
                                            best_net = row["full_net_points"]
                                            best_key = config_id
                                            best_trades = trades.copy()

    summary = round_floats(pd.DataFrame(rows).sort_values(["full_target_frequency", "full_net_points"], ascending=[False, False]))
    summary.to_csv(OUTPUT_DIR / "pdh_pdl_double_sweep_reversal_rr2_summary.csv", index=False, encoding="utf-8-sig")
    write_reports(summary, best_trades)
    print("=== 2M PDH/PDL DOUBLE SWEEP REVERSAL RR2 ===")
    print("Configs:", len(summary), "Trading days:", trading_days, "2026 days:", trading_days_2026)
    print("Best full-period config:", best_key)
    print(summary.head(80).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
