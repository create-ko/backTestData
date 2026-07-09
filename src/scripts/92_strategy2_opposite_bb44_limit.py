# -*- coding: utf-8 -*-
"""Strategy 2: double-BB breakout candle opposite 4/4 band limit entry.

Rules tested:
- TF: 5m, 10m.
- Long breakout: close > BB20/2 upper(close) and close > BB4/4 upper(open).
- Short breakout: close < BB20/2 lower(close) and close < BB4/4 lower(open).
- Long limit price: breakout candle's BB4/4 lower(open).
- Short limit price: breakout candle's BB4/4 upper(open).
- Entry must occur KST 08:30 <= time < 23:30.
- Cost: 0.5 point round turn per trade.
- Single-entry first pass, no time exit after filled.
- Profit exit: close recovers 5P beyond entry, then 5P close-based trailing.
- Stop variants: 15P, 20P, 25P from entry.
- Pending order windows: 3, 6, 10 bars after breakout.
"""
from __future__ import annotations

import contextlib
import io
import math
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gold_data_prep as prep  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "result" / "strategy2_opposite_bb44_limit_cost05_entry0830_2330"

TFS = ["5m", "10m"]
PENDING_WINDOWS = [3, 6, 10]
STOP_POINTS = [15.0, 20.0, 25.0]
TRAIL_TRIGGER_POINTS = 5.0
TRAIL_POINTS = 5.0
COST_POINTS = 0.50
ENTRY_START_MINUTE = 8 * 60 + 30
ENTRY_END_MINUTE = 23 * 60 + 30


def _quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def load_tf(tf: str) -> pd.DataFrame:
    path = DATA_DIR / ("xauusd_%s_2010-01-01_2026-06-16.csv" % tf)
    df = _quiet_call(prep.load_gold_data, path, timeframe=tf)
    df = prep.assign_session(df)
    df = prep.add_bollinger_bands(df)
    return df


def entry_time_allowed(ts: pd.Timestamp) -> bool:
    kst = ts.tz_convert("Asia/Seoul") if ts.tzinfo is not None else ts.tz_localize("Asia/Seoul")
    minutes = kst.hour * 60 + kst.minute
    return ENTRY_START_MINUTE <= minutes < ENTRY_END_MINUTE


