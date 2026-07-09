# -*- coding: utf-8 -*-
"""97 - XAUUSD session 15m opening-range breakout retest strategy.

Rule draft from user:
  1. For each session, mark the first 15 minutes high/low.
  2. Wait for a candle close outside that high/low.
  3. Enter when price retests the broken level.
  4. Stop at the opposite side of the 15m range, target at 2R.
  5. Up to 3 trades per day = one trade per Asia/Europe/NewYork session.

Default data/timeframe:
  15m bars resampled from the 5m source file.

Run from repo root:
  py src/scripts/97_strategy_session_15m_range_retest_once.py

Or from data/:
  python ../src/scripts/97_strategy_session_15m_range_retest_once.py

Console output is ASCII-only. HTML/CSV outputs are UTF-8.
"""
from __future__ import annotations

import bisect
import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


KST = timezone(timedelta(hours=9))
BAR_SECONDS_BY_TF = {"1m": 60, "2m": 120, "5m": 300, "10m": 600, "15m": 900}

TF = os.environ.get("TF", "15m")
TEST_START = os.environ.get("TEST_START", "2026-01-01")
TEST_END = os.environ.get("TEST_END", "2026-06-16 23:59:59")
COST_POINTS = float(os.environ.get("COST_POINTS", "0.5"))
RISK_REWARD = float(os.environ.get("RISK_REWARD", "2.0"))
ENTRY_ON_NEXT_OPEN = os.environ.get("ENTRY_ON_NEXT_OPEN", "1") != "0"
ALLOW_OVERLAP = os.environ.get("ALLOW_OVERLAP", "0") == "1"
BREAKOUT_BODY_RATIO_MIN = float(os.environ.get("BREAKOUT_BODY_RATIO_MIN", "0.0"))

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RESULT_DIR = Path(__file__).resolve().parents[2] / "result"
SOURCE_TF = "5m" if TF == "15m" else TF
DATA_FILE = DATA_DIR / ("xauusd_%s_2010-01-01_2026-06-16.csv" % SOURCE_TF)

PERIOD_TAG = TEST_START[:10].replace("-", "") + "_" + TEST_END[:10].replace("-", "")
BODY_TAG = "body%03d" % int(round(BREAKOUT_BODY_RATIO_MIN * 100))
OUT_DIR = RESULT_DIR / ("strategy_session_15m_range_retest_once_%s_%s_%s" % (TF, PERIOD_TAG, BODY_TAG))
TRADES_FILE = OUT_DIR / "trades.csv"
SUMMARY_FILE = OUT_DIR / "summary.json"
REPORT_FILE = OUT_DIR / "report.html"


@dataclass
class Bar:
    epoch: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class SessionWindow:
    sid: int
    name: str
    reset_epoch: int
    range_end_epoch: int
    next_reset_epoch: int


def parse_kst(value: str) -> int:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return int(dt.astimezone(timezone.utc).timestamp())


def kst_dt(epoch: int) -> datetime:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).astimezone(KST)


def fmt_kst(epoch: int) -> str:
    return kst_dt(epoch).strftime("%Y-%m-%d %H:%M")


def kst_day(epoch: int) -> date:
    return kst_dt(epoch).date()


def kst_fixed_epoch(day: date, hour: int, minute: int) -> int:
    dt = datetime.combine(day, dtime(hour, minute), tzinfo=KST)
    return int(dt.astimezone(timezone.utc).timestamp())


def local_reset_epoch(day: date, tz_name: str, hour: int, minute: int) -> int:
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(tz_name))
    return int(local.astimezone(timezone.utc).timestamp())


def daterange(start_day: date, end_day: date):
    cur = start_day
    while cur <= end_day:
        yield cur
        cur += timedelta(days=1)


def load_bars(path: Path, start_epoch: int, end_epoch: int) -> list[Bar]:
    bars: list[Bar] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        rd = csv.reader(fp)
        header = next(rd)
        for row in rd:
            epoch = int(float(row[0]))
            if epoch > 100000000000:
                epoch //= 1000
            if epoch < start_epoch or epoch > end_epoch:
                continue
            vol = float(row[5]) if len(row) > 5 and row[5] != "" else 0.0
            bars.append(Bar(epoch, float(row[1]), float(row[2]), float(row[3]), float(row[4]), vol))
    return bars


