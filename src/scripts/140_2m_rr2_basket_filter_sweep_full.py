# -*- coding: utf-8 -*-
"""Search long-history regime filters for the fixed RR2 reversal basket."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
BASE = SCRIPT_DIR / "125_2m_rr2_reversal_basket.py"
spec = importlib.util.spec_from_file_location("base125_for_140", BASE)
base = importlib.util.module_from_spec(spec)
sys.modules["base125_for_140"] = base
assert spec.loader is not None
spec.loader.exec_module(base)

OUTPUT = ROOT / "result" / "rr2_basket_filter_sweep_full"
TRADING_DAYS = 5125
DAILY_CAP = 3


def pf(pnl: pd.Series) -> float:
    gain = pnl[pnl > 0].sum()
    loss = abs(pnl[pnl < 0].sum())
    return float(gain / loss) if loss else (math.inf if gain else 0.0)


def dd(pnl: pd.Series) -> float:
    equity = pnl.cumsum()
    return float((equity.cummax() - equity).max()) if len(equity) else 0.0


def daily_cap(trades: pd.DataFrame) -> pd.DataFrame:
    return trades.sort_values("entry_time").groupby("day", sort=False).head(DAILY_CAP).sort_values("entry_time").reset_index(drop=True)


def evaluate(name: str, trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"filter": name, "trades": 0, "trades_per_day": 0.0, "net_points": 0.0, "profit_factor": 0.0, "max_drawdown_points": 0.0}
    pnl = pd.to_numeric(trades["net_points"], errors="coerce").fillna(0.0)
    return {
        "filter": name,
        "trades": len(trades),
        "active_days": trades["day"].nunique(),
        "trades_per_day": len(trades) / TRADING_DAYS,
        "net_points": pnl.sum(),
        "avg_points": pnl.mean(),
        "profit_factor": pf(pnl),
        "win_rate": (pnl > 0).mean() * 100,
        "target_rate": (trades["exit_reason"] == "target_2r").mean() * 100,
        "max_drawdown_points": dd(pnl),
        "positive_year_rate": (trades.groupby("year")["net_points"].sum() > 0).mean() * 100,
        "positive_month_rate": (trades.groupby("month")["net_points"].sum() > 0).mean() * 100,
    }


def main() -> None:
    features = base.daily_features()
    immediate = base.add_regime(base.load_component(base.IMMEDIATE_INPUT, "immediate_sweep"), features)
    or_failed = base.add_regime(base.load_component(base.OR_FAILED_INPUT, "or_failed"), features)
    pdh = base.add_regime(base.load_component(base.PDH_PDL_INPUT, "pdh_pdl_double"), features)
    immediate = immediate[pd.to_numeric(immediate["risk_points"], errors="coerce") >= 2.0]
    or_failed = or_failed[pd.to_numeric(or_failed["risk_points"], errors="coerce") >= 1.5]
    raw = pd.concat([immediate, or_failed, pdh], ignore_index=True)
    base_trades = base.apply_portfolio_cap(base.dedupe(raw), base.PORTFOLIO_CAP)
    base_trades = daily_cap(base_trades)

    sessions = ["all"] + sorted(base_trades["session"].dropna().astype(str).unique().tolist())
    directions = ["all", "long", "short"]
    regimes = [
        ("all", lambda d: pd.Series(True, index=d.index)),
        ("ret20_pos", lambda d: d["ret20"] > 0),
        ("ret20_neg", lambda d: d["ret20"] < 0),
        ("ret60_pos", lambda d: d["ret60"] > 0),
        ("ret60_neg", lambda d: d["ret60"] < 0),
        ("trend_follow", lambda d: ((d["direction"] == "long") & (d["ret60"] > 0)) | ((d["direction"] == "short") & (d["ret60"] < 0))),
        ("trend_fade", lambda d: ((d["direction"] == "long") & (d["ret60"] < 0)) | ((d["direction"] == "short") & (d["ret60"] > 0))),
    ]
    adr_filters = [
        ("adr_all", lambda d: pd.Series(True, index=d.index)),
        ("adr_ge_10", lambda d: d["adr60"] >= 10),
        ("adr_ge_20", lambda d: d["adr60"] >= 20),
        ("adr_ge_30", lambda d: d["adr60"] >= 30),
        ("adr_ge_40", lambda d: d["adr60"] >= 40),
    ]
    rows = []
    for session in sessions:
        for direction in directions:
            for regime_name, regime_fn in regimes:
                for adr_name, adr_fn in adr_filters:
                    mask = pd.Series(True, index=base_trades.index)
                    if session != "all":
                        mask &= base_trades["session"].astype(str).eq(session)
                    if direction != "all":
                        mask &= base_trades["direction"].eq(direction)
                    mask &= regime_fn(base_trades).fillna(False)
                    mask &= adr_fn(base_trades).fillna(False)
                    filtered = base_trades.loc[mask].copy()
                    rows.append(evaluate(f"session={session};direction={direction};regime={regime_name};{adr_name}", filtered))
    summary = pd.DataFrame(rows).sort_values(["profit_factor", "net_points"], ascending=False)
    eligible = summary[(summary["trades_per_day"] >= 0.5) & (summary["trades_per_day"] <= 3.0)]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary.round(4).to_csv(OUTPUT / "all_filters.csv", index=False, encoding="utf-8-sig")
    eligible.head(100).round(4).to_csv(OUTPUT / "eligible_filters.csv", index=False, encoding="utf-8-sig")
    print("BASE", evaluate("base", base_trades))
    print("TOP PF 0.5-3/day")
    print(eligible.head(30).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
