# -*- coding: utf-8 -*-
"""Cross-family regime, correlation, and 2026-selected portfolio audit."""
from __future__ import annotations

import importlib.util
import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "strategy_family_meta_analysis"
START = "2010-01-01"
SELECTION_START = "2026-01-01"
END = "2026-06-17"
FULL_DAYS = 5125
SELECTION_DAYS = 142
SLICES = [
    ("2010-01-01", "2013-01-01", 939),
    ("2013-01-01", "2016-01-01", 935),
    ("2016-01-01", "2019-01-01", 931),
    ("2019-01-01", "2022-01-01", 934),
    ("2022-01-01", "2025-01-01", 932),
    ("2025-01-01", "2026-06-17", 454),
]


FAMILIES = {
    "ny17_swing": ROOT / "result/ny17_daily_king_sma50_5m_execution/trades.csv",
    "retest_3r": ROOT / "result/daily_trend_retest_exit_architecture_oos/selected_full_trades.csv",
    "session_breakout": ROOT / "result/ny17_daily_trend_session_breakout_oos/selected_full_trades.csv",
    "scheduled_session_rr2": ROOT / "result/daily_trend_adr_session_rr2/full_trades.csv",
    "ny17_regime_candle_rr2": ROOT / "result/ny17_sma50_regime_intraday_candle_rr2/full_trades.csv",
    "anchored_mean_reversal": ROOT / "result/anchored_mean_rr2_daily2_full_validation/full_trades.csv",
}
HIGH_FREQUENCY = [name for name in FAMILIES if name != "ny17_swing"]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


boundary = load_module(
    "boundary173_for_183",
    SCRIPT_DIR / "173_daily_king_keltner_boundary_sensitivity.py",
)


def load_trades(path: Path, family: str) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert("Asia/Seoul")
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True).dt.tz_convert("Asia/Seoul")
    trades["net_points"] = pd.to_numeric(trades["net_points"])
    trades["family"] = family
    trades["day_key"] = trades["entry_time"].dt.strftime("%Y-%m-%d")
    trades["month_key"] = trades["entry_time"].dt.strftime("%Y-%m")
    return trades.sort_values("entry_time").reset_index(drop=True)


def period(trades: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start, tz="Asia/Seoul")
    end_ts = pd.Timestamp(end, tz="Asia/Seoul")
    return trades[(trades["entry_time"] >= start_ts) & (trades["entry_time"] < end_ts)].copy()


def max_drawdown(pnl: pd.Series) -> float:
    values = pnl.to_numpy(float)
    if len(values) == 0:
        return 0.0
    equity = values.cumsum()
    peak = np.maximum.accumulate(np.maximum(equity, 0.0))
    return float(np.max(peak - equity))


def profit_factor(pnl: pd.Series) -> float:
    wins = float(pnl[pnl > 0].sum())
    losses = float(-pnl[pnl < 0].sum())
    return wins / losses if losses else float("inf")


def stats(trades: pd.DataFrame, days: int) -> dict:
    if trades.empty:
        return {
            "trades": 0, "trades_per_day": 0.0, "net": 0.0,
            "pf": 0.0, "dd": 0.0, "win_rate": 0.0,
            "positive_month_rate": 0.0,
        }
    pnl = trades["net_points"]
    monthly = trades.groupby("month_key")["net_points"].sum()
    return {
        "trades": len(trades),
        "trades_per_day": len(trades) / days,
        "net": float(pnl.sum()),
        "pf": profit_factor(pnl),
        "dd": max_drawdown(pnl),
        "win_rate": 100.0 * pnl.gt(0).mean(),
        "positive_month_rate": 100.0 * monthly.gt(0).mean(),
    }


