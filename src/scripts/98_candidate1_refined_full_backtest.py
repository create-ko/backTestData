# -*- coding: utf-8 -*-
"""Refined candidate 1 full-period backtest.

Candidate:
- Monthly regime filter, decided at month start using prior daily data only:
  ret20 >= 0.84%, ret240 >= -4.28%, adr20 >= 18P.
- Grid component: Strategy2 5m r2 entries, only 09:00-18:00 KST, with slower exit:
  regular trail arm 10P, trail 10P, third-fill recovery at avg +/- 3P with 50% reduction.
- Session component: 15m range retest body090, all active-month trades.
- Onebee component: 2m SMA cross box Onebee KTR, all active-month trades.
- Duplicate same entry timestamp + direction is treated as one trade, priority grid > session > onebee.
- Practical risk guard: if same-day cumulative net <= -50P, skip the rest of that KST day.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_5M = ROOT / "data" / "xauusd_5m_2010-01-01_2026-06-16.csv"
GRID_TRADES = ROOT / "result" / "strategy2_grid_third_fill_recovery_rules_cost05" / "strategy2_recovery_rule_trades.csv"
SESSION_TRADES = ROOT / "result" / "strategy_session_15m_range_retest_once_5m_20100101_20260616_body090" / "trades.csv"
ONEBEE_TRADES = ROOT / "result" / "strategy_2m_sma_cross_box_onebee_ktr_20100101_20260616" / "strategy_2m_sma_cross_box_onebee_trades.csv"
OUTPUT_DIR = ROOT / "result" / "candidate1_refined_full_201001_202606"

RET20_MIN = 0.0084
RET240_MIN = -0.0428
ADR20_MIN = 18.0

GRID_ENTRY_START_HOUR = 9
GRID_ENTRY_END_HOUR = 18
GRID_STEP = 10.0
GRID_MAX_ENTRIES = 3
GRID_STOP_FROM_ENTRY1 = 35.0
GRID_REGULAR_ARM = 10.0
GRID_TRAIL_POINTS = 10.0
GRID_R2_RECOVERY_PROFIT = 3.0
GRID_R2_REDUCE_FRACTION = 0.50
BASE_COST_PER_UNIT = 0.50

DAY_STOP_POINTS = 50.0
SOURCE_PRIORITY = {"grid": 0, "session": 1, "onebee": 2}


def kst_series_from_epoch_seconds(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, unit="s", utc=True).dt.tz_convert("Asia/Seoul")


def epoch_seconds(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, utc=True).dt.tz_convert("Asia/Seoul")
    return parsed.map(lambda ts: int(ts.timestamp()))


def profit_factor(values: pd.Series | np.ndarray) -> float:
    vals = np.asarray(values, dtype=float)
    gross_profit = vals[vals > 0].sum()
    gross_loss = -vals[vals < 0].sum()
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return float(gross_profit / gross_loss)


def max_drawdown(values: pd.Series | np.ndarray) -> float:
    vals = np.asarray(values, dtype=float)
    if len(vals) == 0:
        return 0.0
    equity = np.cumsum(vals)
    return float(np.max(np.maximum.accumulate(equity) - equity))


def split_name(year: int) -> str:
    if year <= 2019:
        return "train"
    if year <= 2024:
        return "val"
    return "test"


def summarize(group: pd.DataFrame, extra_cost_per_unit: float = 0.0) -> pd.Series:
    values = group["net_points"].to_numpy(float) - extra_cost_per_unit * group["extra_cost_units"].to_numpy(float)
    return pd.Series(
        {
            "trades": int(len(group)),
            "net_points": float(values.sum()),
            "avg_points": float(values.mean()) if len(values) else 0.0,
            "profit_factor": profit_factor(values),
            "win_rate": float((values > 0).mean() * 100) if len(values) else 0.0,
            "max_drawdown_points": max_drawdown(values),
        }
    )


def table_html(df: pd.DataFrame, title: str) -> str:
    headers = "".join(f"<th>{col}</th>" for col in df.columns)
    body_rows = []
    for _, row in df.iterrows():
        cells = []
        for col, value in row.items():
            klass = ""
            if col in {"net_points", "avg_points", "profit_factor"}:
                try:
                    num = float(value)
                    klass = "pos" if (num >= 1 if col == "profit_factor" else num > 0) else "neg"
                except Exception:
                    klass = ""
            if pd.isna(value):
                text = ""
            elif isinstance(value, float):
                text = f"{value:,.3f}"
            else:
                text = str(value)
            cells.append(f"<td class='{klass}'>{text}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f"<section><h2>{title}</h2><div class='table-wrap'><table>"
        f"<thead><tr>{headers}</tr></thead><tbody>{''.join(body_rows)}</tbody>"
        "</table></div></section>"
    )


def load_bars() -> pd.DataFrame:
    bars = pd.read_csv(DATA_5M)
    bars["dt"] = kst_series_from_epoch_seconds(bars["time"])
    return bars.sort_values("time").reset_index(drop=True)


def build_month_features(bars: pd.DataFrame) -> tuple[pd.DataFrame, set[str], int]:
    daily = bars.set_index("dt").resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    daily["range"] = daily["high"] - daily["low"]

    rows: list[dict] = []
    active_months: set[str] = set()
    for month in pd.period_range("2010-01", "2026-06", freq="M"):
        month_start = pd.Timestamp(month.start_time, tz="Asia/Seoul")
        prior = daily[daily.index < month_start]
        if len(prior) < 260:
            continue
        current_close = float(prior["close"].iloc[-1])
        ret20 = current_close / float(prior["close"].iloc[-20]) - 1.0
        ret240 = current_close / float(prior["close"].iloc[-240]) - 1.0
        adr20 = float(prior["range"].iloc[-20:].mean())
        active = ret20 >= RET20_MIN and ret240 >= RET240_MIN and adr20 >= ADR20_MIN
        row = {
            "month": str(month),
            "ret20": ret20,
            "ret240": ret240,
            "adr20": adr20,
            "active": active,
        }
        rows.append(row)
        if active:
            active_months.add(str(month))

    active_days = daily[daily.index.strftime("%Y-%m").isin(active_months)].shape[0]
    return pd.DataFrame(rows), active_months, int(active_days)


class GridSimulator:
    def __init__(self, bars: pd.DataFrame):
        self.idx = bars["time"].to_numpy(np.int64)
        self.high = bars["high"].to_numpy(float)
        self.low = bars["low"].to_numpy(float)
        self.close = bars["close"].to_numpy(float)

    @staticmethod
    def _pnl(direction: str, avg_entry: float, exit_price: float, qty: float) -> float:
        if direction == "long":
            return (exit_price - avg_entry) * qty
        return (avg_entry - exit_price) * qty

    def simulate(self, row: pd.Series) -> dict:
        direction = str(row["direction"])
        entry_pos = int(np.searchsorted(self.idx, int(row["entry_epoch"])))
        entry1 = float(row["entry_price"])
        if direction == "long":
            levels = [entry1 - i * GRID_STEP for i in range(GRID_MAX_ENTRIES)]
            stop = entry1 - GRID_STOP_FROM_ENTRY1
        else:
            levels = [entry1 + i * GRID_STEP for i in range(GRID_MAX_ENTRIES)]
            stop = entry1 + GRID_STOP_FROM_ENTRY1

        filled = [False] * GRID_MAX_ENTRIES
        fill_prices: list[float] = []
        open_qty = 0.0
        avg_entry = math.nan
        realized = 0.0
        reduced_after_third = False
        trailing = False
        trail_stop = math.nan
        trail_active_from = math.inf
        exit_reason = "open_at_data_end"

        for pos in range(entry_pos, len(self.idx)):
            hi = float(self.high[pos])
            lo = float(self.low[pos])
            cl = float(self.close[pos])

            for i, level in enumerate(levels):
                if filled[i]:
                    continue
                hit = lo <= level if direction == "long" else hi >= level
                if hit:
                    filled[i] = True
                    fill_prices.append(level)
                    open_qty += 1.0
                    avg_entry = sum(fill_prices) / len(fill_prices)

            if open_qty <= 0 or math.isnan(avg_entry):
                continue

            stop_hit = lo <= stop if direction == "long" else hi >= stop
            if stop_hit:
                realized += self._pnl(direction, avg_entry, stop, open_qty)
                open_qty = 0.0
                exit_reason = "stop_35p"
                break

            if len(fill_prices) >= 3 and not reduced_after_third:
                recovery_price = (
                    avg_entry + GRID_R2_RECOVERY_PROFIT
                    if direction == "long"
                    else avg_entry - GRID_R2_RECOVERY_PROFIT
                )
                recovery_hit = hi >= recovery_price if direction == "long" else lo <= recovery_price
                if recovery_hit:
                    qty = open_qty * GRID_R2_REDUCE_FRACTION
                    realized += self._pnl(direction, avg_entry, recovery_price, qty)
                    open_qty -= qty
                    reduced_after_third = True
                    trailing = True
                    trail_stop = avg_entry
                    trail_active_from = pos + 1

            if open_qty <= 0:
                exit_reason = "recovery_full"
                break

            trail_hit = (
                trailing
                and not math.isnan(trail_stop)
                and pos >= trail_active_from
                and (lo <= trail_stop if direction == "long" else hi >= trail_stop)
            )
            if trail_hit:
                realized += self._pnl(direction, avg_entry, trail_stop, open_qty)
                open_qty = 0.0
                exit_reason = "trail_10p"
                break

            if reduced_after_third:
                if direction == "long":
                    trail_stop = (
                        max(avg_entry, cl - GRID_TRAIL_POINTS)
                        if math.isnan(trail_stop)
                        else max(trail_stop, avg_entry, cl - GRID_TRAIL_POINTS)
                    )
                else:
                    trail_stop = (
                        min(avg_entry, cl + GRID_TRAIL_POINTS)
                        if math.isnan(trail_stop)
                        else min(trail_stop, avg_entry, cl + GRID_TRAIL_POINTS)
                    )
                continue

            regular_arm_hit = cl >= avg_entry + GRID_REGULAR_ARM if direction == "long" else cl <= avg_entry - GRID_REGULAR_ARM
            if regular_arm_hit:
                trailing = True
                trail_active_from = min(trail_active_from, pos + 1)
                if direction == "long":
                    trail_stop = (
                        max(avg_entry, cl - GRID_TRAIL_POINTS)
                        if math.isnan(trail_stop)
                        else max(trail_stop, avg_entry, cl - GRID_TRAIL_POINTS)
                    )
                else:
                    trail_stop = (
                        min(avg_entry, cl + GRID_TRAIL_POINTS)
                        if math.isnan(trail_stop)
                        else min(trail_stop, avg_entry, cl + GRID_TRAIL_POINTS)
                    )

        if open_qty > 0:
            final_close = float(self.close[-1])
            realized += self._pnl(direction, avg_entry, final_close, open_qty)

        fills = len(fill_prices)
        return {
            "net_points": realized - BASE_COST_PER_UNIT * fills,
            "extra_cost_units": fills,
            "exit_reason": exit_reason,
            "filled_entries": fills,
        }


def grid_component(bars: pd.DataFrame, active_months: set[str]) -> pd.DataFrame:
    trades = pd.read_csv(GRID_TRADES)
    trades = trades[(trades["tf"] == "5m") & (trades["recovery_rule"] == "r2_avg_plus3_70pct")].copy()
    trades["entry_dt"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert("Asia/Seoul")
    trades["entry_epoch"] = trades["entry_dt"].map(lambda ts: int(ts.timestamp()))
    trades["month"] = trades["entry_dt"].dt.strftime("%Y-%m")
    trades = trades[
        trades["month"].isin(active_months)
        & (trades["entry_dt"].dt.hour >= GRID_ENTRY_START_HOUR)
        & (trades["entry_dt"].dt.hour < GRID_ENTRY_END_HOUR)
    ].copy()

    simulator = GridSimulator(bars)
    rows: list[dict] = []
    for _, row in trades.iterrows():
        simulated = simulator.simulate(row)
        entry_dt = row["entry_dt"]
        rows.append(
            {
                "source": "grid",
                "dedupe_key": f"{int(row['entry_epoch'])}_{row['direction']}",
                "entry_dt": entry_dt,
                "year": int(entry_dt.year),
                "month": str(row["month"]),
                "day": entry_dt.date().isoformat(),
                "split": split_name(int(entry_dt.year)),
                "direction": row["direction"],
                **simulated,
            }
        )
    return pd.DataFrame(rows)


def session_component(active_months: set[str]) -> pd.DataFrame:
    trades = pd.read_csv(SESSION_TRADES)
    trades["entry_dt"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert("Asia/Seoul")
    trades["entry_epoch"] = trades["entry_dt"].map(lambda ts: int(ts.timestamp()))
    trades["month"] = trades["entry_dt"].dt.strftime("%Y-%m")
    trades = trades[trades["month"].isin(active_months)].copy()

    rows = []
    for _, row in trades.iterrows():
        entry_dt = row["entry_dt"]
        rows.append(
            {
                "source": "session",
                "dedupe_key": f"{int(row['entry_epoch'])}_{row['direction']}",
                "entry_dt": entry_dt,
                "year": int(entry_dt.year),
                "month": str(row["month"]),
                "day": entry_dt.date().isoformat(),
                "split": split_name(int(entry_dt.year)),
                "direction": row["direction"],
                "net_points": float(row["net_points"]),
                "extra_cost_units": 1,
                "exit_reason": row.get("exit_reason", ""),
                "filled_entries": 1,
            }
        )
    return pd.DataFrame(rows)


def onebee_component(active_months: set[str]) -> pd.DataFrame:
    trades = pd.read_csv(ONEBEE_TRADES)
    trades["entry_dt"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert("Asia/Seoul")
    trades["entry_epoch"] = trades["entry_dt"].map(lambda ts: int(ts.timestamp()))
    trades["month"] = trades["entry_dt"].dt.strftime("%Y-%m")
    trades = trades[trades["month"].isin(active_months)].copy()
    net_col = "net_points_total" if "net_points_total" in trades.columns else "net_points"

    rows = []
    for _, row in trades.iterrows():
        entry_dt = row["entry_dt"]
        rows.append(
            {
                "source": "onebee",
                "dedupe_key": f"{int(row['entry_epoch'])}_{row['direction']}",
                "entry_dt": entry_dt,
                "year": int(entry_dt.year),
                "month": str(row["month"]),
                "day": entry_dt.date().isoformat(),
                "split": split_name(int(entry_dt.year)),
                "direction": row["direction"],
                "net_points": float(row[net_col]),
                "extra_cost_units": 1,
                "exit_reason": row.get("exit_reason", ""),
                "filled_entries": 1,
            }
        )
    return pd.DataFrame(rows)


def dedupe_trades(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    seen: set[str] = set()
    sorted_trades = trades.sort_values(
        by=["entry_dt", "source"],
        key=lambda col: col.map(SOURCE_PRIORITY) if col.name == "source" else col,
    )
    for _, row in sorted_trades.iterrows():
        key = str(row["dedupe_key"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("entry_dt").reset_index(drop=True)


def apply_day_stop(trades: pd.DataFrame) -> pd.DataFrame:
    keep_indices = []
    stopped_day = None
    day_pnl: dict[str, float] = {}
    for idx, row in trades.sort_values("entry_dt").iterrows():
        day = str(row["day"])
        if stopped_day == day:
            continue
        current = day_pnl.get(day, 0.0)
        if current <= -DAY_STOP_POINTS:
            stopped_day = day
            continue
        keep_indices.append(idx)
        day_pnl[day] = current + float(row["net_points"])
    return trades.loc[keep_indices].sort_values("entry_dt").reset_index(drop=True)


def write_outputs(
    month_features: pd.DataFrame,
    combined_before_stop: pd.DataFrame,
    selected: pd.DataFrame,
    active_days: int,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    month_features.to_csv(OUTPUT_DIR / "month_features.csv", index=False, encoding="utf-8-sig")

    before = combined_before_stop.copy()
    before["entry_dt"] = before["entry_dt"].astype(str)
    before.to_csv(OUTPUT_DIR / "candidate1_combined_before_day_stop.csv", index=False, encoding="utf-8-sig")

    out = selected.copy()
    out["entry_dt"] = out["entry_dt"].astype(str)
    out.to_csv(OUTPUT_DIR / "candidate1_selected_trades.csv", index=False, encoding="utf-8-sig")

    summary_rows = []
    for extra_cost in [0.0, 0.2, 0.3, 0.5, 0.8, 1.0]:
        row = summarize(selected, extra_cost).to_dict()
        row["extra_cost_per_unit"] = extra_cost
        row["active_days"] = active_days
        row["trades_per_active_day"] = len(selected) / active_days if active_days else 0.0
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUTPUT_DIR / "candidate1_summary_cost_sensitivity.csv", index=False, encoding="utf-8-sig")

    by_source = selected.groupby("source", sort=True).apply(summarize, include_groups=False).reset_index()
    by_split = selected.groupby("split", sort=True).apply(summarize, include_groups=False).reset_index()
    yearly = selected.groupby("year", sort=True).apply(summarize, include_groups=False).reset_index()
    monthly = selected.groupby("month", sort=True).apply(summarize, include_groups=False).reset_index()
    yearly_e03 = selected.groupby("year", sort=True).apply(lambda group: summarize(group, 0.3), include_groups=False).reset_index()

    by_source.to_csv(OUTPUT_DIR / "candidate1_by_source.csv", index=False, encoding="utf-8-sig")
    by_split.to_csv(OUTPUT_DIR / "candidate1_by_split.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "candidate1_yearly.csv", index=False, encoding="utf-8-sig")
    yearly_e03.to_csv(OUTPUT_DIR / "candidate1_yearly_extra03.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "candidate1_monthly.csv", index=False, encoding="utf-8-sig")

    active_months = int(month_features["active"].sum())
    month_pos = int((monthly["net_points"] > 0).sum())
    month_neg = int((monthly["net_points"] < 0).sum())
    top_summary = summary.iloc[0]
    extra03 = summary[summary["extra_cost_per_unit"] == 0.3].iloc[0]

    report = f"""# Candidate 1 Refined Full Backtest

