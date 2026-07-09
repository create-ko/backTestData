# -*- coding: utf-8 -*-
"""Strategy 2 C-version: keep signal until a new breakout appears.

C signal rule:
- Long breakout creates/replaces an active long limit at that breakout candle's
  bb4_4_lower_open.
- Short breakout creates/replaces an active short limit at that breakout
  candle's bb4_4_upper_open.
- Opposite breakout discards the old signal and starts the new opposite signal.
- The active signal can fill on later candles only when KST entry time is
  08:30 <= time < 23:30.

Exit/grid rule:
- 3 entries every 10P, stop 35P adverse from Entry 1.
- If 1 or 2 entries fill: avg entry +5P, then 5P close trail.
- If 3 entries fill: R2, avg entry +3P에서 70% 감산, 잔량 5P 트레일.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_SCRIPT = SCRIPT_DIR / "92_strategy2_opposite_bb44_limit.py"
RECOVERY_SCRIPT = SCRIPT_DIR / "94_strategy2_grid_third_fill_recovery_rules.py"
OUTPUT_DIR = ROOT / "result" / "strategy2_signal_until_new_breakout_c_r2_cost05"

spec = importlib.util.spec_from_file_location("strategy2_base", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
sys.modules["strategy2_base"] = base
assert spec.loader is not None
spec.loader.exec_module(base)

recovery_spec = importlib.util.spec_from_file_location("strategy2_recovery", RECOVERY_SCRIPT)
recovery = importlib.util.module_from_spec(recovery_spec)
sys.modules["strategy2_recovery"] = recovery
assert recovery_spec.loader is not None
recovery_spec.loader.exec_module(recovery)

TFS = ["5m", "10m"]
SIGNAL_MODE = "until_new_breakout_c"
RECOVERY_RULE = "r2_avg_plus3_70pct"


def find_until_new_breakout_entries(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    rows = []
    idx = df.index
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    bb44_upper = df["bb4_4_upper_open"].to_numpy(dtype=float)
    bb44_lower = df["bb4_4_lower_open"].to_numpy(dtype=float)
    long_break = df["long_breakout"].to_numpy(dtype=bool)
    short_break = df["short_breakout"].to_numpy(dtype=bool)
    sessions = df["session"].astype(str).to_numpy()

    active = None
    for pos in range(len(df)):
        # New breakout is known at candle close. To avoid using stale signals on
        # the same candle as a new breakout, refresh/discard before hit checks.
        # TODO: If intrabar sequence is available, test hit-before-close too.
        if long_break[pos] and not pd.isna(bb44_lower[pos]):
            active = {
                "direction": "long",
                "breakout_pos": pos,
                "limit_price": float(bb44_lower[pos]),
            }
            continue
        if short_break[pos] and not pd.isna(bb44_upper[pos]):
            active = {
                "direction": "short",
                "breakout_pos": pos,
                "limit_price": float(bb44_upper[pos]),
            }
            continue

        if active is None:
            continue
        if pos <= active["breakout_pos"]:
            continue

        direction = active["direction"]
        limit_price = active["limit_price"]
        hit = low[pos] <= limit_price if direction == "long" else high[pos] >= limit_price
        if not hit:
            continue
        if not base.entry_time_allowed(idx[pos]):
            continue

        bi = active["breakout_pos"]
        candle_range = high[bi] - low[bi]
        close_position = math.nan
        if candle_range > 0:
            close_position = (close[bi] - low[bi]) / candle_range if direction == "long" else (high[bi] - close[bi]) / candle_range

        rows.append({
            "tf": tf,
            "direction": direction,
            "signal_mode": SIGNAL_MODE,
            "pending_bars": SIGNAL_MODE,
            "breakout_pos": bi,
            "entry_pos": pos,
            "breakout_time": idx[bi],
            "entry_time": idx[pos],
            "entry_price": limit_price,
            "breakout_close": close[bi],
            "breakout_range": candle_range,
            "breakout_close_position": close_position,
            "session": sessions[pos],
            "year": idx[pos].year,
            "bars_to_fill": pos - bi,
            "bb44_opposite_price": limit_price,
        })
        active = None

    return pd.DataFrame(rows)


def round_report(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(3)
    return out


def grouped_summary(trades: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    rows = []
    for key, group in trades.groupby(cols, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        row = dict(zip(cols, key))
        row.update(recovery.summarize_group(group))
        rows.append(row)
    return round_report(pd.DataFrame(rows))


def build_reports(trades: pd.DataFrame):
    summary = grouped_summary(trades, ["signal_mode", "recovery_rule", "tf", "direction"])
    sessions = grouped_summary(trades, ["signal_mode", "recovery_rule", "tf", "direction", "session"])
    fills = grouped_summary(trades, ["signal_mode", "recovery_rule", "tf", "direction", "filled_entries"])
    exits = grouped_summary(trades, ["signal_mode", "recovery_rule", "tf", "direction", "exit_reason"])
    bars = trades.copy()
    bars["bars_bucket"] = pd.cut(
        bars["bars_to_fill"],
        bins=[0, 3, 6, 10, 20, 50, math.inf],
        labels=["1-3", "4-6", "7-10", "11-20", "21-50", "51+"],
        right=True,
    )
    bars_summary = grouped_summary(bars, ["signal_mode", "recovery_rule", "tf", "direction", "bars_bucket"])
    yearly = grouped_summary(trades, ["signal_mode", "recovery_rule", "tf", "direction", "year"])
    return summary, sessions, fills, exits, bars_summary, yearly


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join(f"<th>{c}</th>" for c in show.columns)
    rows = []
    for _, row in show.iterrows():
        cells = []
        for col, value in row.items():
            klass = ""
            if col in {"expectancy_10p", "expectancy_points", "cumulative_points", "profit_factor"}:
                try:
                    num = float(value)
                    klass = "pos" if (num >= 1 if col == "profit_factor" else num > 0) else "neg"
                except Exception:
                    pass
            if pd.isna(value):
                text = ""
            elif isinstance(value, float):
                text = f"{value*100:.1f}%" if col == "win_rate" or col.endswith("_rate") else f"{value:,.3f}"
            else:
                text = str(value)
            cells.append(f"<td class='{klass}'>{text}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<section><h2>{title}</h2><div class='table-wrap'><table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"


def write_html(summary, sessions, fills, exits, bars_summary, yearly):
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f6f7f9;color:#17202a}
    header{padding:30px 42px;background:#101820;color:white}h1{margin:0 0 8px;font-size:26px}header p{margin:0;color:#c9d3df}
    main{padding:24px 42px 48px;max-width:1900px;margin:0 auto}section{background:white;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{margin:0 0 10px;font-size:18px}.table-wrap{overflow-x:auto;border:1px solid #d9dee7;border-radius:8px}
    table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}
    th{background:#eef2f7}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2),td:nth-child(3),th:nth-child(3),td:nth-child(4),th:nth-child(4){text-align:left}
    """
    html = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Strategy 2 Signal Until New Breakout C</title><style>{css}</style></head>