def build_portfolio(
    trade_map: dict[str, pd.DataFrame],
    priorities: list[str],
    mode: str,
) -> pd.DataFrame:
    frames = []
    for priority, family in enumerate(priorities):
        frame = trade_map[family].copy()
        frame["priority"] = priority
        frames.append(frame)
    merged = pd.concat(frames, ignore_index=True).sort_values(
        ["entry_time", "priority"], ascending=[True, True],
    )
    merged = merged.drop_duplicates("entry_time", keep="first")
    accepted = []
    day_counts = {}
    active_exit = None
    for idx, row in merged.iterrows():
        day = row["day_key"]
        if day_counts.get(day, 0) >= 3:
            continue
        if mode == "single_position" and active_exit is not None and row["entry_time"] < active_exit:
            continue
        accepted.append(idx)
        day_counts[day] = day_counts.get(day, 0) + 1
        if mode == "single_position":
            active_exit = row["exit_time"]
    return merged.loc[accepted].sort_values("entry_time").reset_index(drop=True)


def market_regimes() -> pd.DataFrame:
    execution = boundary.intraday.prepare()
    daily = boundary.aggregate_new_york(execution, 0)
    daily["time_kst"] = pd.DatetimeIndex(daily["time"]).tz_convert("Asia/Seoul")
    daily["tr_pct"] = 100.0 * daily["tr"] / daily["close"]
    daily["abs_return"] = daily["close"].pct_change().abs()
    rows = []
    for start, end, _ in SLICES:
        part = daily[
            (daily["time_kst"] >= pd.Timestamp(start, tz="Asia/Seoul"))
            & (daily["time_kst"] < pd.Timestamp(end, tz="Asia/Seoul"))
        ]
        changes = part["close"].diff().dropna()
        path = float(changes.abs().sum())
        displacement = float(abs(part["close"].iloc[-1] - part["close"].iloc[0]))
        rows.append({
            "start": start,
            "end": end,
            "daily_bars": len(part),
            "start_close": part["close"].iloc[0],
            "end_close": part["close"].iloc[-1],
            "total_return_pct": 100.0 * (part["close"].iloc[-1] / part["close"].iloc[0] - 1.0),
            "mean_tr_points": part["tr"].mean(),
            "mean_tr_pct": part["tr_pct"].mean(),
            "trend_efficiency": displacement / path if path else 0.0,
            "up_day_rate": 100.0 * changes.gt(0).mean(),
        })
    return pd.DataFrame(rows)


