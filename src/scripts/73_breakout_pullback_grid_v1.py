# -*- coding: utf-8 -*-
"""73 - Gold breakout double-BB pullback grid backtest v1.

Run from data/:
  python ../src/scripts/73_breakout_pullback_grid_v1.py

Spec highlights:
- XAUUSD 5m/10m, 2010-01-01~2026-06-16, LONG only.
- BB20/2 uses close. BB4/4 uses open. Do not mix them.
- Breakout double-BB: close > BB20/2 upper AND close > BB4/4 open upper.
- Immediate entry and pullback entry are separated.
- Pullback: after breakout, low < BB4/4 open lower, enter next TF open.
- Pullback windows: none, 1~6 bars, 1~10 bars.
- Midline breach is recorded, not filtered.
- 1V modes: session opening range and pre-entry avg range 20.
- Fills/exits/stops are resolved on each tested TF with conservative ordering
  (adverse fills/stop before favorable targets inside the same bar).

Console output is ASCII-only by AGENT.md. Output files are UTF-8.
"""
import bisect
import csv
import json
import math
import statistics
import time

START = "2010-01-01"
END = "2026-06-16"
TFS = ["5m", "10m"]
WINDOWS = [("w6", 6)]
V_MODES = ["session", "avg20"]
RISK_MODES = {
    "max3_stop3": {"levels": [0.0, 1.0, 2.0], "observe": [0.0, 1.0, 2.0, 3.0, 4.0], "stop": 3.0},
}
EXIT_MODELS = ["defense", "split_b", "split_c"]
COST_POINTS = 0.30
KST = 9 * 3600


def load_bars(path):
    t = []
    o = []
    h = []
    l = []
    c = []
    with open(path, encoding="utf-8-sig", newline="") as fp:
        rd = csv.reader(fp)
        next(rd)
        for r in rd:
            tt = int(float(r[0]))
            if tt > 100000000000:
                tt //= 1000
            t.append(tt)
            o.append(float(r[1]))
            h.append(float(r[2]))
            l.append(float(r[3]))
            c.append(float(r[4]))
    return t, o, h, l, c


