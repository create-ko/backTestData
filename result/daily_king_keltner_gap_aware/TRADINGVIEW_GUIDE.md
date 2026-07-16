# TradingView Check Guide

## Script

Use `src/finescript/daily_king_keltner_gap_aware_v6.pine` on an XAUUSD **1D chart**.

## Required settings

- Chart timeframe: `1D`
- Typical-price SMA: `40`
- Simple TR average: `40`
- Channel ATR multiplier: `1.0`
- Order size: `1` contract
- Commission: `0.25` cash per contract per order, representing `0.5` round trip
- Slippage: `0`; daily gap slippage is handled by TradingView's stop-order fill behavior
- Pyramiding: `0`

The ATR in this script is a 40-day **simple average of True Range**, not TradingView's Wilder-smoothed `ta.atr(40)`.

## Rules

1. Calculate the daily `SMA40` of `HLC3`.
2. Rising SMA: place a next-day buy stop at `SMA40 + simple TR average40`.
3. Falling SMA: place a next-day sell stop at `SMA40 - simple TR average40`.
4. An unfilled entry order expires after the next daily candle.
5. While holding a position, update the next-day stop to the latest completed `SMA40`.
6. Hold only one position at a time.

## Local reference

The gap-aware Dukascopy-data reference for 2010-01-01 through 2026-06-16 is:

- 251 trades
- Net `+1492.59` points after 0.5 per round trip
- Profit factor `1.3932`
- Maximum drawdown `410.38` points
- Positive 3-year chunks: `5/6`
- Average frequency: `0.049` trades per trading day

TradingView results will differ because its XAUUSD feed, daily-session boundary, and contract point value depend on the selected broker symbol. Compare the trade locations and rule behavior before comparing headline profit.

## Decision

This is the most consistent candle-and-trend benchmark found so far, but it does **not** satisfy the requested 1-3 entries per day. It should be treated as a low-frequency swing system, not as confirmation that the intraday strategy is ready for live use.
