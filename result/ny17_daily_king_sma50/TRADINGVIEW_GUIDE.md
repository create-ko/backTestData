# TradingView Guide: NY17 Daily King Keltner SMA50

## Required chart

- XAUUSD spot/CFD symbol whose daily candle rolls at **17:00 America/New_York**
- Timeframe: `1D`
- Pine file: `src/finescript/daily_king_keltner_ny17_sma50_v6.pine`
- Strategy Properties: enable **Bar Magnifier** so daily orders use intraday prices

The daily boundary is part of the strategy. Do not compare results from a UTC-calendar or broker feed with a different rollover. In TradingView, inspect candle timestamps/session information for the selected broker symbol before evaluating the report.

## Defaults

- HLC3 SMA: `50`
- Simple True Range average: `40`
- Channel width: `1.0`
- Quantity: `1`
- Commission: `0.25` cash per filled order only when the symbol's point value is `1`, representing `0.5` points round trip
- Pyramiding: `0`

The channel uses `ta.sma(ta.tr(true), 40)`. Do not replace it with Wilder-smoothed `ta.atr(40)`.

TradingView's `cash_per_contract` commission is a cash amount, not a price-point amount. If Strategy Properties shows a symbol point value other than `1`, set commission per order to `0.25 * point value`; otherwise the comparison does not include the intended `0.5`-point round trip cost.

## Rules

1. Rising completed SMA50: place a buy stop for the next daily candle at `SMA50 + simple TR40`.
2. Falling completed SMA50: place a sell stop for the next daily candle at `SMA50 - simple TR40`.
3. An unfilled entry expires after that next candle.
4. Arm the completed SMA50 exit together with the entry order, then update it after each completed daily candle while holding.
5. Hold only one position.
6. A gap through a stop is filled at the adverse opening price by TradingView's strategy engine.

This is a variable-R trend-following exit, not fixed 2R.

## Corrected local reference

New York 17:00 DST-aware daily bars built from the 5-minute XAUUSD data:

- Chronological 5-minute execution, full 2010-2026: 169 trades, `+2403.55`, PF `1.7626`, DD `414.68`
- Three-year chunks: `6/6` profitable
- Calendar years: `12/17` profitable
- 25 neighboring TR-length/channel-width settings, all executed on 5-minute bars: `25/25` produced `6/6` profitable chunks; the weakest individual chunk was only `+2.91`
- Round-trip cost 1.0: `+2321.64`, PF `1.7235`, chunks `6/6`
- Frequency: `0.0330` trades per trading day

Training-only selection used 2010-2018. It selected SMA50 as the slowest MA whose 25/25 neighbors were profitable in every training chunk. The unused 2019-2026 holdout produced 79 trades, `+1919.43`, PF `2.0487`, DD `359.80`, and `3/3` profitable chunks.

The return is strongly concentrated: the largest win contributed `44.37%` of total net and the five largest wins contributed `100.26%`. Removing those five wins changed net to `-6.23`. The short side lost `-641.60`, while the long side made `+3045.15`. In resampling, the estimated probability of a non-positive ending result was `3.79%` for IID trade bootstrap and `0.53%` for calendar-year blocks; these are descriptive model-risk estimates, not live-loss probabilities.

## Status

This is the strongest correctly aggregated candle-and-trend candidate found, but the historical profit depends heavily on a few long trends. It remains a low-frequency swing research strategy, does not satisfy 1-3 entries per day, and still needs future prospective results before live deployment. Pine compilation and broker-feed equivalence must be checked directly in TradingView.
