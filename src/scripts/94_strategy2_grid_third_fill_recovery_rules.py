# -*- coding: utf-8 -*-
"""Strategy 2 grid recovery-rule comparison for third fill.

Base setup:
- Strategy 2 opposite BB4/4 limit entry.
- Entry 1 at breakout candle opposite BB4/4 band.
- Entry 2/3 every 10P adverse.
- Stop 35P adverse from Entry 1.
- If only 1 or 2 entries fill: avg entry +5P, then 5P close-based trail.

Third-fill rules:
- R1: after 3 fills, full exit at avg entry recovery.
- R2: after 3 fills, exit 70% at avg entry +3P, trail remaining 30% by 5P.
- R3: after 3 fills, exit 70% at avg entry recovery, trail remaining 30% by 5P.
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
OUTPUT_DIR = ROOT / "result" / "strategy2_grid_third_fill_recovery_rules_cost05"

spec = importlib.util.spec_from_file_location("strategy2_base", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
sys.modules["strategy2_base"] = base
assert spec.loader is not None
spec.loader.exec_module(base)

TFS = ["5m", "10m"]
PENDING_WINDOWS = [3, 6, 10]
RECOVERY_RULES = ["r1_avg_full_exit", "r2_avg_plus3_70pct", "r3_avg_70pct"]
GRID_STEP = 10.0
MAX_ENTRIES = 3
STOP_FROM_ENTRY1 = 35.0
REGULAR_TRAIL_ARM = 5.0
TRAIL_POINTS = 5.0
R2_RECOVERY_PROFIT = 3.0
REDUCE_FRACTION = 0.70
COST_PER_UNIT = 0.50


def grid_levels(entry1: float, direction: str) -> list[float]:
    if direction == "long":
        return [entry1 - i * GRID_STEP for i in range(MAX_ENTRIES)]
    return [entry1 + i * GRID_STEP for i in range(MAX_ENTRIES)]


def favorable_hit(direction: str, high: float, low: float, price: float) -> bool:
    return high >= price if direction == "long" else low <= price


def adverse_stop_hit(direction: str, high: float, low: float, stop: float) -> bool:
    return low <= stop if direction == "long" else high >= stop


def pnl_for_exit(direction: str, avg_entry: float, exit_price: float, qty: float) -> float:
    if direction == "long":
        return (exit_price - avg_entry) * qty
    return (avg_entry - exit_price) * qty


def update_trail(direction: str, current: float, close: float, avg_entry: float) -> float:
    if direction == "long":
        next_trail = close - TRAIL_POINTS
        if math.isnan(current):
            return max(avg_entry, next_trail)
        return max(current, avg_entry, next_trail)
    next_trail = close + TRAIL_POINTS
    if math.isnan(current):
        return min(avg_entry, next_trail)
    return min(current, avg_entry, next_trail)


def trail_hit(direction: str, high: float, low: float, trail_stop: float) -> bool:
    if math.isnan(trail_stop):
        return False
    return low <= trail_stop if direction == "long" else high >= trail_stop


def simulate_recovery_rule(data: dict, row: pd.Series, recovery_rule: str) -> dict:
    direction = row["direction"]
    entry_pos = int(row["entry_pos"])
    entry1 = float(row["entry_price"])
    levels = grid_levels(entry1, direction)
    stop = entry1 - STOP_FROM_ENTRY1 if direction == "long" else entry1 + STOP_FROM_ENTRY1

    idx = data["idx"]
    high = data["high"]
    low = data["low"]
    close = data["close"]

    filled = [False] * MAX_ENTRIES
    fill_times = [pd.NaT] * MAX_ENTRIES
    fill_prices: list[float] = []
    open_qty = 0.0
    avg_entry = math.nan
    realized = 0.0
    reduced_after_third = False
    trailing_armed = False
    trail_stop = math.nan
    trail_active_from = math.inf
    max_favorable = 0.0
    max_adverse = 0.0
    exit_reason = "open_at_data_end"
    exit_price = float(close[-1])
    exit_time = idx[-1]
    partial_exit_price = math.nan
    partial_exit_qty = 0.0
    partial_exit_time = pd.NaT

    for pos in range(entry_pos, len(idx)):
        t = idx[pos]
        hi = float(high[pos])
        lo = float(low[pos])
        cl = float(close[pos])

        for i, level in enumerate(levels):
            if filled[i]:
                continue
            hit = lo <= level if direction == "long" else hi >= level
            if hit:
                filled[i] = True
                fill_times[i] = t
                fill_prices.append(level)
                open_qty += 1.0
                avg_entry = sum(fill_prices) / len(fill_prices)

        if open_qty <= 0 or pd.isna(avg_entry):
            continue

        if direction == "long":
            max_favorable = max(max_favorable, hi - avg_entry)
            max_adverse = max(max_adverse, avg_entry - lo)
        else:
            max_favorable = max(max_favorable, avg_entry - lo)
            max_adverse = max(max_adverse, hi - avg_entry)

        if adverse_stop_hit(direction, hi, lo, stop):
            realized += pnl_for_exit(direction, avg_entry, stop, open_qty)
            exit_reason = "stop_35p"
            exit_price = stop
            exit_time = t
            open_qty = 0.0
            break

        filled_count = len(fill_prices)
        if filled_count >= 3 and not reduced_after_third:
            if recovery_rule == "r1_avg_full_exit":
                recovery_price = avg_entry
                if favorable_hit(direction, hi, lo, recovery_price):
                    realized += pnl_for_exit(direction, avg_entry, recovery_price, open_qty)
                    exit_reason = "r1_avg_full_exit"
                    exit_price = recovery_price
                    exit_time = t
                    open_qty = 0.0
                    break
            elif recovery_rule == "r2_avg_plus3_70pct":
                recovery_price = avg_entry + R2_RECOVERY_PROFIT if direction == "long" else avg_entry - R2_RECOVERY_PROFIT
                if favorable_hit(direction, hi, lo, recovery_price):
                    qty = open_qty * REDUCE_FRACTION
                    realized += pnl_for_exit(direction, avg_entry, recovery_price, qty)
                    open_qty -= qty
                    reduced_after_third = True
                    partial_exit_price = recovery_price
                    partial_exit_qty = qty
                    partial_exit_time = t
                    trailing_armed = True
                    trail_stop = avg_entry
                    trail_active_from = pos + 1
            elif recovery_rule == "r3_avg_70pct":
                recovery_price = avg_entry
                if favorable_hit(direction, hi, lo, recovery_price):
                    qty = open_qty * REDUCE_FRACTION
                    realized += pnl_for_exit(direction, avg_entry, recovery_price, qty)
                    open_qty -= qty
                    reduced_after_third = True
                    partial_exit_price = recovery_price
                    partial_exit_qty = qty
                    partial_exit_time = t
                    trailing_armed = True
                    trail_stop = avg_entry
                    trail_active_from = pos + 1

        if open_qty <= 0:
            break

        if trailing_armed and pos >= trail_active_from and trail_hit(direction, hi, lo, trail_stop):
            realized += pnl_for_exit(direction, avg_entry, trail_stop, open_qty)
            exit_reason = "recovery_trail_5p" if reduced_after_third else "regular_trail_5p"
            exit_price = trail_stop
            exit_time = t
            open_qty = 0.0
            break

        if reduced_after_third:
            trail_stop = update_trail(direction, trail_stop, cl, avg_entry)
            continue

        regular_arm_hit = cl >= avg_entry + REGULAR_TRAIL_ARM if direction == "long" else cl <= avg_entry - REGULAR_TRAIL_ARM
        if regular_arm_hit:
            trailing_armed = True
            trail_stop = update_trail(direction, trail_stop, cl, avg_entry)
            trail_active_from = min(trail_active_from, pos + 1)

    if len(fill_prices) <= 0 or pd.isna(avg_entry):
        return {}

    if open_qty > 0:
        final_close = float(close[-1])
        realized += pnl_for_exit(direction, avg_entry, final_close, open_qty)
        exit_price = final_close
        exit_time = idx[-1]

    filled_entries = len(fill_prices)
    cost_total = COST_PER_UNIT * filled_entries
    net_total = realized - cost_total

    return {
        "recovery_rule": recovery_rule,
        "entry_1_price": levels[0],
        "entry_2_price": levels[1],
        "entry_3_price": levels[2],
        "entry_1_time": fill_times[0],
        "entry_2_time": fill_times[1],
        "entry_3_time": fill_times[2],
        "filled_entries": int(filled_entries),
        "avg_entry": avg_entry,
        "stop_price": stop,
        "partial_exit_time": partial_exit_time,
        "partial_exit_price": partial_exit_price,
        "partial_exit_qty": partial_exit_qty,
        "reduced_after_third": bool(reduced_after_third),
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_points_total": realized,
        "cost_points_total": cost_total,
        "net_points_total": net_total,
        "net_10p": net_total / 10.0,
        "mfe_points": max_favorable,
        "mae_points": max_adverse,
        "mfe_10p": max_favorable / 10.0,
        "mae_10p": max_adverse / 10.0,
        "trailing_armed": bool(trailing_armed),
        "hold_bars": int(idx.searchsorted(exit_time) - entry_pos + 1),
    }


def profit_factor(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    gp = vals[vals > 0].sum()
    gl = abs(vals[vals < 0].sum())
    if gl == 0:
        return math.inf if gp > 0 else 0.0
    return float(gp / gl)


def max_drawdown(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").fillna(0.0)
    eq = vals.cumsum()
    dd = eq.cummax() - eq
    return float(dd.max()) if len(dd) else 0.0


def summarize_group(group: pd.DataFrame) -> dict:
    pnl = pd.to_numeric(group["net_points_total"], errors="coerce")
    exits = group["exit_reason"].astype(str)
    return {
        "trades": int(len(group)),
        "win_rate": float((pnl > 0).mean()),
        "expectancy_points": float(pnl.mean()),
        "expectancy_10p": float(group["net_10p"].mean()),
        "profit_factor": profit_factor(pnl),
        "max_drawdown_points": max_drawdown(pnl),
        "cumulative_points": float(pnl.sum()),
        "avg_filled_entries": float(group["filled_entries"].mean()),
        "stop_rate": float((exits == "stop_35p").mean()),
        "recovery_reduce_rate": float(group["reduced_after_third"].mean()),
        "avg_mfe_10p": float(group["mfe_10p"].mean()),
        "avg_mae_10p": float(group["mae_10p"].mean()),
        "avg_bars_to_fill": float(group["bars_to_fill"].mean()),
    }


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
        row.update(summarize_group(group))
        rows.append(row)
    return round_report(pd.DataFrame(rows))


def build_reports(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary = grouped_summary(trades, ["recovery_rule", "tf", "direction", "pending_bars"])
    sessions = grouped_summary(trades, ["recovery_rule", "tf", "direction", "pending_bars", "session"])
    fills = grouped_summary(trades, ["recovery_rule", "tf", "direction", "pending_bars", "filled_entries"])
    exits = grouped_summary(trades, ["recovery_rule", "tf", "direction", "pending_bars", "exit_reason"])
    yearly = grouped_summary(trades, ["recovery_rule", "tf", "direction", "pending_bars", "year"])
    return summary, sessions, fills, exits, yearly


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
                    if col == "profit_factor":
                        klass = "pos" if num >= 1 else "neg"
                    else:
                        klass = "pos" if num > 0 else "neg" if num < 0 else ""
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


def write_html(summary: pd.DataFrame, sessions: pd.DataFrame, fills: pd.DataFrame, exits: pd.DataFrame, yearly: pd.DataFrame):
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f6f7f9;color:#17202a}
    header{padding:30px 42px;background:#101820;color:white}h1{margin:0 0 8px;font-size:26px}header p{margin:0;color:#c9d3df}
    main{padding:24px 42px 48px;max-width:1900px;margin:0 auto}section{background:white;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{margin:0 0 10px;font-size:18px}.table-wrap{overflow-x:auto;border:1px solid #d9dee7;border-radius:8px}
    table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}
    th{background:#eef2f7}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2),td:nth-child(3),th:nth-child(3){text-align:left}
    """
    html = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Strategy 2 Third Fill Recovery Rules</title><style>{css}</style></head>