## Rule
- Monthly filter: ret20 >= {RET20_MIN:.4f}, ret240 >= {RET240_MIN:.4f}, adr20 >= {ADR20_MIN:.1f}P.
- Grid: Strategy2 5m r2, KST {GRID_ENTRY_START_HOUR:02d}:00-{GRID_ENTRY_END_HOUR:02d}:00, arm {GRID_REGULAR_ARM:.0f}P, trail {GRID_TRAIL_POINTS:.0f}P, third-fill +{GRID_R2_RECOVERY_PROFIT:.0f}P / {GRID_R2_REDUCE_FRACTION:.0%} reduce.
- Session: body090 5m session retest.
- Onebee: 2m SMA cross box Onebee KTR.
- Duplicate same entry time + direction: grid > session > onebee.
- Day stop: stop new entries for the KST day after cumulative day net <= -{DAY_STOP_POINTS:.0f}P.

## Headline
- Active months: {active_months}
- Active days: {active_days}
- Trades: {int(top_summary['trades'])}
- Trades per active day: {top_summary['trades_per_active_day']:.3f}
- Net: {top_summary['net_points']:.1f}P
- Average: {top_summary['avg_points']:.3f}P
- PF: {top_summary['profit_factor']:.3f}
- MDD: {top_summary['max_drawdown_points']:.1f}P
- Positive/negative months: {month_pos}/{month_neg}

