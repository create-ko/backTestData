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

## Fixed 1:2 candidate

- Script: `src/scripts/105_2m_bb20_wick_bb4_rr2.py`
- Entry: same BB20 wick breakout -> opposite BB4 pullback signal as script 103
- Stop: signal-to-entry extreme plus 0.5P buffer
- Target: exactly 2R
- Max hold: 20 bars
- Max concurrent positions: 5
- Cost: 0.5P round turn

2026-01-01 to 2026-06-17:

- Trades: 2,052
- Trading days: 142
- Trades/day: 14.4507
- Net points: +822.6515P
- Profit factor: 1.2731
- Win rate: 58.5770%
- Max drawdown: 118.0442P

2023-01-01 to 2026-06-17:

- Trades: 10,747
- Trading days: 1,075
- Trades/day: 9.9972
- Net points: -4,773.7969P
- Profit factor: 0.6570
- Win rate: 38.1502%

Interpretation: this is the first fixed 1:2 setup that satisfies the requested frequency and profitability in the 2026 Jan-Jun sample, but it fails badly when expanded to 2023-2026. Treat it as a current-regime research candidate, not a production strategy.

Post-analysis note:

- Same-sample monthly filters that rescue this RR2 variant mostly isolate the 2026 high-price/high-volatility regime.
- Examples include high ADR60 or high close thresholds that select 2026-02 through 2026-06.
- That explains why the 2026 sample works, but it is not enough evidence for a forward-tradable regime filter.
- Next validation should use walk-forward regime selection specifically for the RR2 variant.

RR2 walk-forward regime check:

- Script: `src/scripts/106_2m_bb20_wick_rr2_walkforward_regime.py`
- Baseline after 12-month warmup: 30 months, 8,783 trades, 13.8972 trades/active day, -3,236.5303P, PF 0.2034.
- Walk-forward selected months: 4 months, 1,350 trades, 18.2432 trades/active day, +373.8096P.
- Selected condition: prior-month `close >= 3772.782000`, selecting 2026-03 through 2026-06.
- Interpretation: RR2 has a faint walk-forward regime signal, but it is still mostly a high-price-regime filter with too little selected history to call stable.

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
- A newer fixed 1:2 variant works in 2026 Jan-Jun but fails on 2023-2026 expansion.
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

## RR2 walk-forward regime check

- Script: `src/scripts/106_2m_bb20_wick_rr2_walkforward_regime.py`
- Prerequisite: run script 105 with `TEST_START=2023-01-01`, `TEST_END=2026-06-17`, default RR2 parameters.
- Baseline after 12-month warmup: 30 months, 8,783 trades, 13.8972 trades/active day, -3,236.5303P, PF 0.2034.
- Walk-forward selected months: 4 months, 1,350 trades, 18.2432 trades/active day, +373.8096P.
- Selected condition: prior-month `close >= 3772.782000`, selecting 2026-03 through 2026-06.
- Interpretation: better than the no-filter RR2 baseline, but still too sparse and regime-specific for production. More robust regime logic or a different 1:2 signal is needed.

## Next work

1. Add a position-sizing/risk-percent layer for `MAX_CONCURRENT_POSITIONS=5`.
2. Improve regime logic using walk-forward validation, not full-period threshold selection.
3. Run a dedicated RR2 walk-forward regime validation before converting it to NinjaScript.
4. Convert capped candidate to NinjaScript after confirming execution assumptions.
5. If fixed RR is still required, continue searching separately; do not treat this grid candidate as 1:2.
