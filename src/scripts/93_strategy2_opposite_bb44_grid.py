# -*- coding: utf-8 -*-
"""Strategy 2 grid variant: opposite BB4/4 limit with 3 entries.

Rules:
- Uses Strategy 2 signal/limit definition.
- Long entry 1: breakout candle's bb4_4_lower_open.
- Short entry 1: breakout candle's bb4_4_upper_open.
- Entry 2/3: every 10P adverse, total 3 entries.
- Stop: 35P adverse from Entry 1.
- Profit exit: after close reaches avg entry +5P, update 5P close-based
  trailing stop. Newly updated trailing stop is active from next bar.
- Cost: 0.5P round turn per filled unit.
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
OUTPUT_DIR = ROOT / "result" / "strategy2_opposite_bb44_grid3_10p_stop35_arm5_trail5_cost05"

spec = importlib.util.spec_from_file_location("strategy2_base", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
sys.modules["strategy2_base"] = base
assert spec.loader is not None
spec.loader.exec_module(base)

TFS = ["5m", "10m"]
PENDING_WINDOWS = [3, 6, 10]
GRID_STEP = 10.0
MAX_ENTRIES = 3
STOP_FROM_ENTRY1 = 35.0
TRAIL_ARM_PROFIT = 5.0
TRAIL_POINTS = 5.0
COST_PER_UNIT = 0.50


def grid_levels(entry1: float, direction: str) -> list[float]:
    if direction == "long":
        return [entry1 - i * GRID_STEP for i in range(MAX_ENTRIES)]
    return [entry1 + i * GRID_STEP for i in range(MAX_ENTRIES)]


def simulate_grid_trade(data: dict, row: pd.Series) -> dict:
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
    fill_prices = []
    open_units = 0
    avg_entry = math.nan
    trailing_armed = False
    trail_stop = math.nan
    max_favorable = 0.0
    max_adverse = 0.0
    exit_reason = "open_at_data_end"
    exit_price = float(close[-1])
    exit_time = idx[-1]

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
                open_units += 1
                avg_entry = sum(fill_prices) / len(fill_prices)

        if open_units <= 0:
            continue

        if direction == "long":
            max_favorable = max(max_favorable, hi - avg_entry)
            max_adverse = max(max_adverse, avg_entry - lo)

            if lo <= stop:
                exit_reason = "stop_35p"
                exit_price = stop
                exit_time = t
                break

            if trailing_armed and lo <= trail_stop:
                exit_reason = "close_trail_5p"
                exit_price = trail_stop
                exit_time = t
                break

            if cl >= avg_entry + TRAIL_ARM_PROFIT:
                next_trail = cl - TRAIL_POINTS
                if not trailing_armed:
                    trailing_armed = True
                    trail_stop = max(avg_entry, next_trail)
                else:
                    trail_stop = max(trail_stop, avg_entry, next_trail)
        else:
            max_favorable = max(max_favorable, avg_entry - lo)
            max_adverse = max(max_adverse, hi - avg_entry)

            if hi >= stop:
                exit_reason = "stop_35p"
                exit_price = stop
                exit_time = t
                break

            if trailing_armed and hi >= trail_stop:
                exit_reason = "close_trail_5p"
                exit_price = trail_stop
                exit_time = t
                break

            if cl <= avg_entry - TRAIL_ARM_PROFIT:
                next_trail = cl + TRAIL_POINTS
                if not trailing_armed:
                    trailing_armed = True
                    trail_stop = min(avg_entry, next_trail)
                else:
                    trail_stop = min(trail_stop, avg_entry, next_trail)

    if open_units <= 0 or pd.isna(avg_entry):
        return {}

    gross_per_unit = exit_price - avg_entry if direction == "long" else avg_entry - exit_price
    gross_total = gross_per_unit * open_units
    cost_total = COST_PER_UNIT * open_units
    net_total = gross_total - cost_total

    return {
        "entry_1_price": levels[0],
        "entry_2_price": levels[1],
        "entry_3_price": levels[2],
        "entry_1_time": fill_times[0],
        "entry_2_time": fill_times[1],
        "entry_3_time": fill_times[2],
        "filled_entries": int(open_units),
        "avg_entry": avg_entry,
        "stop_price": stop,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_points_total": gross_total,
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
        "trail_rate": float((exits == "close_trail_5p").mean()),
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


def summarize(trades: pd.DataFrame):
    summary = []
    yearly = []
    sessions = []
    fills = []
    exits = []

    for key, group in trades.groupby(["tf", "direction", "pending_bars"], sort=True):
        row = {"tf": key[0], "direction": key[1], "pending_bars": int(key[2])}
        row.update(summarize_group(group))
        summary.append(row)
    for key, group in trades.groupby(["tf", "direction", "pending_bars", "year"], sort=True):
        row = {"tf": key[0], "direction": key[1], "pending_bars": int(key[2]), "year": int(key[3])}
        row.update(summarize_group(group))
        yearly.append(row)
    for key, group in trades.groupby(["tf", "direction", "pending_bars", "session"], sort=True):
        row = {"tf": key[0], "direction": key[1], "pending_bars": int(key[2]), "session": key[3]}
        row.update(summarize_group(group))
        sessions.append(row)
    for key, group in trades.groupby(["tf", "direction", "pending_bars", "filled_entries"], sort=True):
        row = {"tf": key[0], "direction": key[1], "pending_bars": int(key[2]), "filled_entries": int(key[3])}
        row.update(summarize_group(group))
        fills.append(row)
    for key, group in trades.groupby(["tf", "direction", "pending_bars", "exit_reason"], sort=True):
        row = {"tf": key[0], "direction": key[1], "pending_bars": int(key[2]), "exit_reason": key[3]}
        row.update(summarize_group(group))
        exits.append(row)

    return tuple(round_report(pd.DataFrame(x)) for x in (summary, yearly, sessions, fills, exits))


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


def write_html(summary: pd.DataFrame, yearly: pd.DataFrame, sessions: pd.DataFrame, fills: pd.DataFrame, exits: pd.DataFrame):
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f6f7f9;color:#17202a}
    header{padding:30px 42px;background:#101820;color:white}h1{margin:0 0 8px;font-size:26px}header p{margin:0;color:#c9d3df}
    main{padding:24px 42px 48px;max-width:1800px;margin:0 auto}section{background:white;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{margin:0 0 10px;font-size:18px}.table-wrap{overflow-x:auto;border:1px solid #d9dee7;border-radius:8px}
    table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}
    th{background:#eef2f7}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}
    """
    html = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Strategy 2 Grid</title><style>{css}</style></head>