<body><header><h1>Strategy 2 C: Signal Until New Breakout</h1><p>Same-direction breakout replaces signal, opposite breakout flips/discards. Exit uses R2 recovery after third fill.</p></header><main>
{table_html(summary.sort_values("expectancy_10p", ascending=False), "Config Ranking")}
{table_html(sessions.sort_values("expectancy_10p", ascending=False), "Session Breakdown")}
{table_html(fills.sort_values(["tf", "direction", "filled_entries"]), "Filled Entries Breakdown")}
{table_html(bars_summary.sort_values(["tf", "direction", "bars_bucket"]), "Bars To Fill Breakdown")}
{table_html(yearly.sort_values(["tf", "direction", "year"]), "Yearly Breakdown")}
{table_html(exits.sort_values(["tf", "direction", "exit_reason"]), "Exit Breakdown")}
</main></body></html>"""
    (OUTPUT_DIR / "strategy2_signal_until_new_breakout_c_report.html").write_text(html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for tf in TFS:
        print("LOAD", tf)
        df = base.detect_breakouts(base.load_tf(tf))
        entries = find_until_new_breakout_entries(df, tf)
        print("entries", tf, len(entries))
        data = {
            "idx": df.index,
            "high": df["high"].to_numpy(dtype=float),
            "low": df["low"].to_numpy(dtype=float),
            "close": df["close"].to_numpy(dtype=float),
        }
        for _, entry in entries.iterrows():
            sim = recovery.simulate_recovery_rule(data, entry, RECOVERY_RULE)
            if not sim:
                continue
            out = entry.to_dict()
            out.update(sim)
            out.update({
                "grid_step": recovery.GRID_STEP,
                "max_entries": recovery.MAX_ENTRIES,
                "stop_from_entry1": recovery.STOP_FROM_ENTRY1,
                "regular_trail_arm": recovery.REGULAR_TRAIL_ARM,
                "trail_points": recovery.TRAIL_POINTS,
                "cost_per_unit": recovery.COST_PER_UNIT,
            })
            all_rows.append(out)

    trades = pd.DataFrame(all_rows)
    summary, sessions, fills, exits, bars_summary, yearly = build_reports(trades)
    trades.to_csv(OUTPUT_DIR / "strategy2_signal_until_new_breakout_c_trades.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "strategy2_signal_until_new_breakout_c_summary.csv", index=False, encoding="utf-8-sig")
    sessions.to_csv(OUTPUT_DIR / "strategy2_signal_until_new_breakout_c_by_session.csv", index=False, encoding="utf-8-sig")
    fills.to_csv(OUTPUT_DIR / "strategy2_signal_until_new_breakout_c_by_fills.csv", index=False, encoding="utf-8-sig")
    exits.to_csv(OUTPUT_DIR / "strategy2_signal_until_new_breakout_c_by_exit.csv", index=False, encoding="utf-8-sig")
    bars_summary.to_csv(OUTPUT_DIR / "strategy2_signal_until_new_breakout_c_by_bars_to_fill.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "strategy2_signal_until_new_breakout_c_by_year.csv", index=False, encoding="utf-8-sig")
    write_html(summary, sessions, fills, exits, bars_summary, yearly)

    print("")
    print("=== STRATEGY 2 SIGNAL UNTIL NEW BREAKOUT C ===")
    print("Trades:", len(trades))
    cols = ["signal_mode", "recovery_rule", "tf", "direction", "trades", "win_rate", "expectancy_10p", "profit_factor", "max_drawdown_points", "cumulative_points", "avg_filled_entries", "stop_rate", "recovery_reduce_rate", "avg_bars_to_fill"]
    print(summary.sort_values("expectancy_10p", ascending=False)[cols].to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
