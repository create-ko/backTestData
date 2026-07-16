# -*- coding: utf-8 -*-
"""Search scheduled three-session entries with volatility-scaled fixed 2R exits."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "three_session_atr_rr2"
TARGET_SESSIONS = {"asia", "europe", "us_open"}
COST = 0.5


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


base115 = load_module("base115_for_147", SCRIPT_DIR / "115_2m_session_liquidity_rr2_sweep.py")
metrics = load_module("metrics144_for_147", SCRIPT_DIR / "144_bb20_rr2_daily2_validation.py")


def load_data() -> pd.DataFrame:
    base115.TEST_START = "2010-01-01"
    base115.TEST_END = "2026-06-17"
    return base115.load_data()


def make_entries(df: pd.DataFrame, direction_rule: str, volatility_mult: float, risk_floor: float) -> pd.DataFrame:
    idx = df.index
    open_ = df["open"].to_numpy(float)
    close = df["close"].to_numpy(float)
    median_range = df["range_median20"].to_numpy(float)
    sma120 = df["sma120"].to_numpy(float)
    session_id = df["session_id"].to_numpy(int)
    session_name = df["session_name"].astype(str).to_numpy()
    kst_date = df["kst_date"].astype(str).to_numpy()
    starts = np.flatnonzero(np.r_[True, session_id[1:] != session_id[:-1]])
    seen = set()
    rows = []
    for start in starts:
        session = session_name[start]
        key = (kst_date[start], session)
        if session not in TARGET_SESSIONS or key in seen:
            continue
        seen.add(key)
        pos = start + 1
        if pos >= len(df) or session_id[pos] != session_id[start]:
            continue
        vol = median_range[start]
        if not math.isfinite(vol) or vol <= 0:
            continue
        if direction_rule == "long":
            direction = "long"
        elif direction_rule == "short":
            direction = "short"
        elif direction_rule == "sma120":
            if not math.isfinite(sma120[start]):
                continue
            direction = "long" if close[start] >= sma120[start] else "short"
        else:
            raise ValueError("Unknown direction rule")
        risk = max(risk_floor, float(vol * volatility_mult))
        entry_price = float(open_[pos])
        stop = entry_price - risk if direction == "long" else entry_price + risk
        target = entry_price + 2.0 * risk if direction == "long" else entry_price - 2.0 * risk
        rows.append({
            "entry_pos": pos,
            "entry_time": idx[pos],
            "entry_price": entry_price,
            "direction": direction,
            "risk_points": risk,
            "stop_price": stop,
            "target_price": target,
            "session_id": int(session_id[pos]),
            "session": session,
            "day": kst_date[pos],
            "year": int(idx[pos].year),
            "month": idx[pos].strftime("%Y-%m"),
        })
    return pd.DataFrame(rows)


def apply_concurrency_cap(trades: pd.DataFrame, cap: int = 5) -> pd.DataFrame:
    open_exits = []
    kept = []
    for idx, row in trades.sort_values("entry_time").iterrows():
        open_exits = [exit_time for exit_time in open_exits if exit_time > row["entry_time"]]
        if len(open_exits) >= cap:
            continue
        kept.append(idx)
        open_exits.append(row["exit_time"])
    return trades.loc[kept].sort_values("entry_time").reset_index(drop=True)


def simulate(df: pd.DataFrame, entries: pd.DataFrame, max_hold_bars: int, concurrency_cap: int = 5) -> pd.DataFrame:
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    rows = []
    for row in entries.itertuples(index=False):
        pos = int(row.entry_pos)
        end = min(len(df) - 1, pos + max_hold_bars)
        exit_pos, exit_price, reason = end, float(close[end]), "time_exit"
        for p in range(pos, end + 1):
            if row.direction == "long":
                if low[p] <= row.stop_price:
                    exit_pos, exit_price, reason = p, row.stop_price, "stop"
                    break
                if high[p] >= row.target_price:
                    exit_pos, exit_price, reason = p, row.target_price, "target_2r"
                    break
            else:
                if high[p] >= row.stop_price:
                    exit_pos, exit_price, reason = p, row.stop_price, "stop"
                    break
                if low[p] <= row.target_price:
                    exit_pos, exit_price, reason = p, row.target_price, "target_2r"
                    break
        gross = exit_price - row.entry_price if row.direction == "long" else row.entry_price - exit_price
        rows.append({
            **row._asdict(),
            "exit_time": idx[exit_pos],
            "gross_points": gross,
            "net_points": gross - COST,
            "r_net": (gross - COST) / row.risk_points,
            "exit_reason": reason,
            "hold_bars": exit_pos - pos + 1,
        })
    trades = pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)
    return apply_concurrency_cap(trades, concurrency_cap) if concurrency_cap > 0 else trades


def evaluate_selection(trades: pd.DataFrame) -> dict:
    pnl = trades["net_points"]
    monthly = trades.groupby("month")["net_points"].sum()
    return {
        "trades": len(trades),
        "active_days": trades["day"].nunique(),
        "trades_per_day": len(trades) / 142,
        "net_points": pnl.sum(),
        "profit_factor": metrics.profit_factor(pnl),
        "max_drawdown": metrics.max_drawdown(pnl),
        "win_rate": (pnl > 0).mean() * 100,
        "positive_month_rate": (monthly > 0).mean() * 100,
    }


def main() -> None:
    df = load_data()
    sample_df = df[(df.index >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")) & (df.index < pd.Timestamp("2026-06-17", tz="Asia/Seoul"))].copy()
    rows = []
    best = None
    for rule in ["long", "short", "sma120"]:
        for mult in [2.0, 4.0, 6.0, 10.0, 15.0]:
            for floor in [0.8, 1.5, 2.0]:
                entries = make_entries(sample_df, rule, mult, floor)
                for hold in [120, 240, 480]:
                    trades = simulate(sample_df, entries, hold)
                    row = {"direction_rule": rule, "volatility_mult": mult, "risk_floor": floor, "max_hold_bars": hold}
                    row.update(evaluate_selection(trades))
                    row["frequency_pass"] = 2.0 <= row["trades_per_day"] <= 3.0
                    row["score"] = row["net_points"] - 0.2 * row["max_drawdown"] + 2.0 * row["positive_month_rate"]
                    rows.append(row)
                    if row["frequency_pass"] and row["net_points"] > 0 and row["profit_factor"] > 1.0:
                        if best is None or (row["positive_month_rate"], row["score"]) > (best["positive_month_rate"], best["score"]):
                            best = row.copy()

    sweep = pd.DataFrame(rows).sort_values(["frequency_pass", "score"], ascending=[False, False])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        (OUTPUT / "REPORT.md").write_text("# Three-Session Volatility RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8")
        print(sweep.head(30).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    entries = make_entries(df, str(best["direction_rule"]), float(best["volatility_mult"]), float(best["risk_floor"]))
    raw = simulate(df, entries, int(best["max_hold_bars"]))
    metrics.audit_orders(raw)
    sample = metrics.select_period(raw, "2026-01-01", "2026-06-17")
    full = metrics.select_period(raw, "2010-01-01", "2026-06-17")
    result_rows = [metrics.summarize("selection_2026", "2026-01-01", "2026-06-17", 142, sample)]
    for start, end, days in metrics.SLICES:
        result_rows.append(metrics.summarize("3y_chunk", start, end, days, metrics.select_period(raw, start, end)))
    result_rows.append(metrics.summarize("full", "2010-01-01", "2026-06-17", 5125, full))
    result = pd.DataFrame(result_rows)
    result.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")
    full_pass = bool(result.loc[result["period"] == "full", "passed"].iloc[0])
    final = "PASSED" if full_pass else "REJECTED"
    report = [
        "# Three-Session Volatility-Scaled RR2",
        "",
        "- One scheduled entry at each Asia, Europe, and US-open session",
        "- Direction selected on 2026: long, short, or prior 120-SMA state",
        "- Stop distance: prior median 2-minute range times a fixed multiplier with a fixed floor",
        "- Target: exactly 2R; cost: 0.5 points; same-bar ambiguity: stop-first",
        "",
        "Selected config: `" + ", ".join(f"{k}={best[k]}" for k in ["direction_rule", "volatility_mult", "risk_floor", "max_hold_bars"]) + "`",
        "",
        f"Final decision: **{final}**.",
        "",
        metrics.markdown_table(result),
        "",
        "No parameter is re-selected in historical slices.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