<body><header><h1>Strategy 2 Grid: Opposite BB4/4 Limit</h1><p>3 entries every 10P, stop 35P from Entry1, avg entry +5P then 5P close trail, cost 0.5P per filled unit</p></header><main>
{table_html(summary.sort_values("expectancy_10p", ascending=False), "Config Ranking")}
{table_html(sessions.sort_values("expectancy_10p", ascending=False), "Session Breakdown", 80)}
{table_html(fills.sort_values(["tf", "direction", "pending_bars", "filled_entries"]), "Filled Entries Breakdown")}
{table_html(yearly.sort_values(["tf", "direction", "pending_bars", "year"]), "Yearly Breakdown")}
{table_html(exits, "Exit Breakdown")}
</main></body></html>"""
    (OUTPUT_DIR / "strategy2_opposite_bb44_grid_report.html").write_text(html, encoding="utf-8")


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
            for _, entry in entries.iterrows():
                sim = simulate_grid_trade(data, entry)
                if not sim:
                    continue
                row = entry.to_dict()
                row.update(sim)
                row.update({
                    "grid_step": GRID_STEP,
                    "max_entries": MAX_ENTRIES,
                    "stop_from_entry1": STOP_FROM_ENTRY1,
                    "trail_arm_profit": TRAIL_ARM_PROFIT,
                    "trail_points": TRAIL_POINTS,
                    "cost_per_unit": COST_PER_UNIT,
                })
                all_rows.append(row)

    trades = pd.DataFrame(all_rows)
    summary, yearly, sessions, fills, exits = summarize(trades)
    trades.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_grid_trades.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_grid_summary.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_grid_by_year.csv", index=False, encoding="utf-8-sig")
    sessions.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_grid_by_session.csv", index=False, encoding="utf-8-sig")
    fills.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_grid_by_fills.csv", index=False, encoding="utf-8-sig")
    exits.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_grid_by_exit.csv", index=False, encoding="utf-8-sig")
    write_html(summary, yearly, sessions, fills, exits)

    print("")
    print("=== STRATEGY 2 GRID ===")
    print("Trades:", len(trades))
    cols = ["tf", "direction", "pending_bars", "trades", "win_rate", "expectancy_10p", "profit_factor", "max_drawdown_points", "cumulative_points", "avg_filled_entries", "stop_rate", "trail_rate"]
    print(summary.sort_values("expectancy_10p", ascending=False)[cols].to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
