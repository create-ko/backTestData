# -*- coding: utf-8 -*-
"""Sweep Strategy2 grid variants across 2m/5m/10m/15m.

This builds on 100_strategy2_grid_multitimeframe_month_filter.py and compares:
- trend_mode=bb_only: double-BB breakout direction + monthly regime filter.
- trend_mode=sma120: double-BB breakout plus SMA20/120 slope agreement.
- signal_mode=pending_3/6/10: limit valid for fixed bars after breakout.
- signal_mode=until_new: limit valid until another breakout replaces it.
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
BASE_SCRIPT = SCRIPT_DIR / "100_strategy2_grid_multitimeframe_month_filter.py"
OUTPUT_DIR = ROOT / "result" / "strategy2_grid_multitimeframe_sweep"

spec = importlib.util.spec_from_file_location("strategy2_mtf", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
sys.modules["strategy2_mtf"] = base
assert spec.loader is not None
spec.loader.exec_module(base)

TREND_MODES = ["bb_only", "sma120"]
SIGNAL_MODES = ["pending_3", "pending_6", "pending_10", "until_new"]


def env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [x.strip() for x in raw.split(",") if x.strip()]


def apply_trend_mode(df: pd.DataFrame, trend_mode: str) -> pd.DataFrame:
    out = df.copy()
    if trend_mode == "sma120":
        return out
    if trend_mode != "bb_only":
        raise ValueError("unknown trend_mode: %s" % trend_mode)
    out["long_breakout"] = (
        (out["close"] > out["bb20_2_upper_close"])
        & (out["close"] > out["bb4_4_upper_open"])
    ).fillna(False)
    out["short_breakout"] = (
        (out["close"] < out["bb20_2_lower_close"])
        & (out["close"] < out["bb4_4_lower_open"])
    ).fillna(False)
    return out


def find_entries_mode(df: pd.DataFrame, tf: str, active_months: set[str], signal_mode: str) -> pd.DataFrame:
    if signal_mode == "until_new":
        out = base.find_entries(df, tf, active_months)
        if not out.empty:
            out["signal_mode"] = signal_mode
        return out

    try:
        pending_bars = int(signal_mode.split("_")[1])
    except Exception as exc:
        raise ValueError("bad signal_mode: %s" % signal_mode) from exc

    rows = []
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    bb44_upper = df["bb4_4_upper_open"].to_numpy(float)
    bb44_lower = df["bb4_4_lower_open"].to_numpy(float)
    long_break = df["long_breakout"].to_numpy(bool)
    short_break = df["short_breakout"].to_numpy(bool)

    for bi in range(len(df) - 2):
        month = idx[bi].strftime("%Y-%m")
        if month not in active_months:
            continue
        direction = None
        limit_price = math.nan
        if long_break[bi] and not pd.isna(bb44_lower[bi]):
            direction = "long"
            limit_price = float(bb44_lower[bi])
        elif short_break[bi] and not pd.isna(bb44_upper[bi]):
            direction = "short"
            limit_price = float(bb44_upper[bi])
        else:
            continue

        entry_pos = None
        end = min(len(df) - 1, bi + pending_bars)
        for pos in range(bi + 1, end + 1):
            if idx[pos].strftime("%Y-%m") not in active_months:
                break
            hit = low[pos] <= limit_price if direction == "long" else high[pos] >= limit_price
            if hit and base.entry_time_allowed(idx[pos]):
                entry_pos = pos
                break
            if hit:
                break
        if entry_pos is None:
            continue

        candle_range = float(high[bi] - low[bi])
        close_pos = math.nan
        if candle_range > 0:
            close_pos = float((close[bi] - low[bi]) / candle_range) if direction == "long" else float((high[bi] - close[bi]) / candle_range)
        rows.append({
            "tf": tf,
            "direction": direction,
            "signal_mode": signal_mode,
            "breakout_pos": bi,
            "entry_pos": entry_pos,
            "breakout_time": idx[bi],
            "entry_time": idx[entry_pos],
            "entry_price": limit_price,
            "breakout_close_position": close_pos,
            "bars_to_fill": entry_pos - bi,
            "session": str(df["session"].iloc[entry_pos]),
            "year": int(idx[entry_pos].year),
            "month": idx[entry_pos].strftime("%Y-%m"),
            "day": idx[entry_pos].date().isoformat(),
        })
    return pd.DataFrame(rows)


def run_config(tf: str, df: pd.DataFrame, active_months: set[str], trend_mode: str, signal_mode: str) -> pd.DataFrame:
    work = apply_trend_mode(df, trend_mode)
    entries = find_entries_mode(work, tf, active_months, signal_mode)
    if entries.empty:
        return pd.DataFrame()
    rows = []
    next_allowed_pos = 0
    for _, entry in entries.sort_values("entry_pos").iterrows():
        if int(entry["entry_pos"]) < next_allowed_pos:
            continue
        sim = base.simulate_trade(work, entry)
        out = entry.to_dict()
        out.update(sim)
        out["trend_mode"] = trend_mode
        out["signal_mode"] = signal_mode
        rows.append(out)
        next_allowed_pos = int(work.index.searchsorted(sim["exit_time"])) + 1
    return pd.DataFrame(rows)


def grouped(trades: pd.DataFrame, cols: list[str], extra_cost: float = 0.0) -> pd.DataFrame:
    rows = []
    for key, group in trades.groupby(cols, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        row = dict(zip(cols, key))
        row.update(base.summarize_group(group, extra_cost=extra_cost))
        rows.append(row)
    return base.round_floats(pd.DataFrame(rows))


def write_html(summary, cost, yearly, monthly):
    def table(df, title):
        headers = "".join("<th>%s</th>" % c for c in df.columns)
        rows = []
        for _, row in df.iterrows():
            cells = []
            for col, value in row.items():
                cls = ""
                if col in {"net_points", "avg_points", "profit_factor"}:
                    try:
                        num = float(value)
                        cls = "pos" if (num >= 1 if col == "profit_factor" else num > 0) else "neg"
                    except Exception:
                        pass
                text = "" if pd.isna(value) else ("%.4f" % value if isinstance(value, float) else str(value))
                cells.append("<td class='%s'>%s</td>" % (cls, text))
            rows.append("<tr>%s</tr>" % "".join(cells))
        return "<section><h2>%s</h2><div><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></section>" % (title, headers, "".join(rows))

    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#17202a}
    header{background:#101820;color:#fff;padding:30px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#c9d3df}
    main{max-width:1900px;margin:0 auto;padding:24px 42px 48px}section{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}th{background:#eef2f7}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2),td:nth-child(3),th:nth-child(3){text-align:left}
    .pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Strategy2 MTF Sweep</title><style>%s</style></head>
<body><header><h1>Strategy2 Grid Multi-Timeframe Sweep</h1><p>BB20/2 close + BB4/4 open, monthly filter, KST 09:00-18:00, day stop -50P. Compares trend and signal-validity modes.</p></header><main>
%s%s%s%s
</main></body></html>""" % (
        css,
        table(summary.sort_values("net_points", ascending=False), "Config Ranking"),
        table(cost.sort_values(["tf", "trend_mode", "signal_mode", "extra_cost_per_unit"]), "Cost Sensitivity"),
        table(yearly.sort_values(["tf", "trend_mode", "signal_mode", "year"]), "Yearly Report"),
        table(monthly.sort_values(["tf", "trend_mode", "signal_mode", "month"]), "Monthly Report"),
    )
    (OUTPUT_DIR / "strategy2_grid_multitimeframe_sweep_report.html").write_text(html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    month_features, active_months, active_days = base.build_month_features()
    month_features.to_csv(OUTPUT_DIR / "month_features.csv", index=False, encoding="utf-8-sig")

    raw_parts = []
    selected_parts = []
    tfs = env_list("SWEEP_TFS", base.TFS)
    trend_modes = env_list("SWEEP_TREND_MODES", TREND_MODES)
    signal_modes = env_list("SWEEP_SIGNAL_MODES", SIGNAL_MODES)
    for tf in tfs:
        print("LOAD", tf, flush=True)
        df = base.load_tf(tf)
        for trend_mode in trend_modes:
            for signal_mode in signal_modes:
                print("RUN", tf, trend_mode, signal_mode, flush=True)
                trades = run_config(tf, df, active_months, trend_mode, signal_mode)
                print("raw", len(trades), flush=True)
                raw_parts.append(trades)
                if not trades.empty:
                    selected_parts.append(base.apply_day_stop(trades))

    raw = pd.concat(raw_parts, ignore_index=True) if raw_parts else pd.DataFrame()
    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else pd.DataFrame()

    summary = grouped(selected, ["tf", "trend_mode", "signal_mode"])
    yearly = grouped(selected, ["tf", "trend_mode", "signal_mode", "year"])
    monthly = grouped(selected, ["tf", "trend_mode", "signal_mode", "month"])
    cost_parts = []
    for extra in [0.0, 0.2, 0.3, 0.5, 0.8, 1.0]:
        c = grouped(selected, ["tf", "trend_mode", "signal_mode"], extra_cost=extra)
        c.insert(3, "extra_cost_per_unit", extra)
        cost_parts.append(c)
    cost = pd.concat(cost_parts, ignore_index=True)

    raw.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_sweep_raw_trades.csv", index=False, encoding="utf-8-sig")
    selected.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_sweep_selected_trades.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_sweep_summary.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_sweep_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_sweep_monthly.csv", index=False, encoding="utf-8-sig")
    cost.to_csv(OUTPUT_DIR / "strategy2_grid_multitimeframe_sweep_cost_sensitivity.csv", index=False, encoding="utf-8-sig")
    write_html(summary, cost, yearly, monthly)

    print("")
    print("=== STRATEGY2 GRID MTF SWEEP ===")
    print("Active months:", int(month_features["active"].sum()), "active days:", active_days)
    print(summary.sort_values("net_points", ascending=False).head(20).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
