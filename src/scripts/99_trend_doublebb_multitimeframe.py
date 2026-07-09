# -*- coding: utf-8 -*-
"""Trend-following double Bollinger backtest for 2m/5m/10m/15m XAUUSD.

Strategy idea:
- BB20/2 on close is the trend/structure band.
- BB4/4 on open is the pullback timing band.
- Trade only in the direction of a 20/120 SMA trend filter.
- Enter on the next bar open after a trend-side pullback touches BB4/4.
- Resolve same-bar stop/target conservatively: stop first.

This script is a research baseline for the user's 2/5/10/15 minute objective.
It intentionally avoids grid averaging and same-candle path optimism.
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
OUTPUT_DIR = ROOT / "result" / "trend_doublebb_multitimeframe_201001_202606"

TFS = ["2m", "5m", "10m", "15m"]
ENTRY_START_MINUTE = 8 * 60 + 30
ENTRY_END_MINUTE = 23 * 60 + 30
COST_POINTS = 0.50
ATR_LEN = 14
SMA_FAST = 20
SMA_SLOW = 120
SLOPE_LOOKBACK = 20
MAX_HOLD_BARS = {
    "2m": 180,
    "5m": 96,
    "10m": 60,
    "15m": 48,
}


def quiet_call(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def resample_15m_from_1m() -> pd.DataFrame:
    path = DATA_DIR / "xauusd_1m_2010-01-01_2026-06-16.csv"
    one = quiet_call(prep.load_gold_data, path, timeframe="1m")
    out = one.resample("15min", label="left", closed="left").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })
    out = out.dropna(subset=["open", "high", "low", "close"]).copy()
    out.attrs["timeframe"] = "15m"
    out.attrs["source_file"] = str(path)
    return out


def load_tf(tf: str) -> pd.DataFrame:
    if tf == "15m":
        df = resample_15m_from_1m()
    else:
        path = DATA_DIR / ("xauusd_%s_2010-01-01_2026-06-16.csv" % tf)
        df = quiet_call(prep.load_gold_data, path, timeframe=tf)
    df = prep.assign_session(df)
    df = prep.add_bollinger_bands(df, ddof=0)
    df = add_indicators(df)
    df.attrs["timeframe"] = tf
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["sma20"] = out["close"].rolling(SMA_FAST, min_periods=SMA_FAST).mean()
    out["sma120"] = out["close"].rolling(SMA_SLOW, min_periods=SMA_SLOW).mean()
    out["sma120_slope"] = out["sma120"] - out["sma120"].shift(SLOPE_LOOKBACK)
    out["bb20_mid_slope"] = out["bb20_2_mid_close"] - out["bb20_2_mid_close"].shift(SLOPE_LOOKBACK)

    prev_close = out["close"].shift(1)
    tr = pd.concat([
        out["high"] - out["low"],
        (out["high"] - prev_close).abs(),
        (out["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(ATR_LEN, min_periods=ATR_LEN).mean()
    out["bb20_width"] = out["bb20_2_upper_close"] - out["bb20_2_lower_close"]
    return out


def entry_time_allowed(ts: pd.Timestamp) -> bool:
    kst = ts.tz_convert("Asia/Seoul") if ts.tzinfo is not None else ts.tz_localize("Asia/Seoul")
    minute = kst.hour * 60 + kst.minute
    return ENTRY_START_MINUTE <= minute < ENTRY_END_MINUTE


def build_signals(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    out = df.copy()
    trend_long = (
        (out["sma20"] > out["sma120"])
        & (out["close"] > out["sma120"])
        & (out["sma120_slope"] > 0)
        & (out["bb20_mid_slope"] > 0)
    )
    trend_short = (
        (out["sma20"] < out["sma120"])
        & (out["close"] < out["sma120"])
        & (out["sma120_slope"] < 0)
        & (out["bb20_mid_slope"] < 0)
    )
    out["long_signal"] = (
        trend_long
        & (out["low"] <= out["bb4_4_lower_open"])
        & (out["close"] >= out["bb20_2_mid_close"])
        & (out["atr14"] > 0)
    ).fillna(False)
    out["short_signal"] = (
        trend_short
        & (out["high"] >= out["bb4_4_upper_open"])
        & (out["close"] <= out["bb20_2_mid_close"])
        & (out["atr14"] > 0)
    ).fillna(False)
    out.attrs["timeframe"] = tf
    return out


def make_trade(df: pd.DataFrame, tf: str, signal_pos: int, direction: str) -> dict | None:
    entry_pos = signal_pos + 1
    if entry_pos >= len(df):
        return None
    idx = df.index
    if not entry_time_allowed(idx[entry_pos]):
        return None

    row = df.iloc[signal_pos]
    entry = float(df["open"].iloc[entry_pos])
    atr = float(row["atr14"])
    width = float(row["bb20_width"])
    if not math.isfinite(atr) or atr <= 0:
        return None

    stop_dist = max(0.8 * atr, 0.18 * width, 5.0)
    target_dist = 1.6 * stop_dist
    if direction == "long":
        stop = entry - stop_dist
        target = entry + target_dist
    else:
        stop = entry + stop_dist
        target = entry - target_dist

    end_pos = min(len(df) - 1, entry_pos + MAX_HOLD_BARS[tf])
    exit_price = float(df["close"].iloc[end_pos])
    exit_time = idx[end_pos]
    exit_reason = "time_exit"
    mfe = 0.0
    mae = 0.0

    for pos in range(entry_pos, end_pos + 1):
        high = float(df["high"].iloc[pos])
        low = float(df["low"].iloc[pos])
        close = float(df["close"].iloc[pos])
        if direction == "long":
            mfe = max(mfe, high - entry)
            mae = max(mae, entry - low)
            if low <= stop:
                exit_price = stop
                exit_time = idx[pos]
                exit_reason = "stop"
                break
            if high >= target:
                exit_price = target
                exit_time = idx[pos]
                exit_reason = "target_1_6r"
                break
            if close < float(df["sma20"].iloc[pos]):
                exit_price = close
                exit_time = idx[pos]
                exit_reason = "sma20_close"
                break
        else:
            mfe = max(mfe, entry - low)
            mae = max(mae, high - entry)
            if high >= stop:
                exit_price = stop
                exit_time = idx[pos]
                exit_reason = "stop"
                break
            if low <= target:
                exit_price = target
                exit_time = idx[pos]
                exit_reason = "target_1_6r"
                break
            if close > float(df["sma20"].iloc[pos]):
                exit_price = close
                exit_time = idx[pos]
                exit_reason = "sma20_close"
                break

    gross = exit_price - entry if direction == "long" else entry - exit_price
    net = gross - COST_POINTS
    return {
        "tf": tf,
        "direction": direction,
        "signal_time": idx[signal_pos],
        "entry_time": idx[entry_pos],
        "exit_time": exit_time,
        "entry_price": entry,
        "exit_price": exit_price,
        "stop_price": stop,
        "target_price": target,
        "stop_dist": stop_dist,
        "target_dist": target_dist,
        "exit_reason": exit_reason,
        "gross_points": gross,
        "net_points": net,
        "r_multiple": net / stop_dist,
        "mfe_points": mfe,
        "mae_points": mae,
        "hold_bars": int(idx.searchsorted(exit_time) - entry_pos + 1),
        "session": str(df["session"].iloc[entry_pos]),
        "year": int(idx[entry_pos].year),
        "month": idx[entry_pos].strftime("%Y-%m"),
    }


def run_tf(tf: str) -> pd.DataFrame:
    df = build_signals(load_tf(tf), tf)
    rows = []
    next_allowed_pos = 0
    long_flags = df["long_signal"].to_numpy(dtype=bool)
    short_flags = df["short_signal"].to_numpy(dtype=bool)
    for pos in range(len(df) - 1):
        if pos < next_allowed_pos:
            continue
        direction = "long" if long_flags[pos] else "short" if short_flags[pos] else None
        if direction is None:
            continue
        trade = make_trade(df, tf, pos, direction)
        if trade is None:
            continue
        rows.append(trade)
        next_allowed_pos = int(df.index.searchsorted(trade["exit_time"])) + 1
    return pd.DataFrame(rows)


def profit_factor(pnl: pd.Series) -> float:
    vals = pd.to_numeric(pnl, errors="coerce").fillna(0.0)
    gp = vals[vals > 0].sum()
    gl = abs(vals[vals < 0].sum())
    if gl == 0:
        return math.inf if gp > 0 else 0.0
    return float(gp / gl)


def max_drawdown(pnl: pd.Series) -> float:
    vals = pd.to_numeric(pnl, errors="coerce").fillna(0.0)
    eq = vals.cumsum()
    dd = eq.cummax() - eq
    return float(dd.max()) if len(vals) else 0.0


def summarize_group(group: pd.DataFrame) -> dict:
    pnl = group["net_points"].astype(float)
    days = pd.DatetimeIndex(group["entry_time"]).tz_convert("Asia/Seoul").date
    active_days = len(set(days))
    return {
        "trades": int(len(group)),
        "active_days": int(active_days),
        "trades_per_active_day": float(len(group) / active_days) if active_days else 0.0,
        "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
        "avg_points": float(pnl.mean()) if len(pnl) else 0.0,
        "net_points": float(pnl.sum()) if len(pnl) else 0.0,
        "profit_factor": profit_factor(pnl),
        "max_drawdown_points": max_drawdown(pnl),
        "avg_r": float(group["r_multiple"].mean()) if len(group) else 0.0,
        "target_rate": float((group["exit_reason"] == "target_1_6r").mean()) if len(group) else 0.0,
        "stop_rate": float((group["exit_reason"] == "stop").mean()) if len(group) else 0.0,
    }


def summarize(trades: pd.DataFrame):
    by_tf = []
    by_tf_dir = []
    yearly = []
    monthly = []
    exits = []

    for tf, group in trades.groupby("tf", sort=True):
        row = {"tf": tf}
        row.update(summarize_group(group))
        by_tf.append(row)
    for key, group in trades.groupby(["tf", "direction"], sort=True):
        row = {"tf": key[0], "direction": key[1]}
        row.update(summarize_group(group))
        by_tf_dir.append(row)
    for key, group in trades.groupby(["tf", "year"], sort=True):
        row = {"tf": key[0], "year": int(key[1])}
        row.update(summarize_group(group))
        yearly.append(row)
    for key, group in trades.groupby(["tf", "month"], sort=True):
        row = {"tf": key[0], "month": key[1]}
        row.update(summarize_group(group))
        monthly.append(row)
    for key, group in trades.groupby(["tf", "exit_reason"], sort=True):
        row = {"tf": key[0], "exit_reason": key[1]}
        row.update(summarize_group(group))
        exits.append(row)

    return tuple(round_floats(pd.DataFrame(x)) for x in (by_tf, by_tf_dir, yearly, monthly, exits))


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


def table_html(df: pd.DataFrame, title: str, max_rows: int | None = None) -> str:
    show = df.head(max_rows) if max_rows else df
    headers = "".join("<th>%s</th>" % c for c in show.columns)
    body = []
    for _, row in show.iterrows():
        cells = []
        for col, val in row.items():
            cls = ""
            if col in {"net_points", "avg_points", "profit_factor", "avg_r"}:
                try:
                    num = float(val)
                    cls = "pos" if (num >= 1 if col == "profit_factor" else num > 0) else "neg"
                except Exception:
                    pass
            if pd.isna(val):
                text = ""
            elif isinstance(val, float):
                text = "%.4f" % val
            else:
                text = str(val)
            cells.append("<td class='%s'>%s</td>" % (cls, text))
        body.append("<tr>%s</tr>" % "".join(cells))
    return "<section><h2>%s</h2><div><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></section>" % (
        title,
        headers,
        "".join(body),
    )


def write_html(by_tf, by_tf_dir, yearly, monthly, exits):
    css = """
    body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f7f8fb;color:#1d2733}
    header{background:#18202b;color:#fff;padding:28px 42px}h1{font-size:26px;margin:0 0 8px}p{margin:0;color:#c8d2df}
    main{max-width:1800px;margin:0 auto;padding:22px 42px 48px}section{background:#fff;border:1px solid #dce2ea;border-radius:8px;margin:16px 0;padding:16px}
    h2{font-size:18px;margin:0 0 10px}div{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
    th,td{border-bottom:1px solid #e0e5ec;padding:7px 9px;text-align:right;white-space:nowrap}th{background:#eef2f6}
    td:first-child,th:first-child{text-align:left}.pos{color:#087f5b;font-weight:700;background:#e9f7f0}.neg{color:#c92a2a;font-weight:700;background:#fff0f0}
    """
    html = """<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>Trend DoubleBB Multi-Timeframe</title><style>%s</style></head>
<body><header><h1>Trend DoubleBB Multi-Timeframe Baseline</h1><p>BB20/2 close + BB4/4 open, 20/120 SMA trend filter, 2m/5m/10m/15m, cost 0.5P, stop-first same-bar rule.</p></header><main>
%s%s%s%s%s
</main></body></html>""" % (
        css,
        table_html(by_tf.sort_values("net_points", ascending=False), "Timeframe Summary"),
        table_html(by_tf_dir.sort_values("net_points", ascending=False), "Timeframe Direction Summary"),
        table_html(yearly.sort_values(["tf", "year"]), "Yearly Report"),
        table_html(monthly.sort_values(["tf", "month"]), "Monthly Report"),
        table_html(exits.sort_values(["tf", "exit_reason"]), "Exit Report"),
    )
    (OUTPUT_DIR / "trend_doublebb_multitimeframe_report.html").write_text(html, encoding="utf-8")


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_trades = []
    for tf in TFS:
        print("RUN", tf)
        trades = run_tf(tf)
        print(tf, "trades", len(trades))
        all_trades.append(trades)
    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    by_tf, by_tf_dir, yearly, monthly, exits = summarize(trades)

    trades.to_csv(OUTPUT_DIR / "trend_doublebb_multitimeframe_trades.csv", index=False, encoding="utf-8-sig")
    by_tf.to_csv(OUTPUT_DIR / "trend_doublebb_by_tf.csv", index=False, encoding="utf-8-sig")
    by_tf_dir.to_csv(OUTPUT_DIR / "trend_doublebb_by_tf_direction.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "trend_doublebb_yearly.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "trend_doublebb_monthly.csv", index=False, encoding="utf-8-sig")
    exits.to_csv(OUTPUT_DIR / "trend_doublebb_exits.csv", index=False, encoding="utf-8-sig")
    write_html(by_tf, by_tf_dir, yearly, monthly, exits)

    print("")
    print("=== TREND DOUBLEBB MULTI-TIMEFRAME ===")
    print(by_tf.sort_values("net_points", ascending=False).to_string(index=False))
    print("WROTE:", OUTPUT_DIR)


if __name__ == "__main__":
    run()
