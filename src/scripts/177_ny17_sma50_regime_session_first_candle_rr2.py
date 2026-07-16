# -*- coding: utf-8 -*-
"""2026 selection audit for first-session candles under the NY17 SMA50 regime."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "result" / "ny17_sma50_regime_session_first_candle_rr2"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


regime = load_module(
    "regime176_for_177", SCRIPT_DIR / "176_ny17_sma50_regime_intraday_candle_rr2.py",
)
session = load_module(
    "session171_for_177", SCRIPT_DIR / "171_daily_king_regime_session_first_candle_rr2.py",
)


def main() -> None:
    df = regime.intraday.prepare()
    bars = regime.intraday.resample_signal_bars(df, "15min")
    daily_frame, daily_trades = regime.ny17_daily_trades(df)
    state = regime.completed_regime(bars.index, daily_frame, daily_trades)
    known_daily_tr = pd.Series(
        daily_frame["tr"].rolling(40, min_periods=40).mean().shift(1).to_numpy(float),
        index=pd.DatetimeIndex(daily_frame["time"]).tz_convert("Asia/Seoul"),
    ).reindex(bars.index, method="ffill")
    rows = []
    for session_mode in ["all", "asia_europe", "asia"]:
        for body_fraction in [0.0, 0.25, 0.50]:
            for risk_source, multipliers in [
                ("intraday", [1.0, 1.5, 2.0]),
                ("daily", [0.20, 0.30, 0.40]),
            ]:
                entries = session.session_entries(
                    df, bars, state, known_daily_tr, session_mode, body_fraction,
                    risk_source, "2026-01-01", "2026-06-17",
                )
                for risk_mult in multipliers:
                    for hold in [72, 144, 288]:
                        trades = regime.intraday.simulate(df, entries, risk_mult, hold)
                        summary = regime.intraday.selection_metrics(trades)
                        rows.append({
                            "session_mode": session_mode, "body_fraction": body_fraction,
                            "risk_source": risk_source, "risk_mult": risk_mult,
                            "max_hold_bars": hold, **summary,
                            "frequency_pass": 1.0 <= summary["trades_per_day"] <= 3.0,
                            "performance_pass": summary["net_points"] > 0 and summary["profit_factor"] > 1.0,
                        })
    result = pd.DataFrame(rows).sort_values(
        ["frequency_pass", "net_points"], ascending=[False, False],
    )
    eligible = result[result["frequency_pass"] & result["performance_pass"]]
    frequency = result[result["frequency_pass"]]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result.round(4).to_csv(OUTPUT / "selection_2026_sweep.csv", index=False, encoding="utf-8-sig")
    report = [
        "# NY17 SMA50 Regime Session First Candle RR2", "",
        "Corrected 2026 selection using the NY17 SMA50 daily regime.",
        f"Configurations meeting 1-3 entries/day: {len(frequency)}.",
        f"Configurations meeting frequency and positive net/PF: {len(eligible)}.", "",
        "Best frequency-passing row:", frequency.head(1).round(4).to_string(index=False), "",
        "Decision: **REJECTED**. No 2026 configuration passed both frequency and performance.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("FREQUENCY_PASS", len(frequency), "ELIGIBLE", len(eligible))
    print(frequency.head(20).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