def sma(src, n):
    out = [None] * len(src)
    s = 0.0
    for i, x in enumerate(src):
        s += x
        if i >= n:
            s -= src[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def boll(src, n, mult):
    mid = [None] * len(src)
    up = [None] * len(src)
    lo = [None] * len(src)
    s = 0.0
    ss = 0.0
    for i, x in enumerate(src):
        s += x
        ss += x * x
        if i >= n:
            old = src[i - n]
            s -= old
            ss -= old * old
        if i >= n - 1:
            m = s / n
            var = ss / n - m * m
            if var < 0:
                var = 0.0
            d = mult * math.sqrt(var)
            mid[i] = m
            up[i] = m + d
            lo[i] = m - d
    return mid, up, lo


def kdt(epoch):
    return time.gmtime(epoch + KST)


def kyear(epoch):
    return time.strftime("%Y", kdt(epoch))


def is_us_dst_kst(epoch):
    # US DST: second Sunday in March to first Sunday in November, evaluated in UTC-ish day.
    y = int(time.strftime("%Y", time.gmtime(epoch)))
    def nth_sunday(month, nth):
        ts = time.mktime((y, month, 1, 0, 0, 0, 0, 0, 0))
        g = time.gmtime(ts)
        offset = (6 - g.tm_wday) % 7
        return int(ts + (offset + 7 * (nth - 1)) * 86400)
    start = nth_sunday(3, 2)
    end = nth_sunday(11, 1)
    return start <= epoch < end


def session_start_for(epoch):
    kt = epoch + KST
    day = kt // 86400
    sec = kt % 86400
    dst = is_us_dst_kst(epoch)
    asia = 7 * 3600 if dst else 8 * 3600
    euro = 16 * 3600 if dst else 17 * 3600
    us = 22 * 3600 + 30 * 60 if dst else 23 * 3600 + 30 * 60
    starts = [asia, euro, us]
    labels = ["asia", "europe", "us"]
    chosen = None
    label = None
    for s, lab in zip(starts, labels):
        if sec >= s:
            chosen = day * 86400 + s
            label = lab
    if chosen is None:
        prev_day = day - 1
        chosen = prev_day * 86400 + us
        label = "us"
    return chosen - KST, label


def build_session_ranges(t, h, l):
    first = {}
    for i, epoch in enumerate(t):
        st, lab = session_start_for(epoch)
        key = "%s:%d" % (lab, st)
        if key not in first and epoch >= st:
            first[key] = h[i] - l[i]
    ranges = []
    labels = []
    for epoch in t:
        st, lab = session_start_for(epoch)
        key = "%s:%d" % (lab, st)
        ranges.append(first.get(key))
        labels.append(lab)
    return ranges, labels


def avg_range(h, l, end_i, n):
    if end_i <= 0:
        return None
    start = max(0, end_i - n)
    xs = [h[j] - l[j] for j in range(start, end_i)]
    return sum(xs) / len(xs) if xs else None


def make_signals(tf, t, o, h, l, c):
    mid20, up20, lo20 = boll(c, 20, 2.0)
    mid4, up4, lo4 = boll(o, 4, 4.0)
    sess_v, sess_lab = build_session_ranges(t, h, l)
    breakouts = []
    for i in range(len(t) - 1):
        if up20[i] is None or up4[i] is None:
            continue
        if c[i] > up20[i] and c[i] > up4[i]:
            breakouts.append(i)
    trades = []
    for bi in breakouts:
        ei = bi + 1
        if ei < len(t):
            trades.append(base_trade("immediate", "na", tf, bi, bi, ei, t, o, h, l, c, mid20, sess_v, sess_lab))
        pending_end = len(t) - 2
        next_break_pos = bisect.bisect_right(breakouts, bi)
        if next_break_pos < len(breakouts):
            pending_end = min(pending_end, breakouts[next_break_pos] - 1)
        for win_name, win in WINDOWS:
            max_i = pending_end if win is None else min(pending_end, bi + win)
            for k in range(bi + 1, max_i + 1):
                if lo4[k] is None:
                    continue
                if l[k] < lo4[k]:
                    ei = k + 1
                    if ei < len(t):
                        trades.append(base_trade("pullback", win_name, tf, bi, k, ei, t, o, h, l, c, mid20, sess_v, sess_lab))
                    break
    return [x for x in trades if x is not None]


def base_trade(entry_mode, window, tf, bi, trigger_i, entry_i, t, o, h, l, c, mid20, sess_v, sess_lab):
    if mid20[bi] is None:
        return None
    mid_breach = False
    for x in range(bi + 1, trigger_i + 1):
        if mid20[x] is not None and c[x] < mid20[x]:
            mid_breach = True
            break
    v_avg = avg_range(h, l, entry_i, 20)
    return {
        "tf": tf,
        "entry_mode": entry_mode,
        "window": window,
        "breakout_i": bi,
        "trigger_i": trigger_i,
        "entry_i": entry_i,
        "breakout_epoch": t[bi],
        "trigger_epoch": t[trigger_i],
        "entry_epoch": t[entry_i],
        "entry_price": o[entry_i],
        "pullback_bars": trigger_i - bi,
        "mid_breach": mid_breach,
        "mid_type": "B_mid_break" if mid_breach else "A_mid_hold",
        "session": sess_lab[entry_i],
        "year": kyear(t[entry_i]),
        "v_session": sess_v[entry_i],
        "v_avg20": v_avg,
    }


def exit_targets(model, entry1, avg_entry, v, max_fill):
    if model == "defense":
        if max_fill >= 3:
            return [(entry1, 1.0)]
        return [(entry1 + 0.5 * v, 0.5), (entry1 + 1.0 * v, 0.3), (entry1 + 2.0 * v, 0.2)]
    if model == "split_b":
        return [(avg_entry + 0.5 * v, 0.4), (avg_entry + 1.0 * v, 0.4), (avg_entry + 2.0 * v, 0.2)]
    if model == "split_c":
        return [(avg_entry + 0.3 * v, 0.5), (avg_entry + 0.8 * v, 0.3), (avg_entry + 1.5 * v, 0.2)]
    raise ValueError(model)


def simulate_one(tr, v, risk_mode_name, exit_model, t1, o1, h1, l1, c1):
    if v is None or v <= 0:
        return None
    rm = RISK_MODES[risk_mode_name]
    entry1 = tr["entry_price"]
    fill_levels = [entry1 - m * v for m in rm["levels"]]
    observe_levels = [entry1 - m * v for m in rm["observe"]]
    stop = entry1 - rm["stop"] * v
    j0 = bisect.bisect_left(t1, tr["entry_epoch"])
    if j0 >= len(t1):
        return None

    filled = [False] * len(fill_levels)
    filled[0] = True
    units = [1.0] * len(fill_levels)
    open_units = 1.0
    entry_cost = COST_POINTS * open_units
    cash = -entry_cost
    entry_sum = fill_levels[0] * open_units
    max_fill = 1
    max_touch = 1
    entry1_recovered_after_3 = False
    targets = []
    next_target = 0
    mfe = 0.0
    mae = 0.0
    reason = "FINAL"
    exit_epoch = t1[-1]

    def avg_entry():
        return entry_sum / open_units if open_units > 0 else entry1

    for j in range(j0, len(t1)):
        lo = l1[j]
        hi = h1[j]

        for idx, lvl in enumerate(observe_levels):
            if lo <= lvl:
                max_touch = max(max_touch, idx + 1)

        # Adverse path first: fills then stop.
        for idx, lvl in enumerate(fill_levels):
            if not filled[idx] and lo <= lvl:
                filled[idx] = True
                u = units[idx]
                open_units += u
                entry_sum += lvl * u
                cash -= COST_POINTS * u
                max_fill = max(max_fill, idx + 1)
                targets = []
                next_target = 0

        if open_units > 0:
            ae = avg_entry()
            if ae - lo > mae:
                mae = ae - lo
            if hi - ae > mfe:
                mfe = hi - ae
        if max_fill >= 3 and hi >= entry1:
            entry1_recovered_after_3 = True

        if lo <= stop:
            ae = avg_entry()
            cash += (stop - ae) * open_units
            cash -= COST_POINTS * open_units
            entry_sum -= ae * open_units
            open_units = 0.0
            reason = "SL"
            exit_epoch = t1[j]
            break

        if not targets:
            targets = exit_targets(exit_model, entry1, avg_entry(), v, max_fill)
        while open_units > 0 and next_target < len(targets) and hi >= targets[next_target][0]:
            price, frac = targets[next_target]
            if next_target == len(targets) - 1:
                close_u = open_units
            else:
                close_u = min(open_units, sum(units[:max_fill]) * frac)
            ae = avg_entry()
            cash += (price - ae) * close_u
            cash -= COST_POINTS * close_u
            entry_sum -= ae * close_u
            open_units -= close_u
            next_target += 1
            if open_units <= 1e-9:
                open_units = 0.0
                reason = "TP"
                exit_epoch = t1[j]
                break
        if open_units == 0.0:
            break
    if open_units > 0:
        price = c1[-1]
        ae = avg_entry()
        cash += (price - ae) * open_units
        cash -= COST_POINTS * open_units
        entry_sum -= ae * open_units
        reason = "FINAL"
        exit_epoch = t1[-1]

    return {
        "pnl_points": cash,
        "net_v": cash / v,
        "max_fill": max_fill,
        "max_touch": max_touch,
        "mfe_v": mfe / v,
        "mae_v": mae / v,
        "mfe_capture": (cash / v) / (mfe / v) if mfe > 0 else 0.0,
        "entry1_recovered_after_3": entry1_recovered_after_3,
        "reason": reason,
        "exit_epoch": exit_epoch,
    }


def aggregate(rows):
    if not rows:
        return {}
    xs = [r["net_v"] for r in rows]
    wins = [x for x in xs if x > 0]
    losses = [x for x in xs if x <= 0]
    gp = sum(wins)
    gl = -sum(losses)
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for x in xs:
        eq += x
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > mdd:
            mdd = dd
    max_fill_counts = {}
    for r in rows:
        key = str(r["max_touch"] if r["max_touch"] < 4 else "4plus")
        max_fill_counts[key] = max_fill_counts.get(key, 0) + 1
    three = [r for r in rows if r["max_touch"] >= 3]
    fourplus = [r for r in rows if r["max_touch"] >= 4]
    return {
        "trades": len(rows),
        "win_rate": round(100 * len(wins) / len(rows), 2),
        "avg_profit": round(sum(wins) / len(wins), 4) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 4) if losses else 0.0,
        "pf": round(gp / gl, 4) if gl > 0 else "inf",
        "expectancy": round(sum(xs) / len(xs), 4),
        "net_v": round(sum(xs), 3),
        "max_dd_v": round(mdd, 3),
        "mae_avg": round(sum(r["mae_v"] for r in rows) / len(rows), 4),
        "mfe_avg": round(sum(r["mfe_v"] for r in rows) / len(rows), 4),
        "mfe_capture_avg": round(sum(r["mfe_capture"] for r in rows) / len(rows), 4),
        "entry1_recovery_after_3_rate": round(100 * sum(1 for r in three if r["entry1_recovered_after_3"]) / len(three), 2) if three else 0.0,
        "touch_4plus_rate": round(100 * len(fourplus) / len(rows), 2),
        "max_touch_dist": max_fill_counts,
    }


