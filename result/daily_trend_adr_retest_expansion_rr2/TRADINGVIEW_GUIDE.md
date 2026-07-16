# TradingView Verification Guide

## Chart

- Symbol: the XAUUSD feed you actually trade
- Chart type: standard candles
- Timeframe: 5 minutes
- Pine version: 6
- Script: `src/finescript/daily_trend_adr_retest_expansion_rr2_v6.pine`
- Feature history start: 2010-01-01

## Selected Defaults

- Completed KST daily SMA: 120 days
- Retest type: either continuation retest or counter-break failure
- Retest window: 6 completed 5-minute bars
- Breakout body minimum: 0
- Stop distance: max of 1.5 points and prior KST ADR20 times 0.50
- Target: 2R
- Maximum hold: 576 5-minute bars, or 48 hours
- Sessions: Asia 08:30 KST, London 08:00 local, New York 09:30 local

## Execution Model

The signal is confirmed at a 5-minute close. A market entry is submitted for the next
bar open. `calc_on_order_fills` installs the stop and target after the entry fill.
The chart must have enough history to warm up 120 completed KST days. Keep Feature
history start at 2010-01-01 when changing the trade window to 2026 so the daily filter
uses the same prior completed history as the Python selection test.

## Differences From Python Research

- The Python result permits up to 10 independently tracked concurrent trades. This
  Pine port holds one net position because TradingView strategies do not model
  independently hedged long and short positions in one strategy.
- Python deducts exactly 0.5 price points per round trip. Pine uses 0.25 cash per
  contract on entry and exit. Adjust Strategy Properties for the contract size and
  point value of the selected broker feed.
- TradingView data, session gaps, OHLC construction, and historical coverage can differ
  from the local XAUUSD dataset. Compare signal timestamps before comparing net profit.
- Historical stop/target fills use TradingView's broker emulator. Enable Bar Magnifier
  when the account plan and available lower-timeframe history allow it.

Use the Pine result as an independent replication. It should not be expected to match
the Python totals trade-for-trade until data feed, costs, and concurrency are identical.

## One-Position Reference

Applying the selected 48-hour rule to the local data with only one position at a time
produced 3,432 trades, 1,738.09 net points, profit factor 1.0707, and 1,493.45 points
of maximum drawdown. Only two of six historical slices were profitable. This is the
appropriate local reference for the Pine port, not the 10-position Python total.
