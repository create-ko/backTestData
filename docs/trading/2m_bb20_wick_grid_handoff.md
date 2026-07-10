# 2m BB20 Wick Grid Handoff

## Current best candidate

- Script: `src/scripts/103_2m_bb20_wick_bb4_grid_concurrent.py`
- Timeframe: XAUUSD 2m
- Signal: BB20/2 close-band wick breakout
- Entry: opposite BB4/4 open-band pullback limit within 20 bars
- Management: reused Strategy2 3-entry grid engine
- Practical cap: `MAX_CONCURRENT_POSITIONS=5`
- Cost: 0.5P per filled unit

This is not a fixed 1:2 RR strategy. It is the strongest high-frequency candidate found so far after fixed 1:2 tests failed.

## Verified snapshots

2026-01-01 to 2026-06-17, no regime filter, max concurrent positions 5:

- Trades: 1,577
- Trading days: 142
- Trades/day: 11.1056
- Net points: +5,384.8804P
- Profit factor: 1.3950
- Win rate: 85.7324%
- Max drawdown: 838.1854P

2023-01-01 to 2026-06-17, regime filter `ret60_le_0p129_ret240_ge_0p272`, max concurrent positions 5:

- Trades: 1,679
- Trading days: 1,075
- Active days: 180
- Trades/calendar day: 1.5619
- Trades/active day: 9.3278
- Net points: +4,198.7517P
- Profit factor: 1.2550
- Win rate: 83.9190%
- Max drawdown: 1,888.1324P

## Known risks

- Fixed 1:2 RR variants tested so far were negative; this candidate uses grid/trailing recovery logic.
- No-regime 2023-2026 result is negative, so regime or volatility/trend gating matters.
- The default capped model is more practical than independent-signal evaluation, but still needs margin/exposure sizing checks.
- NinjaTrader/Pine versions should be generated from the capped rule set, not the old independent-signal assumption.
- A first walk-forward regime check did not strongly validate the same-sample regime filter. Using only prior months to choose a next-month filter selected just 1 month out of 30 post-warmup months.

## Walk-forward regime check

- Script: `src/scripts/104_2m_bb20_wick_grid_walkforward_regime.py`
- Prerequisite: run script 103 with `TEST_START=2023-01-01`, `TEST_END=2026-06-17`, `REGIME_FILTER=none`, `MAX_CONCURRENT_POSITIONS=5`.
- Baseline after 12-month warmup: 30 months, 4,673 trades, 6.1005 trades/day, -3,290.2321P, PF 0.7306.
- Walk-forward selected months: 1 month, 308 trades, 11.8462 trades/day, +1,678.3619P.
- Interpretation: the candidate can work in certain regimes, but the current monthly filter selection is too sparse/unstable to call production-ready.

## Next work

1. Add a position-sizing/risk-percent layer for `MAX_CONCURRENT_POSITIONS=5`.
2. Improve regime logic using walk-forward validation, not full-period threshold selection.
3. Convert capped candidate to NinjaScript after confirming execution assumptions.
4. If fixed RR is still required, continue searching separately; do not treat this grid candidate as 1:2.