def group_aggregate(rows, key):
    out = {}
    for r in rows:
        k = str(r[key])
        out.setdefault(k, []).append(r)
    return {k: aggregate(v) for k, v in sorted(out.items())}


def run():
    all_rows = []
    summaries = {}
    for tf in TFS:
        print("Signals", tf)
        t, o, h, l, c = load_bars("xauusd_%s_%s_%s.csv" % (tf, START, END))
        signals = make_signals(tf, t, o, h, l, c)
        print("  base entries", len(signals))
        for sig in signals:
            for v_mode in V_MODES:
                v = sig["v_session"] if v_mode == "session" else sig["v_avg20"]
                for risk_mode in RISK_MODES:
                    for exit_model in EXIT_MODELS:
                        # Immediate entries do not use pullback windows; keep only na.
                        sim = simulate_one(sig, v, risk_mode, exit_model, t, o, h, l, c)
                        if sim is None:
                            continue
                        row = dict(sig)
                        row.update(sim)
                        row.update({"v_mode": v_mode, "risk_mode": risk_mode, "exit_model": exit_model})
                        all_rows.append(row)
    variant_keys = ["tf", "entry_mode", "window", "v_mode", "risk_mode", "exit_model"]
    buckets = {}
    for r in all_rows:
        k = "|".join(str(r[x]) for x in variant_keys)
        buckets.setdefault(k, []).append(r)
    for k, rows in buckets.items():
        summaries[k] = {
            "keys": dict(zip(variant_keys, k.split("|"))),
            "summary": aggregate(rows),
            "by_year": group_aggregate(rows, "year"),
            "by_session": group_aggregate(rows, "session"),
            "by_mid_type": group_aggregate(rows, "mid_type"),
            "by_pullback_bars": group_aggregate(rows, "pullback_bars"),
            "by_max_touch": group_aggregate(rows, "max_touch"),
        }
    with open("breakout_pullback_grid_v1_summary.json", "w", encoding="utf-8") as fp:
        json.dump(summaries, fp, ensure_ascii=False, indent=2)
    with open("breakout_pullback_grid_v1_summary.csv", "w", encoding="utf-8", newline="") as fp:
        wr = csv.writer(fp)
        wr.writerow(variant_keys + ["trades", "win_rate", "expectancy", "net_v", "pf", "max_dd_v", "mae_avg", "mfe_avg", "entry1_rec3", "touch4plus"])
        for k, item in sorted(summaries.items()):
            sm = item["summary"]
            keys = item["keys"]
            wr.writerow([keys[x] for x in variant_keys] + [
                sm.get("trades"), sm.get("win_rate"), sm.get("expectancy"), sm.get("net_v"),
                sm.get("pf"), sm.get("max_dd_v"), sm.get("mae_avg"), sm.get("mfe_avg"),
                sm.get("entry1_recovery_after_3_rate"), sm.get("touch_4plus_rate"),
            ])
    print("WROTE breakout_pullback_grid_v1_summary.json")
    print("WROTE breakout_pullback_grid_v1_summary.csv")
    print("Priority view: pullback w6 max3_stop3")
    for k, item in sorted(summaries.items()):
        keys = item["keys"]
        if keys["entry_mode"] == "pullback" and keys["window"] == "w6" and keys["risk_mode"] == "max3_stop3":
            sm = item["summary"]
            print("%s %s %s %s exp=%s pf=%s n=%s midA/B=%s/%s 4+=%s" % (
                keys["tf"], keys["v_mode"], keys["exit_model"], keys["risk_mode"],
                sm.get("expectancy"), sm.get("pf"), sm.get("trades"),
                item["by_mid_type"].get("A_mid_hold", {}).get("expectancy"),
                item["by_mid_type"].get("B_mid_break", {}).get("expectancy"),
                sm.get("touch_4plus_rate"),
            ))


if __name__ == "__main__":
    run()