def detect_breakouts(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["long_breakout"] = (
        (out["close"] > out["bb20_2_upper_close"])
        & (out["close"] > out["bb4_4_upper_open"])
    ).fillna(False)
    out["short_breakout"] = (
        (out["close"] < out["bb20_2_lower_close"])
        & (out["close"] < out["bb4_4_lower_open"])
    ).fillna(False)
    return out


def find_limit_entries(df: pd.DataFrame, tf: str, pending_bars: int) -> pd.DataFrame:
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

    for bi in range(len(df) - 2):
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

        end = min(len(df) - 1, bi + pending_bars)
        entry_pos = None
        for pos in range(bi + 1, end + 1):
            hit = low[pos] <= limit_price if direction == "long" else high[pos] >= limit_price
            if hit:
                if not entry_time_allowed(idx[pos]):
                    entry_pos = None
                else:
                    entry_pos = pos
                break
        if entry_pos is None:
            continue

        candle_range = high[bi] - low[bi]
        close_position = math.nan
        if candle_range > 0:
            if direction == "long":
                close_position = (close[bi] - low[bi]) / candle_range
            else:
                close_position = (high[bi] - close[bi]) / candle_range

        rows.append({
            "tf": tf,
            "direction": direction,
            "pending_bars": pending_bars,
            "breakout_pos": bi,
            "entry_pos": entry_pos,
            "breakout_time": idx[bi],
            "entry_time": idx[entry_pos],
            "entry_price": limit_price,
            "breakout_close": close[bi],
            "breakout_range": candle_range,
            "breakout_close_position": close_position,
            "session": sessions[entry_pos],
            "year": idx[entry_pos].year,
            "bars_to_fill": entry_pos - bi,
            "bb44_opposite_price": limit_price,
        })
    return pd.DataFrame(rows)


def simulate_trade(data: dict, row: pd.Series, stop_points: float) -> dict:
    direction = row["direction"]
    entry_pos = int(row["entry_pos"])
    entry = float(row["entry_price"])
    idx = data["idx"]
    high = data["high"]
    low = data["low"]
    close = data["close"]
    stop = entry - stop_points if direction == "long" else entry + stop_points
    trailing_armed = False
    trail_stop = math.nan
    mfe = 0.0
    mae = 0.0
    exit_reason = "open_at_data_end"
    exit_price = float(close[-1])
    exit_time = idx[-1]

    for pos in range(entry_pos, len(idx)):
        hi = float(high[pos])
        lo = float(low[pos])
        cl = float(close[pos])
        t = idx[pos]

        if direction == "long":
            mfe = max(mfe, hi - entry)
            mae = max(mae, entry - lo)
            if lo <= stop:
                exit_reason = "stop"
                exit_price = stop
                exit_time = t
                break
            if trailing_armed and lo <= trail_stop:
                exit_reason = "close_trail_5p"
                exit_price = trail_stop
                exit_time = t
                break
            if cl >= entry + TRAIL_TRIGGER_POINTS:
                next_trail = cl - TRAIL_POINTS
                trail_stop = max(entry, next_trail) if not trailing_armed else max(trail_stop, entry, next_trail)
                trailing_armed = True
        else:
            mfe = max(mfe, entry - lo)
            mae = max(mae, hi - entry)
            if hi >= stop:
                exit_reason = "stop"
                exit_price = stop
                exit_time = t
                break
            if trailing_armed and hi >= trail_stop:
                exit_reason = "close_trail_5p"
                exit_price = trail_stop
                exit_time = t
                break
            if cl <= entry - TRAIL_TRIGGER_POINTS:
                next_trail = cl + TRAIL_POINTS
                trail_stop = min(entry, next_trail) if not trailing_armed else min(trail_stop, entry, next_trail)
                trailing_armed = True

    gross = (exit_price - entry) if direction == "long" else (entry - exit_price)
    net = gross - COST_POINTS
    return {
        "stop_points": stop_points,
        "stop_price": stop,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_points": gross,
        "net_points": net,
        "net_10p": net / 10.0,
        "mfe_points": mfe,
        "mae_points": mae,
        "mfe_10p": mfe / 10.0,
        "mae_10p": mae / 10.0,
        "trailing_armed": trailing_armed,
        "hold_bars": int(idx.searchsorted(exit_time) - int(row["entry_pos"]) + 1),
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
    if group.empty:
        return {}
    pnl = group["net_points"].astype(float)
    return {
        "trades": int(len(group)),
        "win_rate": float((pnl > 0).mean()),
        "expectancy_points": float(pnl.mean()),
        "expectancy_10p": float(group["net_10p"].mean()),
        "profit_factor": profit_factor(pnl),
        "max_drawdown_points": max_drawdown(pnl),
        "cumulative_points": float(pnl.sum()),
        "stop_rate": float((group["exit_reason"] == "stop").mean()),
        "trail_rate": float((group["exit_reason"] == "close_trail_5p").mean()),
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
    configs = []
    yearly = []
    sessions = []
    exits = []
    for key, group in trades.groupby(["tf", "direction", "pending_bars", "stop_points"], sort=True):
        row = {"tf": key[0], "direction": key[1], "pending_bars": int(key[2]), "stop_points": float(key[3])}
        row.update(summarize_group(group))
        configs.append(row)
    for key, group in trades.groupby(["tf", "direction", "pending_bars", "stop_points", "year"], sort=True):
        row = {"tf": key[0], "direction": key[1], "pending_bars": int(key[2]), "stop_points": float(key[3]), "year": int(key[4])}
        row.update(summarize_group(group))
        yearly.append(row)
    for key, group in trades.groupby(["tf", "direction", "pending_bars", "stop_points", "session"], sort=True):
        row = {"tf": key[0], "direction": key[1], "pending_bars": int(key[2]), "stop_points": float(key[3]), "session": key[4]}
        row.update(summarize_group(group))
        sessions.append(row)
    for key, group in trades.groupby(["tf", "direction", "pending_bars", "stop_points", "exit_reason"], sort=True):
        row = {"tf": key[0], "direction": key[1], "pending_bars": int(key[2]), "stop_points": float(key[3]), "exit_reason": key[4]}
        row.update(summarize_group(group))
        exits.append(row)
    return tuple(round_report(pd.DataFrame(x)) for x in (configs, yearly, sessions, exits))


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join(f"<th>{c}</th>" for c in show.columns)
    rows = []
    for _, row in show.iterrows():
        cells = []
        for col, val in row.items():
            cls = ""
            if col in {"expectancy_10p", "expectancy_points", "cumulative_points", "profit_factor"}:
                try:
                    num = float(val)
                    cls = "pos" if (num >= 1 if col == "profit_factor" else num > 0) else "neg"
                except Exception:
                    pass
            if pd.isna(val):
                text = ""
            elif isinstance(val, float):
                text = f"{val:,.3f}" if col != "win_rate" and not col.endswith("_rate") else f"{val*100:.1f}%"
            else:
                text = str(val)
            cells.append(f"<td class='{cls}'>{text}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<section><h2>{title}</h2><div class='table-wrap'><table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"


def write_html(summary: pd.DataFrame, yearly: pd.DataFrame, sessions: pd.DataFrame, exits: pd.DataFrame):
    top = summary.sort_values("expectancy_10p", ascending=False)
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f6f7f9;color:#17202a}
    header{padding:30px 42px;background:#101820;color:white} h1{margin:0 0 8px;font-size:26px} header p{margin:0;color:#c9d3df}
    main{padding:24px 42px 48px;max-width:1800px;margin:0 auto} section{background:white;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}
    h2{margin:0 0 10px;font-size:18px}.table-wrap{overflow-x:auto;border:1px solid #d9dee7;border-radius:8px}
    table{width:100%;border-collapse:collapse;font-size:13px} th,td{padding:7px 9px;border-bottom:1px solid #d9dee7;text-align:right;white-space:nowrap}
    th{background:#eef2f7}td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.pos{color:#087f5b;font-weight:700;background:#e6f4ee}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    html = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Strategy 2 Opposite BB4/4 Limit</title><style>{css}</style></head>
<body><header><h1>Strategy 2: Breakout Candle Opposite BB4/4 Limit</h1><p>Cost 0.5P, KST entry 08:30-23:30, single-entry first pass, no time exit after filled</p></header><main>
{table_html(top, "Config Ranking")}
{table_html(sessions.sort_values("expectancy_10p", ascending=False), "Session Breakdown", 80)}
{table_html(yearly.sort_values(["tf", "direction", "pending_bars", "stop_points", "year"]), "Yearly Breakdown")}
{table_html(exits, "Exit Reason Breakdown")}
</main></body></html>"""
    (OUTPUT_DIR / "strategy2_opposite_bb44_limit_report.html").write_text(html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_trades = []
    for tf in TFS:
        print("LOAD", tf)
        df = detect_breakouts(load_tf(tf))
        data = {
            "idx": df.index,
            "high": df["high"].to_numpy(dtype=float),
            "low": df["low"].to_numpy(dtype=float),
            "close": df["close"].to_numpy(dtype=float),
        }
        for pending in PENDING_WINDOWS:
            entries = find_limit_entries(df, tf, pending)
            print("entries", tf, pending, len(entries))
            for _, entry in entries.iterrows():
                for stop in STOP_POINTS:
                    row = entry.to_dict()
                    row.update(simulate_trade(data, entry, stop))
                    all_trades.append(row)
    trades = pd.DataFrame(all_trades)
    summary, yearly, sessions, exits = summarize(trades)
    trades.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_limit_trades.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_limit_summary.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_limit_by_year.csv", index=False, encoding="utf-8-sig")
    sessions.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_limit_by_session.csv", index=False, encoding="utf-8-sig")
    exits.to_csv(OUTPUT_DIR / "strategy2_opposite_bb44_limit_by_exit.csv", index=False, encoding="utf-8-sig")
    write_html(summary, yearly, sessions, exits)
    print("")
    print("=== STRATEGY 2 OPPOSITE BB4/4 LIMIT ===")
    print("Trades:", len(trades))
    cols = ["tf", "direction", "pending_bars", "stop_points", "trades", "win_rate", "expectancy_10p", "profit_factor", "max_drawdown_points", "cumulative_points", "stop_rate", "trail_rate"]
    print(summary.sort_values("expectancy_10p", ascending=False)[cols].to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
