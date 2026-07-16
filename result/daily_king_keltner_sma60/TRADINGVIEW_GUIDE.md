# LEGACY REJECTED: Daily King Keltner SMA60

> Do not use this version for strategy confirmation. Its original robustness came from UTC calendar bars containing short Sunday partial candles. The corrected TradingView candidate is `daily_king_keltner_ny17_sma50_v6.pine` on a New York 17:00 daily feed.

## Chart and settings

- Script: `src/finescript/daily_king_keltner_sma60_v6.pine`
- Symbol: an XAUUSD spot/CFD feed
- Timeframe: `1D`
- Typical-price SMA: `60`
- Simple TR average: `40`
- Channel multiplier: `1.0`
- Position size: `1`
- Commission: `0.25` per order, equivalent to `0.5` round trip

Do not replace the simple TR average with `ta.atr(40)`. TradingView's `ta.atr` uses Wilder smoothing and produces different orders.

## Entry and exit

1. A rising completed HLC3 SMA60 enables only a next-day buy stop.
2. A falling completed HLC3 SMA60 enables only a next-day sell stop.
3. Entry is at SMA60 plus/minus one simple TR-average40.
4. An unfilled entry expires after one daily candle.
5. An open trade exits with a next-day stop at the latest completed SMA60.
6. Only one position can be open.

TradingView's stop-fill engine uses the opening price when a daily candle gaps through an order. The local reference applies the same adverse-gap rule.

## Local reference

For Dukascopy-derived UTC daily bars from 2010-01-01 through 2026-06-16:

- 190 trades
- Net `+2414.97` points after cost
- Profit factor `1.7654`
- Maximum drawdown `432.90` points
- Positive 3-year chunks: `6/6`
- Positive calendar years: `12/17`
- Average frequency: `0.0371` trades per trading day

All 25 tested SMA60 neighbors formed from TR lengths `20/30/40/60/80` and channel multipliers `0.5/0.75/1.0/1.25/1.5` were positive in all six historical chunks. Their full-period PF range was `1.7050-2.1172`.

## Chronological holdout

A separate selection audit used only 2010-2018:

1. For each MA length, test all 25 TR-length/channel-width combinations in the three training chunks.
2. Require every one of the 25 combinations to be profitable in all three chunks.
3. Select the slowest qualifying MA to reduce turnover under fixed cost.
4. Use the central `TR40 / 1.0` channel defaults.

This rule selected SMA60 without using 2019-2026 results. The unseen holdout produced:

- 88 trades
- Net `+1966.55` points
- Profit factor `2.1346`
- Maximum drawdown `303.14` points
- Positive holdout chunks: `3/3`
- At 1.0-point round-trip cost: `+1922.55`, PF `2.0894`, chunks `3/3`

The detailed audit is in `result/daily_king_keltner_robust_length_holdout/REPORT.md`.

## Research status

This is an exploratory low-frequency swing candidate. Only three trades occurred in the 2026 selection window, so 2026 does not contain enough observations to confirm the parameter. The chronological holdout is encouraging, but its robustness-selection rule was formulated during the current research process; genuinely future data is still required before live deployment. It does not satisfy the original 1-3 entries/day requirement.