## Cost Sensitivity
- Extra +0.3P/unit: net {extra03['net_points']:.1f}P, avg {extra03['avg_points']:.3f}P, PF {extra03['profit_factor']:.3f}, MDD {extra03['max_drawdown_points']:.1f}P.
- Extra +1.0P/unit: net {summary[summary['extra_cost_per_unit'] == 1.0].iloc[0]['net_points']:.1f}P, PF {summary[summary['extra_cost_per_unit'] == 1.0].iloc[0]['profit_factor']:.3f}.

## Caveat
This is a practical candidate, not a guarantee. 2011 remains negative, and the 2025-12 month is still the worst single active month.
"""
    (OUTPUT_DIR / "candidate1_report.md").write_text(report, encoding="utf-8")

    html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Candidate 1 Refined Backtest Report</title>
<style>
body{{margin:0;background:#f5f6f8;color:#17202a;font-family:Arial,'Malgun Gothic',sans-serif}}
header{{background:#111827;color:white;padding:28px 40px}}
h1{{margin:0 0 8px;font-size:26px}} header p{{margin:0;color:#cbd5e1}}
main{{max-width:1500px;margin:0 auto;padding:24px 40px 48px}}
section{{background:white;border:1px solid #d9dee7;border-radius:8px;padding:18px;margin:16px 0}}
h2{{font-size:18px;margin:0 0 12px}}
.cards{{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:10px}}
.card{{border:1px solid #d9dee7;border-radius:8px;padding:12px;background:#fbfcfe}}
.k{{font-size:12px;color:#64748b}}.v{{font-size:22px;font-weight:700;margin-top:4px}}
.table-wrap{{overflow-x:auto;border:1px solid #d9dee7;border-radius:8px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border-bottom:1px solid #d9dee7;padding:7px 9px;text-align:right;white-space:nowrap}}
th{{background:#eef2f7}}td:first-child,th:first-child{{text-align:left}}
.pos{{color:#087f5b;font-weight:700;background:#e6f4ee}}.neg{{color:#c92a2a;font-weight:700;background:#fff0f0}}
</style>
</head>
<body>
<header>
<h1>Candidate 1 Refined Full Backtest</h1>
<p>2010-01 ~ 2026-06, XAUUSD CFD research data. Local Python report is the authoritative result.</p>
</header>
<main>
<section>
<h2>Headline</h2>
<div class="cards">
<div class="card"><div class="k">Active Months</div><div class="v">{active_months}</div></div>
<div class="card"><div class="k">Active Days</div><div class="v">{active_days}</div></div>
<div class="card"><div class="k">Trades / Day</div><div class="v">{top_summary['trades_per_active_day']:.3f}</div></div>
<div class="card"><div class="k">Trades</div><div class="v">{int(top_summary['trades'])}</div></div>
<div class="card"><div class="k">Net</div><div class="v">{top_summary['net_points']:.1f}P</div></div>
<div class="card"><div class="k">Avg</div><div class="v">{top_summary['avg_points']:.3f}P</div></div>
<div class="card"><div class="k">PF</div><div class="v">{top_summary['profit_factor']:.3f}</div></div>
<div class="card"><div class="k">MDD</div><div class="v">{top_summary['max_drawdown_points']:.1f}P</div></div>
</div>
</section>
{table_html(summary, "Cost Sensitivity")}
{table_html(by_split, "Train / Validation / Test")}
{table_html(by_source, "By Source")}
{table_html(yearly, "Yearly Report")}
{table_html(yearly_e03, "Yearly Report: Extra +0.3P/unit")}
{table_html(monthly, "Monthly Report")}
</main>
</body>
</html>
"""
    (OUTPUT_DIR / "candidate1_report.html").write_text(html, encoding="utf-8")


def main() -> None:
    bars = load_bars()
    month_features, active_months, active_days = build_month_features(bars)

    components = [
        grid_component(bars, active_months),
        session_component(active_months),
        onebee_component(active_months),
    ]
    combined = dedupe_trades(pd.concat(components, ignore_index=True))
    selected = apply_day_stop(combined)

    write_outputs(month_features, combined, selected, active_days)

    summary = summarize(selected)
    print(f"Output: {OUTPUT_DIR}")
    print(f"Active months: {int(month_features['active'].sum())}, active days: {active_days}")
    print(f"Trades: {len(selected)}, trades/day: {len(selected) / active_days:.3f}")
    print(
        f"Net: {summary['net_points']:.1f}P, avg: {summary['avg_points']:.3f}P, "
        f"PF: {summary['profit_factor']:.3f}, MDD: {summary['max_drawdown_points']:.1f}P"
    )
    extra03 = summarize(selected, 0.3)
    print(
        f"Extra +0.3P/unit: net {extra03['net_points']:.1f}P, "
        f"PF {extra03['profit_factor']:.3f}"
    )


if __name__ == "__main__":
    main()
