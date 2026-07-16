# -*- coding: utf-8 -*-
"""First completed 15m candle of each session, filtered by daily King regime."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_king_regime_session_first_candle_rr2"
START = "2010-01-01"
SELECTION_START = "2026-01-01"
END = "2026-06-17"
SESSIONS = ["asia", "europe", "us_open"]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


regime_model = load_module(
    "regime169_for_171", SCRIPT_DIR / "169_daily_king_regime_intraday_candle_rr2.py",
)
intraday = regime_model.intraday
daily = regime_model.daily
metrics = intraday.metrics


def completed_daily_tr(index: pd.DatetimeIndex) -> pd.Series:
    frame = daily.daily_frame()
    values = frame["tr"].rolling(40, min_periods=40).mean().shift(1)
    known_index = pd.DatetimeIndex(frame["time"]).tz_convert("Asia/Seoul")
    known = pd.Series(values.to_numpy(float), index=known_index)
    return known.reindex(index, method="ffill")


def session_entries(
    execution: pd.DataFrame,
    bars: pd.DataFrame,
    regime: pd.Series,
    daily_tr: pd.Series,
    session_mode: str,
    body_fraction: float,
    risk_source: str,
    start: str,
    end: str,
) -> pd.DataFrame:
    bar_session = execution["session"].reindex(bars.index).astype(str)
    session_start = bar_session.isin(SESSIONS) & bar_session.ne(bar_session.shift(1))
    if session_mode == "asia_europe":
        session_start &= bar_session.isin(["asia", "europe"])
    elif session_mode == "asia":
        session_start &= bar_session.eq("asia")
    elif session_mode != "all":
        raise ValueError(session_mode)
    candle_range = (bars["high"] - bars["low"]).replace(0.0, np.nan)
    body_ratio = (bars["close"] - bars["open"]).abs() / candle_range
    bullish = (bars["close"] > bars["open"]) & (body_ratio >= body_fraction)
    bearish = (bars["close"] < bars["open"]) & (body_ratio >= body_fraction)
    direction = np.where(
        session_start & (regime == 1) & bullish,
        1,
        np.where(session_start & (regime == -1) & bearish, -1, 0),
    )
    intraday_atr = intraday.true_range(bars).rolling(14, min_periods=14).mean()
    risk_base = intraday_atr if risk_source == "intraday" else daily_tr
    signals = pd.DataFrame({
        "direction": direction, "atr": risk_base, "session": bar_session,
    }, index=bars.index)
    signals = signals[(signals["direction"] != 0) & signals["atr"].notna()]
    start_ts = pd.Timestamp(start, tz="Asia/Seoul")
    end_ts = pd.Timestamp(end, tz="Asia/Seoul")
    signals = signals[(signals.index >= start_ts - pd.Timedelta(minutes=15)) & (signals.index < end_ts)]
    rows = []
    for ts, signal in signals.iterrows():
        entry_time = ts + pd.Timedelta(minutes=15)
        if entry_time < start_ts or entry_time >= end_ts or not 8 <= entry_time.hour <= 23:
            continue
        pos = int(execution.index.searchsorted(entry_time, side="left"))
        if pos >= len(execution) or execution.index[pos] != entry_time:
            continue
        rows.append({
            "entry_pos": pos,
            "entry_time": entry_time,
            "entry_price": float(execution["open"].iloc[pos]),
            "direction": "long" if int(signal["direction"]) == 1 else "short",
            "signal_time": ts,
            "atr": float(signal["atr"]),
            "day": entry_time.date().isoformat(),
            "session": str(signal["session"]),
            "year": int(entry_time.year),
            "month": entry_time.strftime("%Y-%m"),
        })
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame()


def main() -> None:
    df = intraday.prepare()
    bars = intraday.resample_signal_bars(df, "15min")
    daily_positions = regime_model.daily_trades()
    regime = regime_model.completed_regime(bars.index, daily_positions)
    daily_risk = completed_daily_tr(bars.index)
    rows = []
    best = None
    for session_mode in ["all", "asia_europe", "asia"]:
        for body_fraction in [0.0, 0.25, 0.50]:
            for risk_source, risk_multipliers in [
                ("intraday", [1.0, 1.5, 2.0]),
                ("daily", [0.20, 0.30, 0.40]),
            ]:
                entries = session_entries(
                    df, bars, regime, daily_risk, session_mode, body_fraction,
                    risk_source, SELECTION_START, END,
                )
                for risk_mult in risk_multipliers:
                    for hold in [72, 144, 288]:
                        trades = intraday.simulate(df, entries, risk_mult, hold)
                        row = {
                            "session_mode": session_mode, "body_fraction": body_fraction,
                            "risk_source": risk_source, "risk_mult": risk_mult,
                            "max_hold_bars": hold,
                        }
                        row.update(intraday.selection_metrics(trades))
                        row["frequency_pass"] = 1.0 <= row["trades_per_day"] <= 3.0
                        row["score"] = (
                            row["net_points"] - 0.25 * row["max_drawdown"]
                            + 2.0 * row["positive_month_rate"]
                        )
                        rows.append(row)
                        eligible = (
                            row["frequency_pass"] and row["net_points"] > 0
                            and row["profit_factor"] > 1.0
                        )
                        if eligible:
                            rank = (row["positive_month_rate"], row["score"], row["profit_factor"])
                            if best is None or rank > (
                                best["positive_month_rate"], best["score"], best["profit_factor"],
                            ):
                                best = row.copy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep = pd.DataFrame(rows).sort_values(
        ["frequency_pass", "positive_month_rate", "score"], ascending=[False, False, False],
    )
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None:
        (OUTPUT / "REPORT.md").write_text(
            "# Daily King Regime Session First Candle RR2\n\nNo 2026 candidate passed.\n",
            encoding="utf-8",
        )
        print(sweep.head(30).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    entries = session_entries(
        df, bars, regime, daily_risk, str(best["session_mode"]),
        float(best["body_fraction"]), str(best["risk_source"]), START, END,
    )
    fixed = intraday.simulate(
        df, entries, float(best["risk_mult"]), int(best["max_hold_bars"]),
    )
    metrics.audit_orders(fixed)
    sample = metrics.select_period(fixed, SELECTION_START, END)
    full = metrics.select_period(fixed, START, END)
    result_rows = [metrics.summarize("selection_2026", SELECTION_START, END, 142, sample)]
    for start, end, days in metrics.SLICES:
        result_rows.append(metrics.summarize(
            "3y_chunk", start, end, days, metrics.select_period(fixed, start, end),
        ))
    result_rows.append(metrics.summarize("full", START, END, 5125, full))
    result = pd.DataFrame(result_rows)
    result["frequency_pass"] = result["trades_per_trading_day"].between(1.0, 3.0, inclusive="both")
    result["passed"] = result["frequency_pass"] & result["performance_pass"]
    result.round(4).to_csv(OUTPUT / "fixed_validation_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUTPUT / "selection_2026_trades.csv", index=False, encoding="utf-8-sig")
    full.to_csv(OUTPUT / "full_trades.csv", index=False, encoding="utf-8-sig")
    metrics.breakdown(full, "year").round(4).to_csv(
        OUTPUT / "full_yearly.csv", index=False, encoding="utf-8-sig",
    )
    chunk_passes = int(result.loc[result["period"] == "3y_chunk", "performance_pass"].sum())
    full_performance = bool(result.loc[result["period"] == "full", "performance_pass"].iloc[0])
    final = (
        "PASSED" if full_performance and chunk_passes == 6
        else ("CONDITIONAL_PASS" if full_performance else "REJECTED")
    )
    keys = ["session_mode", "body_fraction", "risk_source", "risk_mult", "max_hold_bars"]
    report = [
        "# Daily King Regime Session First Candle RR2", "",
        "- Regime: completed gap-aware daily SMA60 King Keltner position",
        "- Trigger: first completed 15m candle of each selected session, color aligned with regime",
        "- Entry: next 5m open; exact 2R with 5m adverse-stop first",
        "- Controls: one position, at most three entries/day, cost 0.5", "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in keys) + "`", "",
        f"Final decision: **{final}**. Profitable chunks: {chunk_passes}/6.", "",
        metrics.markdown_table(result), "",
        "Intraday parameters were selected on 2026 and frozen historically.",
        "The SMA60 regime remains a full-history-discovered research component.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
