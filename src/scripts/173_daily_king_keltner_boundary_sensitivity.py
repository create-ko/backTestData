# -*- coding: utf-8 -*-
"""Audit daily King Keltner across session boundaries and partial-bar handling."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "daily_king_keltner_boundary_sensitivity"
SLICES = [
    ("2010-01-01", "2013-01-01"), ("2013-01-01", "2016-01-01"),
    ("2016-01-01", "2019-01-01"), ("2019-01-01", "2022-01-01"),
    ("2022-01-01", "2025-01-01"), ("2025-01-01", "2026-06-17"),
]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


intraday = load_module("intraday157_for_173", SCRIPT_DIR / "157_intraday_king_keltner_rr2.py")
research = load_module("research167_for_173", SCRIPT_DIR / "167_daily_king_keltner_2026_selection.py")


def aggregate_fixed(df: pd.DataFrame, hour_kst: int, minimum_bars: int = 0) -> pd.DataFrame:
    local = df.index.tz_convert("Asia/Seoul").tz_localize(None)
    keys = (local - pd.Timedelta(hours=hour_kst)).date
    work = df[["open", "high", "low", "close"]].copy()
    work["session_key"] = keys
    grouped = work.groupby("session_key", sort=True)
    out = grouped.agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), bar_count=("close", "size"),
    ).reset_index()
    if minimum_bars:
        out = out[out["bar_count"] >= minimum_bars].copy()
    out["time"] = pd.to_datetime(out["session_key"].astype(str)).dt.tz_localize("Asia/Seoul") + pd.Timedelta(hours=hour_kst)
    out["time"] = out["time"].dt.tz_convert("UTC")
    return add_features(out)


def aggregate_new_york(df: pd.DataFrame, minimum_bars: int = 0) -> pd.DataFrame:
    local = df.index.tz_convert("America/New_York").tz_localize(None)
    keys = (local - pd.Timedelta(hours=17)).date
    work = df[["open", "high", "low", "close"]].copy()
    work["session_key"] = keys
    grouped = work.groupby("session_key", sort=True)
    out = grouped.agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), bar_count=("close", "size"),
    ).reset_index()
    if minimum_bars:
        out = out[out["bar_count"] >= minimum_bars].copy()
    ny = ZoneInfo("America/New_York")
    out["time"] = [
        pd.Timestamp(year=day.year, month=day.month, day=day.day, hour=17, tz=ny).tz_convert("UTC")
        for day in out["session_key"]
    ]
    return add_features(out)


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values("time").reset_index(drop=True)
    out["typical"] = (out["high"] + out["low"] + out["close"]) / 3.0
    previous_close = out["close"].shift(1)
    out["tr"] = pd.concat([
        out["high"] - out["low"],
        (out["high"] - previous_close).abs(),
        (out["low"] - previous_close).abs(),
    ], axis=1).max(axis=1)
    return out


def config_trades(frame: pd.DataFrame, atr_length: int, band: float) -> pd.DataFrame:
    center = frame["typical"].rolling(60, min_periods=60).mean().to_numpy(float)
    atr = frame["tr"].rolling(atr_length, min_periods=atr_length).mean().to_numpy(float)
    return research.simulate(frame, center, atr, band)


def main() -> None:
    df = intraday.prepare()
    frames = {
        "utc00_raw": aggregate_fixed(df, 9, 0),
        "utc00_drop_short": aggregate_fixed(df, 9, 100),
        "ny17": aggregate_new_york(df, 0),
        "ny17_drop_short": aggregate_new_york(df, 100),
        "kst07": aggregate_fixed(df, 7, 0),
        "kst08": aggregate_fixed(df, 8, 0),
        "kst00": aggregate_fixed(df, 0, 0),
    }
    rows = []
    neighbor_rows = []
    central_trades = {}
    for name, frame in frames.items():
        trades = config_trades(frame, 40, 1.0)
        central_trades[name] = trades
        full = research.stats(trades)
        chunk_nets = [
            research.stats(research.period(trades, start, end))["net"]
            for start, end in SLICES
        ]
        holdout = research.stats(research.period(trades, "2019-01-01", "2026-06-17"))
        rows.append({
            "boundary": name, "daily_bars": len(frame),
            "short_bars_under_100": int((frame["bar_count"] < 100).sum()),
            "trades": full["trades"], "net_points": full["net"],
            "profit_factor": full["pf"], "max_drawdown": full["dd"],
            "positive_chunks": sum(value > 0 for value in chunk_nets),
            "worst_chunk_net": min(chunk_nets),
            "holdout_trades": holdout["trades"], "holdout_net": holdout["net"],
            "holdout_pf": holdout["pf"],
            **{f"chunk_{i + 1}_net": value for i, value in enumerate(chunk_nets)},
        })
        for atr_length in [20, 30, 40, 60, 80]:
            for band in [0.5, 0.75, 1.0, 1.25, 1.5]:
                candidate = config_trades(frame, atr_length, band)
                nets = [
                    research.stats(research.period(candidate, start, end))["net"]
                    for start, end in SLICES
                ]
                summary = research.stats(candidate)
                neighbor_rows.append({
                    "boundary": name, "atr_length": atr_length, "band": band,
                    "trades": summary["trades"], "net_points": summary["net"],
                    "profit_factor": summary["pf"],
                    "positive_chunks": sum(value > 0 for value in nets),
                    "worst_chunk_net": min(nets),
                })
    summary = pd.DataFrame(rows)
    neighbors = pd.DataFrame(neighbor_rows)
    neighbor_summary = neighbors.groupby("boundary").agg(
        configs=("boundary", "size"),
        six_chunk_configs=("positive_chunks", lambda values: int((values == 6).sum())),
        median_pf=("profit_factor", "median"),
        minimum_worst_chunk=("worst_chunk_net", "min"),
    ).reset_index()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary.round(4).to_csv(OUTPUT / "central_config_summary.csv", index=False, encoding="utf-8-sig")
    neighbors.round(4).to_csv(OUTPUT / "neighbor_configs.csv", index=False, encoding="utf-8-sig")
    neighbor_summary.round(4).to_csv(OUTPUT / "neighbor_summary.csv", index=False, encoding="utf-8-sig")
    for name, trades in central_trades.items():
        trades.to_csv(OUTPUT / f"trades_{name}.csv", index=False, encoding="utf-8-sig")
    report = [
        "# Daily King Keltner Boundary Sensitivity", "",
        "The SMA60 / simple TR40 / 1ATR candidate is rebuilt from 5m data under multiple daily boundaries.",
        "New York 17:00 and KST 07:00/08:00 boundaries merge the Sunday open into the following trading session.",
        "UTC-calendar raw preserves the legacy short Sunday partial bars for comparison.", "",
        summary.round(4).to_string(index=False), "",
        neighbor_summary.round(4).to_string(index=False), "",
        "A TradingView-ready strategy requires stability on session-based daily bars, not only legacy UTC calendar bars.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("CENTRAL")
    print(summary.round(4).to_string(index=False))
    print("NEIGHBORS")
    print(neighbor_summary.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
