# -*- coding: utf-8 -*-
"""Walk-forward long/short selector for scheduled session fixed-2R entries."""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict, deque
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "walkforward_session_direction_rr2"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


base = load_module("base147_for_148", SCRIPT_DIR / "147_three_session_atr_rr2_search.py")
metrics = load_module("metrics144_for_148", SCRIPT_DIR / "144_bb20_rr2_daily2_validation.py")


def pair_outcomes(long_trades: pd.DataFrame, short_trades: pd.DataFrame) -> list[dict]:
    long_map = {row.entry_time: row for row in long_trades.itertuples(index=False)}
    short_map = {row.entry_time: row for row in short_trades.itertuples(index=False)}
    times = sorted(set(long_map) & set(short_map))
    return [{"entry_time": ts, "long": long_map[ts], "short": short_map[ts]} for ts in times]


def choose_walkforward(pairs: list[dict], lookback: int, scope: str) -> pd.DataFrame:
    histories = defaultdict(lambda: deque(maxlen=lookback))
    pending = []
    selected = []
    for pair in pairs:
        now = pair["entry_time"]
        still_pending = []
        for old in pending:
            completion = max(old["long"].exit_time, old["short"].exit_time)
            if completion < now:
                key = old["long"].session if scope == "session" else "all"
                histories[key].append((float(old["long"].net_points), float(old["short"].net_points)))
            else:
                still_pending.append(old)
        pending = still_pending
        key = pair["long"].session if scope == "session" else "all"
        history = histories[key]
        if len(history) >= min(10, lookback):
            long_avg = sum(item[0] for item in history) / len(history)
            short_avg = sum(item[1] for item in history) / len(history)
            direction = "long" if long_avg >= short_avg else "short"
        else:
            direction = "long"
        selected.append(pair[direction]._asdict())
        pending.append(pair)
    trades = pd.DataFrame(selected).sort_values("entry_time").reset_index(drop=True)
    return base.apply_concurrency_cap(trades, 5)


def selection_metrics(trades: pd.DataFrame) -> dict:
    sample = trades[(trades["entry_time"] >= pd.Timestamp("2026-01-01", tz="Asia/Seoul")) & (trades["entry_time"] < pd.Timestamp("2026-06-17", tz="Asia/Seoul"))]
    pnl = sample["net_points"]
    monthly = sample.groupby("month")["net_points"].sum()
    return {
        "sample_trades": len(sample),
        "sample_trades_per_day": len(sample) / 142,
        "sample_net_points": pnl.sum(),
        "sample_profit_factor": metrics.profit_factor(pnl),
        "sample_max_drawdown": metrics.max_drawdown(pnl),
        "sample_positive_month_rate": (monthly > 0).mean() * 100,
    }


def main() -> None:
    df = base.load_data()
    rows = []
    best = None
    best_trades = None
    for mult in [6.0, 10.0, 15.0]:
        for floor in [0.8, 1.5]:
            long_entries = base.make_entries(df, "long", mult, floor)
            short_entries = base.make_entries(df, "short", mult, floor)
            for hold in [120, 240]:
                long_outcomes = base.simulate(df, long_entries, hold, concurrency_cap=0)
                short_outcomes = base.simulate(df, short_entries, hold, concurrency_cap=0)
                pairs = pair_outcomes(long_outcomes, short_outcomes)
                for lookback in [20, 60, 120]:
                    for scope in ["global", "session"]:
                        trades = choose_walkforward(pairs, lookback, scope)
                        row = {
                            "volatility_mult": mult,
                            "risk_floor": floor,
                            "max_hold_bars": hold,
                            "lookback": lookback,
                            "scope": scope,
                        }
                        row.update(selection_metrics(trades))
                        row["frequency_pass"] = 2.0 <= row["sample_trades_per_day"] <= 3.0
                        row["score"] = row["sample_net_points"] - 0.2 * row["sample_max_drawdown"] + 2.0 * row["sample_positive_month_rate"]
                        rows.append(row)
                        if row["frequency_pass"] and row["sample_net_points"] > 0 and row["sample_profit_factor"] > 1.0:
                            if best is None or (row["sample_positive_month_rate"], row["score"]) > (best["sample_positive_month_rate"], best["score"]):
                                best = row.copy()
                                best_trades = trades.copy()

    sweep = pd.DataFrame(rows).sort_values(["frequency_pass", "score"], ascending=[False, False])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sweep.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    if best is None or best_trades is None:
        (OUTPUT / "REPORT.md").write_text("# Walk-Forward Session Direction RR2\n\nNo 2026 candidate passed.\n", encoding="utf-8")
        print(sweep.head(30).round(4).to_string(index=False))
        print("FINAL NO_2026_CANDIDATE")
        return

    metrics.audit_orders(best_trades)
    sample = metrics.select_period(best_trades, "2026-01-01", "2026-06-17")
    full = metrics.select_period(best_trades, "2010-01-01", "2026-06-17")
    result_rows = [metrics.summarize("selection_2026", "2026-01-01", "2026-06-17", 142, sample)]
    for start, end, days in metrics.SLICES:
        result_rows.append(metrics.summarize("3y_chunk", start, end, days, metrics.select_period(best_trades, start, end)))
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
        "# Walk-Forward Session Direction RR2",
        "",
        "- Scheduled Asia, Europe, and US-open entries",
        "- Direction uses only completed prior hypothetical long/short outcomes",
        "- Fixed 2R target, volatility-scaled stop, 0.5-point cost, five-position cap",
        "",
        "Selected config: `" + ", ".join(f"{key}={best[key]}" for key in ["volatility_mult", "risk_floor", "max_hold_bars", "lookback", "scope"]) + "`",
        "",
        f"Final decision: **{final}**.",
        "",
        metrics.markdown_table(result),
        "",
        "The walk-forward rule and parameters remain fixed in all historical slices.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("BEST_2026", best)
    print(result.round(4).to_string(index=False))
    print("FINAL", final)


if __name__ == "__main__":
    main()