<body><header><h1>Strategy 2: Third Fill Recovery Rules</h1><p>R1 avg full exit, R2 avg+3P 70% reduce, R3 avg 70% reduce. Non-third-fill trades use avg+5P then 5P close trail.</p></header><main>
{table_html(summary.sort_values("expectancy_10p", ascending=False), "Config Ranking")}
{table_html(sessions.sort_values("expectancy_10p", ascending=False), "Session Breakdown", 100)}
{table_html(fills.sort_values(["recovery_rule", "tf", "direction", "pending_bars", "filled_entries"]), "Filled Entries Breakdown")}
{table_html(exits.sort_values(["recovery_rule", "tf", "direction", "pending_bars", "exit_reason"]), "Exit Breakdown")}
{table_html(yearly.sort_values(["recovery_rule", "tf", "direction", "pending_bars", "year"]), "Yearly Breakdown")}
</main></body></html>"""
    (OUTPUT_DIR / "strategy2_grid_third_fill_recovery_rules_report.html").write_text(html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for tf in TFS:
        print("LOAD", tf)
        df = base.detect_breakouts(base.load_tf(tf))
        data = {
            "idx": df.index,
            "high": df["high"].to_numpy(dtype=float),
            "low": df["low"].to_numpy(dtype=float),
            "close": df["close"].to_numpy(dtype=float),
        }
        for pending in PENDING_WINDOWS:
            entries = base.find_limit_entries(df, tf, pending)
            print("entries", tf, pending, len(entries))
            for rule in RECOVERY_RULES:
                print("rule", rule)
                for _, entry in entries.iterrows():
                    sim = simulate_recovery_rule(data, entry, rule)
                    if not sim:
                        continue
                    out = entry.to_dict()
                    out.update(sim)
                    out.update({
                        "grid_step": GRID_STEP,
                        "max_entries": MAX_ENTRIES,
                        "stop_from_entry1": STOP_FROM_ENTRY1,
                        "regular_trail_arm": REGULAR_TRAIL_ARM,
                        "trail_points": TRAIL_POINTS,
                        "cost_per_unit": COST_PER_UNIT,
                    })
                    all_rows.append(out)

    trades = pd.DataFrame(all_rows)
    summary, sessions, fills, exits, yearly = build_reports(trades)
    trades.to_csv(OUTPUT_DIR / "strategy2_recovery_rule_trades.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "strategy2_recovery_rule_summary.csv", index=False, encoding="utf-8-sig")
    sessions.to_csv(OUTPUT_DIR / "strategy2_recovery_rule_by_session.csv", index=False, encoding="utf-8-sig")
    fills.to_csv(OUTPUT_DIR / "strategy2_recovery_rule_by_fills.csv", index=False, encoding="utf-8-sig")
    exits.to_csv(OUTPUT_DIR / "strategy2_recovery_rule_by_exit.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "strategy2_recovery_rule_by_year.csv", index=False, encoding="utf-8-sig")
    write_html(summary, sessions, fills, exits, yearly)

    print("")
    print("=== STRATEGY 2 THIRD FILL RECOVERY RULES ===")
    print("Trades:", len(trades))
    cols = ["recovery_rule", "tf", "direction", "pending_bars", "trades", "win_rate", "expectancy_10p", "profit_factor", "max_drawdown_points", "cumulative_points", "avg_filled_entries", "stop_rate", "recovery_reduce_rate"]
    print(summary.sort_values("expectancy_10p", ascending=False)[cols].to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