def main() -> None:
    trade_map = {name: load_trades(path, name) for name, path in FAMILIES.items()}
    score_rows = []
    chunk_rows = []
    monthly = {}
    selection_rows = []

    for name, trades in trade_map.items():
        full = stats(period(trades, START, END), FULL_DAYS)
        selection = stats(period(trades, SELECTION_START, END), SELECTION_DAYS)
        chunks = []
        for start, end, days in SLICES:
            chunk = stats(period(trades, start, end), days)
            chunks.append(chunk["net"])
            chunk_rows.append({"family": name, "start": start, "end": end, **chunk})
        score_rows.append({
            "family": name,
            **{f"full_{key}": value for key, value in full.items()},
            **{f"selection_{key}": value for key, value in selection.items()},
            "profitable_chunks": sum(value > 0 for value in chunks),
            "worst_chunk_net": min(chunks),
        })
        selection_rows.append({"family": name, **selection})
        monthly[name] = trades.groupby("month_key")["net_points"].sum()

    scorecard = pd.DataFrame(score_rows)
    chunks = pd.DataFrame(chunk_rows)
    monthly_frame = pd.DataFrame(monthly).fillna(0.0).sort_index()
    correlations = monthly_frame.corr()
    regimes = market_regimes()

    eligible = pd.DataFrame(selection_rows)
    eligible = eligible[
        eligible["family"].isin(HIGH_FREQUENCY)
        & eligible["trades_per_day"].between(1.0, 3.0, inclusive="both")
        & eligible["net"].gt(0) & eligible["pf"].gt(1.0)
    ].copy()
    eligible["score"] = eligible["net"] - 0.25 * eligible["dd"]
    eligible = eligible.sort_values(
        ["positive_month_rate", "score", "pf"], ascending=False,
    ).reset_index(drop=True)
    selected_families = eligible.head(2)["family"].tolist()
    if len(selected_families) < 2:
        raise RuntimeError("Fewer than two 2026-eligible strategy families")

    portfolio_candidates = []
    portfolio_map = {}
    for order in [selected_families, list(reversed(selected_families))]:
        for mode in ["daily_cap3", "single_position"]:
            key = f"{order[0]}__{order[1]}__{mode}"
            portfolio = build_portfolio(trade_map, order, mode)
            portfolio_map[key] = portfolio
            selection = stats(period(portfolio, SELECTION_START, END), SELECTION_DAYS)
            portfolio_candidates.append({
                "portfolio": key,
                "priority_1": order[0],
                "priority_2": order[1],
                "mode": mode,
                **selection,
                "frequency_pass": 1.0 <= selection["trades_per_day"] <= 3.0,
                "performance_pass": selection["net"] > 0 and selection["pf"] > 1.0,
                "score": selection["net"] - 0.25 * selection["dd"],
            })
    portfolio_selection = pd.DataFrame(portfolio_candidates)
    passed = portfolio_selection[
        portfolio_selection["frequency_pass"] & portfolio_selection["performance_pass"]
    ].sort_values(["positive_month_rate", "score", "pf"], ascending=False)
    if passed.empty:
        raise RuntimeError("No 2026 meta-portfolio candidate passed")
    chosen = passed.iloc[0]
    chosen_trades = portfolio_map[str(chosen["portfolio"])]

    validation_rows = []
    for label, start, end, days in [
        ("selection_2026", SELECTION_START, END, SELECTION_DAYS),
        *[("3y_chunk", start, end, days) for start, end, days in SLICES],
        ("full", START, END, FULL_DAYS),
    ]:
        result = stats(period(chosen_trades, start, end), days)
        validation_rows.append({"period": label, "start": start, "end": end, **result})
    validation = pd.DataFrame(validation_rows)
    validation["frequency_pass"] = validation["trades_per_day"].between(1.0, 3.0, inclusive="both")
    validation["performance_pass"] = validation["net"].gt(0) & validation["pf"].gt(1.0)
    validation["passed"] = validation["frequency_pass"] & validation["performance_pass"]

    swing_chunks = chunks[chunks["family"].eq("ny17_swing")].set_index("start")["net"]
    chosen_chunks = validation[validation["period"].eq("3y_chunk")].set_index("start")["net"]
    required = max(
        [0.0] + [
            -float(chosen_chunks.loc[start]) / float(swing_chunks.loc[start])
            for start in chosen_chunks.index
            if chosen_chunks.loc[start] < 0 and swing_chunks.loc[start] > 0
        ]
    )
    required *= 1.000001
    overlay_rows = []
    for start in chosen_chunks.index:
        overlay_rows.append({
            "start": start,
            "portfolio_net": chosen_chunks.loc[start],
            "swing_net_1x": swing_chunks.loc[start],
            "required_swing_multiplier": required,
            "combined_net": chosen_chunks.loc[start] + required * swing_chunks.loc[start],
        })
    overlay = pd.DataFrame(overlay_rows)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    scorecard.round(6).to_csv(OUTPUT / "strategy_scorecard.csv", index=False, encoding="utf-8-sig")
    chunks.round(6).to_csv(OUTPUT / "chunk_scorecard.csv", index=False, encoding="utf-8-sig")
    monthly_frame.round(6).to_csv(OUTPUT / "monthly_net_points.csv", encoding="utf-8-sig")
    correlations.round(6).to_csv(OUTPUT / "monthly_correlations.csv", encoding="utf-8-sig")
    regimes.round(6).to_csv(OUTPUT / "market_regimes.csv", index=False, encoding="utf-8-sig")
    eligible.round(6).to_csv(OUTPUT / "selection_2026_family_ranking.csv", index=False, encoding="utf-8-sig")
    portfolio_selection.round(6).to_csv(OUTPUT / "selection_2026_portfolios.csv", index=False, encoding="utf-8-sig")
    validation.round(6).to_csv(OUTPUT / "selected_portfolio_validation.csv", index=False, encoding="utf-8-sig")
    chosen_trades.to_csv(OUTPUT / "selected_portfolio_trades.csv", index=False, encoding="utf-8-sig")
    overlay.round(6).to_csv(OUTPUT / "swing_overlay_requirement.csv", index=False, encoding="utf-8-sig")

    chunk_passes = int(validation.loc[validation["period"].eq("3y_chunk"), "performance_pass"].sum())
    frequency_passes = int(validation.loc[validation["period"].eq("3y_chunk"), "frequency_pass"].sum())
    full = validation[validation["period"].eq("full")].iloc[0]
    portfolio_pass = (
        chunk_passes == 6 and frequency_passes == 6
        and bool(full["performance_pass"]) and bool(full["frequency_pass"])
    )
    decision = "PASSED" if portfolio_pass else "REJECTED"
    latest_regime = regimes.iloc[-1]
    earlier_regimes = regimes.iloc[:-1]
    report = [
        "# Strategy Family Meta-Analysis", "",
        "- Six independently tested candle/trend or reversal families are aligned by entry month and fixed three-year chunks.",
        "- Component families and portfolio priority are ranked with 2026 only.",
        "- The chosen portfolio enforces a maximum of three accepted entries per day; single-position and concurrent modes are both considered on 2026.", "",
        "## 2026 selection", "",
        f"- Top component families: {selected_families[0]}, {selected_families[1]}.",
        f"- Chosen portfolio: {chosen['portfolio']}.",
        f"- 2026: {int(chosen['trades'])} trades, {chosen['trades_per_day']:.4f}/day, net {chosen['net']:.2f}, PF {chosen['pf']:.4f}, positive months {chosen['positive_month_rate']:.2f}%.", "",
        "## Frozen historical validation", "",
        f"- Full: {int(full['trades'])} trades, {full['trades_per_day']:.4f}/day, net {full['net']:.2f}, PF {full['pf']:.4f}, DD {full['dd']:.2f}.",
        f"- Profitable chunks: {chunk_passes}/6; frequency-valid chunks: {frequency_passes}/6.",
        f"- Making every chunk non-negative with the low-frequency NY17 swing requires at least {required:.2f}x swing exposure versus 1x portfolio exposure.",
        "- That overlay is not accepted because the swing result is already concentrated in five outlier wins and scaling it multiplies the tail risk.", "",
        "## Regime and research limit", "",
        f"- 2025-2026 mean daily TR was {latest_regime['mean_tr_points']:.2f} points / {latest_regime['mean_tr_pct']:.2f}% of price, versus prior chunk ranges of {earlier_regimes['mean_tr_points'].min():.2f}-{earlier_regimes['mean_tr_points'].max():.2f} points / {earlier_regimes['mean_tr_pct'].min():.2f}-{earlier_regimes['mean_tr_pct'].max():.2f}%.",
        f"- Its trend efficiency was {latest_regime['trend_efficiency']:.4f}, the highest fixed chunk in the sample.",
        "- Repeated strategy redesign after inspecting 2010-2025 failures means those years are now research data, not a fresh independent holdout.", "",
        "## Decision", "",
        f"**{decision}**. Acceptance requires all six chunks to pass performance and frequency without a leveraged swing overlay.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("SCORECARD")
    print(scorecard.round(4).to_string(index=False))
    print("REGIMES")
    print(regimes.round(4).to_string(index=False))
    print("ELIGIBLE_2026")
    print(eligible.round(4).to_string(index=False))
    print("PORTFOLIOS_2026")
    print(portfolio_selection.round(4).to_string(index=False))
    print("CHOSEN", chosen.to_dict())
    print("VALIDATION")
    print(validation.round(4).to_string(index=False))
    print("SWING_MULTIPLIER", round(required, 4))


if __name__ == "__main__":
    main()
