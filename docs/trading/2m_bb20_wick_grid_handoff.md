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

## RR2 simple slice diagnostics

- Script: `src/scripts/107_2m_bb20_wick_rr2_slice_diagnostics.py`
- Report: `result/bb20_wick_rr2_slice_diagnostics/rr2_slice_diagnostics_report.html`
- Input: script 105 trades for `2023-01-01` to `2026-06-17`.
- Slices checked: direction, session, entry hour, weekday, risk bucket, fill-speed bucket, breakout close-position bucket, and simple two-way combinations.
- Baseline: 10,751 trades, 1,075 trading days, 10.0009 trades/day, -4,779.9355P, PF 0.6567.
- Finding: the no-filter baseline is the only checked slice that reaches the requested 10-20 trades/day over the full 2023-2026 period, but it is deeply negative.
- Interpretation: simple NinjaScript-friendly filters reduce some damage, but they also cut frequency below the target. This points back to either current-regime-only deployment, a stronger walk-forward regime gate, or a different 1:2 entry concept.

## RR2 parameter sweep

- Script: `src/scripts/108_2m_bb20_wick_rr2_param_sweep.py`
- Report: `result/bb20_wick_rr2_param_sweep/rr2_param_sweep_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Swept parameters: pending bars `10/20/30`, stop buffer `0.2/0.5`, min risk `0.8`, max risk `4/8`, max hold `10/20`, max concurrent positions `5`.
- Best full-period frequency-fit config: `pending=30`, `stop_buffer=0.5`, `max_risk=4`, `max_hold=10`, `cap=5`.
- Full-period result for that config: 13,269 trades, 12.3433 trades/day, -4,749.8582P, PF 0.6756, max DD 6,530.7409P.
- 2026 sample for the same config: 2,277 trades, 16.0352 trades/day, +1,700.8860P, PF 1.7485.
- Interpretation: parameter tuning can satisfy the requested 10-20 trades/day and looks strong in 2026, but it does not repair the 2023-2026 failure. The BB20 wick -> BB4 fixed RR2 idea remains current-regime dependent.

## BB20 fade RR2 sweep

- Script: `src/scripts/109_2m_bb20_fade_rr2_sweep.py`
- Report: `result/bb20_fade_rr2_sweep/bb20_fade_rr2_sweep_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Concept: fade BB20/2 upper/lower extremes on the next 2m open, stop beyond the signal candle extreme plus buffer, target exactly 2R.
- Close-signal quick check: all tested configs were negative and too infrequent; the best groups were only around 2-4 trades/day.
- Wick-signal quick check: frequency can reach the requested band, but performance is deeply negative.
- Best full-period frequency-fit wick config: `signal=wick`, `cooldown=0`, `stop_buffer=0.2`, `min_risk=0.8`, `max_risk=3`, `max_hold=10`, `cap=5`.
- Full-period result for that config: 20,710 trades, 19.2651 trades/day, -11,386.1455P, PF 0.5453.
- 2026 sample for the same config: 4,178 trades, 29.4225 trades/day, -2,196.6960P, PF 0.6448.
- Interpretation: simple BB20 mean-reversion with fixed 1:2 RR is not viable. The next fixed-RR search should prefer continuation/breakout-pullback ideas rather than fading every band extreme.

## BB20 continuation RR2 sweep

- Script: `src/scripts/110_2m_bb20_continuation_rr2_sweep.py`
- Report: `result/bb20_continuation_rr2_sweep/bb20_continuation_rr2_sweep_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Concept: enter in the direction of a BB20/2 close or wick extreme on the next 2m open, stop beyond the signal candle opposite extreme plus buffer, target exactly 2R.
- Close-signal quick check best frequency-fit config: `signal=close`, `trend=none`, `cooldown=3`, `stop_buffer=0.2`, `min_risk=0.8`, `max_risk=8`, `max_hold=20`, `cap=5`.
- Close-signal full-period result: 10,829 trades, 10.0735 trades/day, -4,704.5995P, PF 0.7277.
- Close-signal 2026 sample for the same config: 1,528 trades, 10.7606 trades/day, -1,015.0960P, PF 0.7717.
- Wick-signal quick check best frequency-fit config: `signal=wick`, `trend=none`, `cooldown=3`, `stop_buffer=0.2`, `min_risk=0.8`, `max_risk=4`, `max_hold=20`, `cap=5`.
- Wick-signal full-period result: 12,130 trades, 11.2837 trades/day, -5,887.5605P, PF 0.6433.
- Wick-signal 2026 sample for the same config: 1,480 trades, 10.4225 trades/day, -976.1485P, PF 0.6712.
- Interpretation: simple BB20 continuation is also not viable with fixed 1:2 RR. The signal is frequent enough, but the stop location and entry timing do not produce enough 2R follow-through.

## Structural breakout-pullback RR2 sweep

- Script: `src/scripts/111_2m_structure_breakout_pullback_rr2_sweep.py`
- Report: `result/structure_breakout_pullback_rr2_sweep/structure_breakout_pullback_rr2_sweep_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Concept: rolling prior high/low breakout, pullback touches the broken level and closes back on the breakout side, entry next 2m open, stop behind retest/level plus buffer, target exactly 2R.
- Quick sweep: lookbacks `12/24`, retest windows `3/6`, stop modes `retest/level`, stop buffer `0.2`, min risk `0.8`, max risk `4/8`, max hold `20`, cap `5`.
- Best full-period frequency-fit config: `lookback=12`, `retest_window=6`, `stop_mode=retest`, `stop_buffer=0.2`, `max_risk=4`, `max_hold=20`, `cap=5`.
- Full-period result for that config: 11,623 trades, 10.8121 trades/day, -5,676.8255P, PF 0.6402.
- 2026 sample for the same config: 1,945 trades, 13.6972 trades/day, -1,019.3525P, PF 0.7159.
- Interpretation: structural breakout-pullback reaches the desired frequency, but the basic 1:2 follow-through is still too weak. More selectivity is needed before another full sweep.

## Next work

1. Add a position-sizing/risk-percent layer for `MAX_CONCURRENT_POSITIONS=5`.
2. Improve regime logic using walk-forward validation, not full-period threshold selection.
3. Test stronger quality filters for breakout-pullback: breakout candle body/close-position, impulse size, HTF trend, or session/time gating.
4. Convert capped candidate to NinjaScript after confirming execution assumptions.
5. If fixed RR is still required, continue searching separately; do not treat this grid candidate as 1:2.
