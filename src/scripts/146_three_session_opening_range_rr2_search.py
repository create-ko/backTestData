# -*- coding: utf-8 -*-
"""Search and validate a three-session opening-range strategy at fixed 2R."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "three_session_opening_range_rr2"
ROUND_TRIP_COST = 0.5
TARGET_SESSIONS = {"asia", "europe", "us_open"}
SELECTION_START = pd.Timestamp("2026-01-01", tz="Asia/Seoul")
END = pd.Timestamp("2026-06-17", tz="Asia/Seoul")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


base115 = load_module("base115_for_146", SCRIPT_DIR / "115_2m_session_liquidity_rr2_sweep.py")
metrics = load_module("metrics144_for_146", SCRIPT_DIR / "144_bb20_rr2_daily2_validation.py")


def load_data() -> pd.DataFrame:
    base115.TEST_START = "2010-01-01"
    base115.TEST_END = "2026-06-17"
    return base115.load_data()


def find_entries(df: pd.DataFrame, opening_bars: int, direction_mode: str) -> pd.DataFrame:
    idx = df.index
    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    session_id = df["session_id"].to_numpy(int)
    session_name = df["session_name"].astype(str).to_numpy()
    kst_date = df["kst_date"].astype(str).to_numpy()
    starts = np.flatnonzero(np.r_[True, session_id[1:] != session_id[:-1]])
    rows = []
    seen_day_sessions = set()
    for start in starts:
        session = session_name[start]
        if session not in TARGET_SESSIONS:
            continue
        day_session = (kst_date[start], session)
        if day_session in seen_day_sessions:
            continue
        seen_day_sessions.add(day_session)
        entry_pos = start + opening_bars
        if entry_pos >= len(df) or session_id[entry_pos] != session_id[start]:
            continue
        opening_end = entry_pos - 1
        change = close[opening_end] - open_[start]
        if change == 0:
            continue
        direction = "long" if change > 0 else "short"
        if direction_mode == "reversal":
            direction = "short" if direction == "long" else "long"
        rows.append({
            "entry_pos": entry_pos,
            "entry_time": idx[entry_pos],
            "entry_price": open_[entry_pos],
            "direction": direction,
            "opening_high": float(high[start:entry_pos].max()),
            "opening_low": float(low[start:entry_pos].min()),
            "session_id": int(session_id[entry_pos]),
            "session": session,
            "day": kst_date[entry_pos],
            "year": int(idx[entry_pos].year),
            "month": idx[entry_pos].strftime("%Y-%m"),
        })
    return pd.DataFrame(rows)


def simulate(
    df: pd.DataFrame,
    entries: pd.DataFrame,
    stop_buffer: float,
    min_risk: float,
    max_risk: float,
    max_hold_bars: int,
) -> pd.DataFrame:
    idx = df.index
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    session_id = df["session_id"].to_numpy(int)
    rows = []
    for row in entries.itertuples(index=False):
        pos = int(row.entry_pos)
        if row.direction == "long":
            stop = float(row.opening_low - stop_buffer)
            risk = float(row.entry_price - stop)
            target = float(row.entry_price + 2.0 * risk)
        else:
            stop = float(row.opening_high + stop_buffer)
            risk = float(stop - row.entry_price)
            target = float(row.entry_price - 2.0 * risk)
        if not math.isfinite(risk) or risk < min_risk or risk > max_risk:
            continue
        end = min(len(df) - 1, pos + max_hold_bars)
        while end > pos and session_id[end] != session_id[pos]:
            end -= 1
        exit_pos = end
        exit_price = float(close[end])
        reason = "time_exit"
        for p in range(pos, end + 1):
            if row.direction == "long":
                if low[p] <= stop:
                    exit_pos, exit_price, reason = p, stop, "stop"
                    break
                if high[p] >= target:
                    exit_pos, exit_price, reason = p, target, "target_2r"
                    break
            else:
                if high[p] >= stop:
                    exit_pos, exit_price, reason = p, stop, "stop"
                    break
                if low[p] <= target:
                    exit_pos, exit_price, reason = p, target, "target_2r"
                    break
        gross = exit_price - row.entry_price if row.direction == "long" else row.entry_price - exit_price
        rows.append({
            **row._asdict(),
            "exit_time": idx[exit_pos],
            "stop_price": stop,
            "target_price": target,
            "risk_points": risk,
            "gross_points": gross,
            "net_points": gross - ROUND_TRIP_COST,
            "r_net": (gross - ROUND_TRIP_COST) / risk,
            "exit_reason": reason,
            "hold_bars": exit_pos - pos + 1,
        })
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def selection_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0, "trades_per_day": 0.0, "net_points": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0, "positive_month_rate": 0.0}
    trades = trades.sort_values("entry_time").groupby("day", sort=False).head(3)
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
    sample_df = df[(df.index >= SELECTION_START) & (df.index < END)].copy()
    rows = []
    cached_entries = {}
    best = None
    for opening_bars in [3, 5, 10, 15]:
        for direction_mode in ["momentum", "reversal"]:
            entries = find_entries(sample_df, opening_bars, direction_mode)
            cached_entries[(opening_bars, direction_mode)] = entries
            for stop_buffer in [0.2, 0.5]:
                for min_risk in [0.8, 1.5]:
                    for max_risk in [12.0, 25.0, 50.0]:
                        for max_hold_bars in [30, 60, 120]:
                            trades = simulate(sample_df, entries, stop_buffer, min_risk, max_risk, max_hold_bars)
                            row = {
                                "opening_bars": opening_bars,
                                "direction_mode": direction_mode,
                                "stop_buffer": stop_buffer,
                                "min_risk": min_risk,
                                "max_risk": max_risk,
                                "max_hold_bars": max_hold_bars,
                            }
                            row.update(selection_metrics(trades))
                            row["frequency_pass"] = 2.0 <= row["trades_per_day"] <= 3.0
                            row["score"] = row["net_points"] - 0.20 * row["max_drawdown"] + 2.0 * row["positive_month_rate"]
                            rows.append(row)
                            if row["frequency_pass"] and row["net_points"] > 0 and row["profit_factor"] > 1.0:
                                if best is None or (row["positive_month_rate"], row["score"]) > (best["positive_month_rate"], best["score"]):
                                    best = row.copy()

    sweep = pd.DataFrame(rows).sort_values(["frequency_pass", "score"], ascending=[False, False])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        (OUTPUT / "REPORT.md").write_text("# Three-Session Opening Range RR2\n\nNo 2026 config passed frequency and performance gates.\n", encoding="utf-8")
        print(sweep.head(30).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    full_entries = find_entries(df, int(best["opening_bars"]), str(best["direction_mode"]))
    full_raw = simulate(
        df,
        full_entries,
        float(best["stop_buffer"]),
        float(best["min_risk"]),
        float(best["max_risk"]),
        int(best["max_hold_bars"]),
    )
    metrics.audit_orders(full_raw)
    sample = metrics.select_period(full_raw, "2026-01-01", "2026-06-17")
    full = metrics.select_period(full_raw, "2010-01-01", "2026-06-17")
    validation_rows = [metrics.summarize("selection_2026", "2026-01-01", "2026-06-17", 142, sample)]
    for start, end, days in metrics.SLICES:
        validation_rows.append(metrics.summarize("3y_chunk", start, end, days, metrics.select_period(full_raw, start, end)))
    validation_rows.append(metrics.summarize("full", "2010-01-01", "2026-06-17", 5125, full))
    validation = pd.DataFrame(validation_rows)
    validation.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(sample, "month").round(4).to_csv(OUTPUT / "selection_2026_monthly.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig")

    full_pass = bool(validation.loc[validation["period"] == "full", "passed"].iloc[0])
    final = "PASSED" if full_pass else "REJECTED"
    report = [
        "# Three-Session Opening Range RR2",
        "",
        "- Sessions: Asia, Europe, US open; at most one entry per session",
        "- Signal: opening-range momentum or reversal selected only on 2026",
        "- Stop: opposite opening-range extreme plus buffer; target: fixed 2R",
        "- Cost: 0.5 points round trip; same-bar ambiguity resolved stop-first",
        "",
        "Selected config: `" + ", ".join(f"{k}={best[k]}" for k in ["opening_bars", "direction_mode", "stop_buffer", "min_risk", "max_risk", "max_hold_bars"]) + "`",
        "",
        f"Final decision: **{final}**.",
        "",
        metrics.markdown_table(validation),
        "",
        "No parameter is re-selected in historical slices.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(validation.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