def resample_bars(bars: list[Bar], target_seconds: int) -> list[Bar]:
    if not bars:
        return []
    groups = {}
    order = []
    for bar in bars:
        bucket = (bar.epoch // target_seconds) * target_seconds
        if bucket not in groups:
            groups[bucket] = []
            order.append(bucket)
        groups[bucket].append(bar)
    out = []
    for bucket in order:
        items = groups[bucket]
        out.append(Bar(
            epoch=bucket,
            open=items[0].open,
            high=max(b.high for b in items),
            low=min(b.low for b in items),
            close=items[-1].close,
            volume=sum(b.volume for b in items),
        ))
    return out


def build_session_windows(first_epoch: int, last_epoch: int, bar_seconds: int) -> list[SessionWindow]:
    start_day = kst_day(first_epoch) - timedelta(days=2)
    end_day = kst_day(last_epoch) + timedelta(days=2)
    resets = []
    for day in daterange(start_day, end_day):
        resets.append((kst_fixed_epoch(day, 8, 30), "Asia"))
        resets.append((local_reset_epoch(day, "Europe/London", 8, 0), "Europe"))
        resets.append((local_reset_epoch(day, "America/New_York", 9, 30), "NewYork"))
    resets = sorted(set(resets))
    out: list[SessionWindow] = []
    sid = 0
    for i in range(len(resets) - 1):
        reset_epoch, name = resets[i]
        next_reset_epoch = resets[i + 1][0]
        if reset_epoch < first_epoch or reset_epoch > last_epoch:
            continue
        sid += 1
        out.append(SessionWindow(
            sid=sid,
            name=name,
            reset_epoch=int(reset_epoch),
            range_end_epoch=int(reset_epoch + 15 * 60),
            next_reset_epoch=int(next_reset_epoch),
        ))
    return out


def opening_range(bars: list[Bar], epochs: list[int], session: SessionWindow):
    start_i = bisect.bisect_left(epochs, session.reset_epoch)
    end_i = bisect.bisect_left(epochs, session.range_end_epoch)
    window = bars[start_i:end_i]
    if not window:
        return None
    # Require the full first 15 minutes to avoid partial-session ranges.
    expected = max(1, (15 * 60) // BAR_SECONDS_BY_TF.get(TF, 300))
    if len(window) < expected:
        return None
    # For TF=15m this is exactly the first completed 15m candle.
    return {
        "start_i": start_i,
        "end_i": end_i,
        "range_high": max(b.high for b in window),
        "range_low": min(b.low for b in window),
        "range_points": max(b.high for b in window) - min(b.low for b in window),
    }


def candle_body_ratio(bar: Bar) -> float:
    candle_range = bar.high - bar.low
    if candle_range <= 0:
        return 0.0
    return abs(bar.close - bar.open) / candle_range


def find_breakout(bars: list[Bar], start_i: int, end_i: int, range_high: float, range_low: float):
    low_body_breakouts = 0
    for i in range(start_i, end_i):
        b = bars[i]
        long_break = b.close > range_high
        short_break = b.close < range_low
        if long_break and short_break:
            # TODO: This is practically impossible with a valid range. Keep explicit for audit clarity.
            return None, low_body_breakouts
        if long_break or short_break:
            ratio = candle_body_ratio(b)
            if ratio < BREAKOUT_BODY_RATIO_MIN:
                low_body_breakouts += 1
                continue
        if long_break:
            return (i, "long", range_high, candle_body_ratio(b)), low_body_breakouts
        if short_break:
            return (i, "short", range_low, candle_body_ratio(b)), low_body_breakouts
    return None, low_body_breakouts


def find_retest(bars: list[Bar], start_i: int, end_i: int, direction: str, level: float):
    for i in range(start_i, end_i):
        b = bars[i]
        if direction == "long" and b.low <= level:
            return i
        if direction == "short" and b.high >= level:
            return i
    return None


def resolve_exit(bars: list[Bar], start_i: int, direction: str, stop: float, target: float):
    for i in range(start_i, len(bars)):
        b = bars[i]
        if direction == "long":
            stop_hit = b.low <= stop
            target_hit = b.high >= target
        else:
            stop_hit = b.high >= stop
            target_hit = b.low <= target
        if stop_hit and target_hit:
            return i, stop, "SL_same_bar"
        if stop_hit:
            return i, stop, "SL"
        if target_hit:
            return i, target, "TP"
    return len(bars) - 1, bars[-1].close, "FINAL"


def close_trade(session, bars, open_range, breakout_i, retest_i, entry_i, exit_i, direction, level, body_ratio, entry, stop, target, exit_price, reason):
    sign = 1 if direction == "long" else -1
    gross_points = (exit_price - entry) * sign
    net_points = gross_points - COST_POINTS
    risk_points = abs(entry - stop)
    return {
        "session_id": session.sid,
        "session": session.name,
        "date_kst": str(kst_day(session.reset_epoch)),
        "direction": direction,
        "session_start_kst": fmt_kst(session.reset_epoch),
        "range_start_kst": fmt_kst(session.reset_epoch),
        "range_end_kst": fmt_kst(session.range_end_epoch),
        "breakout_time": fmt_kst(bars[breakout_i].epoch),
        "retest_time": fmt_kst(bars[retest_i].epoch),
        "entry_time": fmt_kst(bars[entry_i].epoch),
        "exit_time": fmt_kst(bars[exit_i].epoch),
        "range_high": open_range["range_high"],
        "range_low": open_range["range_low"],
        "range_points": open_range["range_points"],
        "breakout_level": level,
        "breakout_body_ratio": body_ratio,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "exit_price": exit_price,
        "risk_points": risk_points,
        "gross_points": gross_points,
        "cost_points": COST_POINTS,
        "net_points": net_points,
        "r_net": net_points / risk_points if risk_points > 0 else math.nan,
        "hold_bars": exit_i - entry_i + 1,
        "exit_reason": reason,
        "breakout_epoch": bars[breakout_i].epoch,
        "retest_epoch": bars[retest_i].epoch,
        "entry_epoch": bars[entry_i].epoch,
        "exit_epoch": bars[exit_i].epoch,
    }


def backtest(bars: list[Bar], sessions: list[SessionWindow]):
    epochs = [b.epoch for b in bars]
    trades = []
    meta = {
        "sessions": 0,
        "missing_range": 0,
        "invalid_range": 0,
        "no_breakout": 0,
        "no_retest": 0,
        "bad_risk": 0,
        "busy_session": 0,
        "low_body_breakouts": 0,
        "trades": 0,
    }
    traded_sessions_by_day = {}
    busy_until_epoch = -1
    for session in sessions:
        meta["sessions"] += 1
        if not ALLOW_OVERLAP and session.reset_epoch <= busy_until_epoch:
            meta["busy_session"] += 1
            continue
        day = kst_day(session.reset_epoch)
        traded_sessions_by_day.setdefault(day, 0)
        if traded_sessions_by_day[day] >= 3:
            continue
        open_range = opening_range(bars, epochs, session)
        if open_range is None:
            meta["missing_range"] += 1
            continue
        if open_range["range_points"] <= 0:
            meta["invalid_range"] += 1
            continue

        scan_start = open_range["end_i"]
        scan_end = bisect.bisect_left(epochs, session.next_reset_epoch)
        breakout, low_body_breakouts = find_breakout(
            bars,
            scan_start,
            scan_end,
            open_range["range_high"],
            open_range["range_low"],
        )
        meta["low_body_breakouts"] += low_body_breakouts
        if breakout is None:
            meta["no_breakout"] += 1
            continue
        breakout_i, direction, level, body_ratio = breakout

        retest_i = find_retest(bars, breakout_i + 1, scan_end, direction, level)
        if retest_i is None:
            meta["no_retest"] += 1
            continue

        entry_i = retest_i + 1 if ENTRY_ON_NEXT_OPEN else retest_i
        if entry_i >= len(bars) or bars[entry_i].epoch >= session.next_reset_epoch:
            meta["no_retest"] += 1
            continue
        entry = bars[entry_i].open if ENTRY_ON_NEXT_OPEN else level

        if direction == "long":
            stop = open_range["range_low"]
            risk = entry - stop
            target = entry + RISK_REWARD * risk
        else:
            stop = open_range["range_high"]
            risk = stop - entry
            target = entry - RISK_REWARD * risk
        if risk <= 0:
            meta["bad_risk"] += 1
            continue

        exit_i, exit_price, reason = resolve_exit(bars, entry_i, direction, stop, target)
        trades.append(close_trade(
            session,
            bars,
            open_range,
            breakout_i,
            retest_i,
            entry_i,
            exit_i,
            direction,
            level,
            body_ratio,
            entry,
            stop,
            target,
            exit_price,
            reason,
        ))
        busy_until_epoch = bars[exit_i].epoch
        traded_sessions_by_day[day] += 1
        meta["trades"] += 1
    return trades, meta


def profit_factor(values):
    gp = sum(v for v in values if v > 0)
    gl = -sum(v for v in values if v < 0)
    if gl == 0:
        return math.inf if gp > 0 else 0.0
    return gp / gl


def max_drawdown(values):
    total = 0.0
    peak = 0.0
    mdd = 0.0
    for v in values:
        total += v
        peak = max(peak, total)
        mdd = max(mdd, peak - total)
    return mdd


def summarize(rows):
    vals = [float(r["net_points"]) for r in rows]
    rvals = [float(r["r_net"]) for r in rows if not math.isnan(float(r["r_net"]))]
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v < 0]
    pf = profit_factor(vals)
    return {
        "trades": len(rows),
        "win_rate": round(100 * len(wins) / len(vals), 3) if vals else 0.0,
        "expectancy_points": round(sum(vals) / len(vals), 3) if vals else 0.0,
        "expectancy_r": round(sum(rvals) / len(rvals), 3) if rvals else 0.0,
        "profit_factor": "inf" if pf == math.inf else round(pf, 3),
        "cumulative_points": round(sum(vals), 3),
        "max_drawdown_points": round(max_drawdown(vals), 3),
        "avg_win_points": round(sum(wins) / len(wins), 3) if wins else 0.0,
        "avg_loss_points": round(sum(losses) / len(losses), 3) if losses else 0.0,
    }


def group_summary(rows, key):
    groups = {}
    for row in rows:
        groups.setdefault(row[key], []).append(row)
    out = []
    for name in sorted(groups):
        summary = summarize(groups[name])
        summary[key] = name
        out.append(summary)
    return out


def write_csv(path: Path, rows):
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        wr = csv.DictWriter(fp, fieldnames=fields)
        wr.writeheader()
        for row in rows:
            wr.writerow(row)


def esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def html_table(rows, first_key):
    if not rows:
        return "<p>No rows.</p>"
    cols = [
        first_key,
        "trades",
        "win_rate",
        "expectancy_points",
        "expectancy_r",
        "profit_factor",
        "cumulative_points",
        "max_drawdown_points",
    ]
    head = "".join("<th>%s</th>" % esc(c) for c in cols)
    body = []
    for row in rows:
        body.append("<tr>" + "".join("<td>%s</td>" % esc(row.get(c, "")) for c in cols) + "</tr>")
    return "<table><tr>%s</tr>%s</table>" % (head, "".join(body))


def trade_table(rows, limit=300):
    cols = [
        "date_kst",
        "session",
        "direction",
        "breakout_time",
        "retest_time",
        "entry_time",
        "exit_time",
        "entry_price",
        "stop_price",
        "target_price",
        "breakout_body_ratio",
        "net_points",
        "r_net",
        "exit_reason",
    ]
    head = "".join("<th>%s</th>" % esc(c) for c in cols)
    body = []
    for row in rows[:limit]:
        body.append("<tr>" + "".join("<td>%s</td>" % esc(row.get(c, "")) for c in cols) + "</tr>")
    return "<table><tr>%s</tr>%s</table>" % (head, "".join(body))


def equity_svg(rows, width=1000, height=260):
    vals = [0.0]
    total = 0.0
    for row in rows:
        total += float(row["net_points"])
        vals.append(total)
    if not vals:
        vals = [0.0]
    vmin, vmax = min(vals), max(vals)
    if vmin == vmax:
        vmax = vmin + 1.0
    pad = 14
    points = []
    for i, value in enumerate(vals):
        x = pad + (width - 2 * pad) * i / max(1, len(vals) - 1)
        y = pad + (height - 2 * pad) * (1 - (value - vmin) / (vmax - vmin))
        points.append("%.1f,%.1f" % (x, y))
    return (
        '<svg viewBox="0 0 %d %d"><rect width="%d" height="%d" fill="#fff"/>'
        '<polyline fill="none" stroke="#1f5eff" stroke-width="2" points="%s"/></svg>'
    ) % (width, height, width, height, " ".join(points))


def write_report(path: Path, trades, meta, report):
    overall = report["overall"]
    html = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>Session 15m Range Retest Once</title>
<style>
body{font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;margin:24px;background:#f7f8fb;color:#172033}
h1{font-size:24px}h2{font-size:18px;margin-top:26px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.card{background:white;border:1px solid #d8dee8;border-radius:8px;padding:12px}.k{font-size:12px;color:#667085}.v{font-size:22px;font-weight:700}
table{border-collapse:collapse;background:white;font-size:13px;margin-top:8px;width:100%%}
th,td{border:1px solid #d8dee8;padding:7px;text-align:right}th{background:#eef1f6}td:first-child,th:first-child{text-align:left}
.note{background:#eef4ff;border-left:4px solid #1f5eff;padding:10px 12px;border-radius:6px}
</style></head><body>
<h1>XAUUSD %s 세션 첫 15분 범위 돌파 리테스트</h1>
<p class="note">가정: Asia 08:30 KST, Europe 08:00 London, NewYork 09:30 New York 시작. 각 세션 첫 15분의 고가/저가를 범위로 삼고, 종가가 범위 밖에서 마감한 뒤 깨진 레벨을 리테스트하면 다음 봉 시가에 진입합니다. 손절은 범위 반대편, 익절은 2R, 하루 최대 3회입니다. 같은 봉에서 손절/익절이 모두 닿으면 손절 우선입니다.</p>
<div class="grid">
<div class="card"><div class="k">Trades</div><div class="v">%s</div></div>
<div class="card"><div class="k">Win Rate</div><div class="v">%s%%</div></div>
<div class="card"><div class="k">Expectancy</div><div class="v">%sP</div></div>
<div class="card"><div class="k">Expectancy R</div><div class="v">%sR</div></div>
<div class="card"><div class="k">PF</div><div class="v">%s</div></div>
<div class="card"><div class="k">Cum PnL</div><div class="v">%sP</div></div>
<div class="card"><div class="k">Max DD</div><div class="v">%sP</div></div>
<div class="card"><div class="k">Cost</div><div class="v">%sP</div></div>
</div>
<h2>Equity</h2>%s
<h2>Session</h2>%s
<h2>Direction</h2>%s
<h2>Year</h2>%s
<h2>Exit Reason</h2>%s
<h2>Meta</h2><pre>%s</pre>
<h2>Trades</h2>%s
</body></html>""" % (
        TF,
        overall["trades"],
        overall["win_rate"],
        overall["expectancy_points"],
        overall["expectancy_r"],
        overall["profit_factor"],
        overall["cumulative_points"],
        overall["max_drawdown_points"],
        COST_POINTS,
        equity_svg(trades),
        html_table(report["by_session"], "session"),
        html_table(report["by_direction"], "direction"),
        html_table(report["by_year"], "year"),
        html_table(report["by_exit_reason"], "exit_reason"),
        esc(json.dumps(meta, ensure_ascii=False, indent=2)),
        trade_table(trades),
    )
    path.write_text(html, encoding="utf-8")


def add_year(rows):
    out = []
    for row in rows:
        item = dict(row)
        item["year"] = item["entry_time"][:4]
        out.append(item)
    return out


def main():
    if TF not in BAR_SECONDS_BY_TF:
        raise ValueError("Unsupported TF: %s" % TF)
    start_epoch = parse_kst(TEST_START)
    end_epoch = parse_kst(TEST_END)
    print(
        "session_15m_range_retest_once | tf=%s | start=%s | end=%s | body_min=%.2f"
        % (TF, TEST_START, TEST_END, BREAKOUT_BODY_RATIO_MIN)
    )
    bars = load_bars(DATA_FILE, start_epoch, end_epoch)
    if TF == "15m":
        bars = resample_bars(bars, BAR_SECONDS_BY_TF[TF])
    if not bars:
        raise RuntimeError("No bars loaded: %s" % DATA_FILE)
    sessions = build_session_windows(bars[0].epoch, bars[-1].epoch, BAR_SECONDS_BY_TF[TF])
    trades, meta = backtest(bars, sessions)
    trades = add_year(trades)
    report = {
        "overall": summarize(trades),
        "by_session": group_summary(trades, "session"),
        "by_direction": group_summary(trades, "direction"),
        "by_year": group_summary(trades, "year"),
        "by_exit_reason": group_summary(trades, "exit_reason"),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(TRADES_FILE, trades)
    SUMMARY_FILE.write_text(json.dumps({"meta": meta, "report": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(REPORT_FILE, trades, meta, report)
    overall = report["overall"]
    print(
        "trades=%d win=%.3f expP=%.3f expR=%.3f pf=%s cumP=%.3f mddP=%.3f"
        % (
            overall["trades"],
            overall["win_rate"],
            overall["expectancy_points"],
            overall["expectancy_r"],
            str(overall["profit_factor"]),
            overall["cumulative_points"],
            overall["max_drawdown_points"],
        )
    )
    print("WROTE %s" % TRADES_FILE)
    print("WROTE %s" % SUMMARY_FILE)
    print("WROTE %s" % REPORT_FILE)


if __name__ == "__main__":
    main()
