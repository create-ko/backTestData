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

## Structural RR2 quality-filter diagnostics

- Script: `src/scripts/112_2m_structure_rr2_quality_filter_diagnostics.py`
- Report: `result/structure_rr2_quality_filters/structure_rr2_quality_filter_report.html`
- Input: script 111 best-trades output for `lookback=12`, `retest_window=6`, `stop_mode=retest`, `stop_buffer=0.2`, `max_risk=4`, `max_hold=20`, `cap=5`.
- Filters checked: direction, session, entry hour, weekday, risk bucket, breakout impulse bucket, impulse/risk bucket, close-position proxy, simple two-way combinations, and threshold conditions.
- Best full-period frequency-fit filter: `impulse_to_risk >= 0.1000`.
- Full-period result for that filter: 11,031 trades, 10.2614 trades/day, -5,383.0655P, PF 0.6415.
- 2026 best frequency-fit diagnostic slice: `breakout_impulse_points >= 1.0000`, 1,428 trades, 10.0563 trades/day, -771.2235P, PF 0.7127.
- Interpretation: simple quality filters improve the structural breakout-pullback setup only marginally. The fixed 1:2 target remains too ambitious for this signal family without a materially different entry or stop model.

## False breakout reversal RR2 sweep

- Script: `src/scripts/113_2m_false_breakout_reversal_rr2_sweep.py`
- Report: `result/false_breakout_reversal_rr2_sweep/false_breakout_reversal_rr2_sweep_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Concept: reuse structural breakout-pullback events from script 111, but enter the opposite direction at the same next-open entry. Stop is beyond the retest or breakout extreme, target exactly 2R.
- Quick sweep: lookbacks `12/24`, retest windows `3/6`, stop modes `retest/breakout`, stop buffer `0.2`, min risk `0.8`, max risk `4/8`, max hold `10/20`, cap `5`.
- Best full-period net result: `lookback=24`, `retest_window=3`, `stop_mode=breakout`, `max_risk=8`, `max_hold=20`, `cap=5`.
- Full-period result for that config: 2,807 trades, 2.6112 trades/day, -1,404.2800P, PF 0.6586.
- 2026 sample for the same config: 775 trades, 5.4577 trades/day, -193.7320P, PF 0.8590.
- Interpretation: reversing the failed breakout-pullback reduces loss severity but collapses frequency below the requested 10-20 trades/day and remains negative.

## Trend pullback RR2 sweep

- Script: `src/scripts/114_2m_trend_pullback_rr2_sweep.py`
- Report: `result/trend_pullback_rr2_sweep/trend_pullback_rr2_sweep_report.html`
- Period report: `result/trend_pullback_rr2_sweep/trend_pullback_rr2_best_period_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Concept: 2m SMA trend filter, pullback to the fast SMA area, momentum confirmation candle, entry next 2m open, stop behind the pullback swing, target exactly 2R.
- Representative target-frequency config: `fast_sma=20`, `slow_sma=120`, `pullback_window=3`, `touch_buffer=0.2`, `trend_mode=slope`, `confirm_mode=momentum`, `stop_buffer=0.2`, `min_risk=0.8`, `max_risk=2.5`, `max_hold=20`, `cap=5`.
- Full-period result: 20,784 trades, 19.3340 trades/day, -9,965.5825P, PF 0.5718, win rate 34.5362%, target rate 23.5325%.
- 2026 sample for the same config: 516 trades, 3.6338 trades/day, -230.6240P, PF 0.7291.
- Yearly result: 2023 -3,747.6650P, 2024 -3,567.3725P, 2025 -2,419.9210P, 2026 -230.6240P.
- Interpretation: the non-extreme trend-pullback model also fails fixed 1:2 RR. It can be tuned to the requested full-period frequency, but target hit rate remains too low and every tested year is negative.

## Session opening-range retest 2m baseline

- Script: `src/scripts/97_strategy_session_15m_range_retest_once.py`
- Command: `TF=2m TEST_START=2023-01-01 TEST_END=2026-06-17 BREAKOUT_BODY_RATIO_MIN=0.0`
- Report: `result/strategy_session_15m_range_retest_once_2m_20230101_20260617_body000/report.html`
- Result: 2,050 trades, about 1.9070 trades/day, -793.9490P, PF 0.918, win rate 32.976%.
- Body-filter command: `TF=2m TEST_START=2023-01-01 TEST_END=2026-06-17 BREAKOUT_BODY_RATIO_MIN=0.3`
- Body-filter report: `result/strategy_session_15m_range_retest_once_2m_20230101_20260617_body030/report.html`
- Body-filter result: 2,047 trades, about 1.9042 trades/day, -630.5290P, PF 0.934, win rate 33.073%.
- Interpretation: this is still negative and far below the requested 10-20 trades/day because the script intentionally allows only one trade per session. However, PF is materially closer to breakeven than the BB20/structure/SMA-pullback families, so session liquidity levels are a better next research branch.

## Session liquidity multi-level RR2 sweep

- Script: `src/scripts/115_2m_session_liquidity_rr2_sweep.py`
- Report: `result/session_liquidity_rr2_sweep/session_liquidity_rr2_sweep_report.html`
- Period report: `result/session_liquidity_rr2_sweep/session_liquidity_rr2_best_period_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Levels: session opening range high/low, previous-day high/low, previous-session high/low, and dynamic current-session prior high/low.
- Breakout/retest target-frequency check: `level_set=or,pdhpdl,prev_session,session_dynamic`, `retest_window=6`, `cooldown=0`, `stop_mode=retest`, `stop_buffer=0.2`, `max_risk=5`, `max_hold=20`, `cap=5`.
- Breakout/retest result: 11,924 trades, 11.0921 trades/day, -5,531.9645P, PF 0.6650, win rate 34.1161%, target rate 28.6984%.
- Same breakout/retest config in 2026: 2,050 trades, 14.4366 trades/day, -1,367.9955P, PF 0.6792.
- Sweep-reversal target-frequency check: same level set, `signal_mode=sweep_reversal`, `cooldown=3`, `max_risk=3`, `max_hold=20`, `cap=5`.
- Sweep-reversal result: 17,370 trades, 16.1581 trades/day, -8,768.9755P, PF 0.5851, win rate 33.5982%, target rate 27.4611%.
- Same sweep-reversal config in 2026: 2,120 trades, 14.9296 trades/day, -1,194.2525P, PF 0.6510.
- Interpretation: adding dynamic session highs/lows finally reaches the requested 10-20 trades/day with fixed 1:2 RR, but both breakout/retest and sweep-reversal variants remain structurally negative. The common failure is still low 2R target hit rate around 27-29%.

## Session liquidity filter/bias diagnostics

- Filter diagnostics script: `src/scripts/116_2m_session_liquidity_rr2_filter_diagnostics.py`
- Filter report: `result/session_liquidity_rr2_filter_diagnostics/session_liquidity_rr2_filter_diagnostics_report.html`
- Input: script 115 sweep-reversal target-frequency trades.
- Finding: simple pre-entry filters such as session, level family, direction, risk bucket, weekday, hour, and entry-to-level distance do not rescue the strategy while preserving 10-20 trades/day. Best target-frequency simple slice was `risk_points <= 1.5`: 10,842 trades, 10.0856 trades/day, -5,356.3635P, PF 0.5029.
- Biases added to script 115: `trend_follow`, `trend_fade`, `price_follow`, `price_fade`, and `combined` signal mode.
- Best lower-frequency quality candidate: sweep reversal + `price_follow`, cooldown 0, max risk 5, max hold 20. Full period: 7,660 trades, 7.1256 trades/day, -795.5270P, PF 0.9126. 2026: 1,244 trades, 8.7606 trades/day, +157.3440P, PF 1.0727.
- Best target-frequency biased candidate: combined sweep-reversal + breakout-retest, `price_follow`, cooldown 3, max risk 5, max hold 30, cap 5.
- Full-period result for that candidate: 12,568 trades, 11.6912 trades/day, -3,068.9810P, PF 0.8121, win rate 38.2161%, target rate 33.6330%.
- 2026 result for the same candidate: 2,020 trades, 14.2254 trades/day, -352.1850P, PF 0.9076.
- Yearly result: 2023 -1,036.1675P, 2024 -1,001.4815P, 2025 -679.1470P, 2026 -352.1850P.
- Interpretation: price-side bias materially improves the session liquidity branch and is the closest fixed 1:2 target-frequency candidate so far, but it remains negative over the full period and still does not meet the user's profitability requirement.

## Session liquidity displacement filter

- Script updated: `src/scripts/115_2m_session_liquidity_rr2_sweep.py`
- New knobs: `DISPLACEMENT_MODES=none,body35,body50,range120,body35_range120,close_extreme,body35_close_extreme`.
- Also fixed the sweep loop so every `cooldown_bars` combination is evaluated instead of only the last one.
- Test branch: `combined` signal mode, `price_follow` bias, `retest_window=3`, `max_risk=5`, `max_hold=30`, `cap=5`.
- Best target-frequency displacement result: `displacement_mode=close_extreme`, `cooldown=0`.
- Full-period result: 11,949 trades, 11.1153 trades/day, -2,892.0330P, PF 0.8161, win rate 37.9781%, target rate 32.5550%.
- 2026 result: 1,421 trades, 10.0070 trades/day, -123.8435P, PF 0.9586, win rate 39.0570%, target rate 36.4532%.
- Lower-frequency quality examples: `body35_close_extreme` improved 2026 to +75.6290P, PF 1.0433, but only 5.7887 trades/day; `body35_range120` improved 2026 to +8.5665P, PF 1.0071, but only 3.9789 trades/day.
- Interpretation: displacement filtering improves quality and brings the 2026 target-frequency result close to breakeven, but it still does not solve the full 2023-2026 profitability requirement. The trade-off is now clear: stricter displacement gets quality but loses frequency.

## Session liquidity regime diagnostics

- Script: `src/scripts/117_2m_session_liquidity_regime_diagnostics.py`
- Report: `result/session_liquidity_rr2_regime_diagnostics/session_liquidity_rr2_regime_diagnostics_report.html`
- Input: script 115 best target-frequency trades, `combined` signal, `price_follow`, `close_extreme`, cooldown 0.
- Baseline input result: 11,949 trades, 11.1153 trades/day, -2,892.0330P, PF 0.8161. 2026 sample: 1,421 trades, 10.0070 trades/day, -123.8435P, PF 0.9586.
- Best target-frequency regime filter: `adr20 >= 20.0000`.
- Full-period result for that filter: 10,955 trades, 10.1907 trades/day, -2,416.9265P, PF 0.8369, positive-month rate 17.9487%.
- 2026 result for the same filter: unchanged from baseline because all 2026 trades already pass the filter.
- Best positive same-sample filter: `vol20 >= 0.0120`, 2,224 trades, 2.0688 trades/day, +113.6765P, PF 1.0281, positive-month rate 60.0000%. 2026 sample: 951 trades, 6.6972 trades/day, +24.6440P, PF 1.0124.
- Other positive but low-frequency filters: `prev_month_ret >= 0.02 & adr60 >= 40.0`, 2,246 trades, 2.0893 trades/day, +61.1860P, PF 1.0145; `ret60 >= 0.02 & adr20 >= 40.0`, 3,123 trades, 2.9051 trades/day, +15.7255P, PF 1.0030.
- Interpretation: regime filtering confirms the direction of improvement: higher volatility / stronger regime conditions can push the session-liquidity RR2 branch slightly positive. However, every positive filter found so far collapses frequency well below the requested 10-20 trades/day. The current fixed 1:2 target-frequency version still does not meet the profitability requirement.

## Session liquidity exclusion-score sweep

- Script: `src/scripts/118_2m_session_liquidity_rr2_exclusion_score_sweep.py`
- Report: `result/session_liquidity_rr2_exclusion_score_sweep/session_liquidity_rr2_exclusion_score_sweep_report.html`
- Input: same script 115 best target-frequency trades as the regime diagnostics.
- Purpose: because the baseline has 11,949 trades, preserving 10 trades/day allows dropping only about 1,199 trades. This script searches for small pre-entry exclusion rules and combinations that remove the worst pockets without collapsing frequency.
- Best target-frequency exclusion found: drop `adr60 < 20.0000 + ret60 < -0.0800 + adr5 < 15.0000`.
- Full-period result after that exclusion: 10,845 trades, 10.0884 trades/day, -2,279.1430P, PF 0.8401, target rate 33.4348%.
- This improves the baseline by about +612.8900P, but the strategy remains far from profitable.
- Best target-frequency exclusion that also keeps 2026 above 10 trades/day: drop `adr20 < 20.0000 + adr60 < 20.0000 + adr5 < 15.0000`.
- Result for that rule: 10,755 trades, 10.0047 trades/day, -2,316.1080P, PF 0.8417. 2026 remains 1,421 trades, 10.0070 trades/day, -123.8435P, PF 0.9586.
- Interpretation: excluding the worst 10% can reduce damage, but cannot rescue the current target-frequency candidate. This suggests the remaining edge problem is in the entry concept, not just in a missing simple regime filter.

## Session liquidity immediate-entry 2026 quick check

- Script: `src/scripts/119_2m_session_liquidity_immediate_rr2_sweep.py`
- Report: `result/session_liquidity_immediate_rr2_sweep/session_liquidity_immediate_rr2_sweep_report.html`
- Command used: `TEST_START=2026-01-01 TEST_END=2026-06-17`.
- Concept: use the same liquidity levels as script 115, but enter next 2m open immediately after a level breakout or sweep/reversal instead of waiting for retest.
- Full 2023-2026 run was not completed yet because the first non-vectorized implementation is too slow on the full 2m dataset. Treat this as a 2026 sample check only.
- Best 2026 target-frequency immediate config: `combined_immediate`, `price_follow`, `body35_close_extreme`, cooldown 3, retest-candle stop, max risk 5, hold 20.
- 2026 result for that target-frequency config: 1,754 trades, 12.3521 trades/day, -684.8365P, PF 0.8309, target rate 31.1288%.
- Best 2026 quality config: `sweep_reversal_immediate`, `price_follow`, `body35_close_extreme`, cooldown 3, hold 30.
- 2026 result for that quality config: 432 trades, 3.0423 trades/day, +167.7805P, PF 1.1983, target rate 40.0463%.
- Interpretation: immediate breakout momentum is poor, but immediate sweep reversal has a real 2026 signal. The same trade-off appears again: profitable 1:2 behavior exists at 3-5 trades/day, but combining enough signals to reach 10-20 trades/day degrades expectancy.

## Immediate sweep-reversal full-period check

- Script: `src/scripts/120_2m_session_sweep_reversal_immediate_rr2_full.py`
- Report: `result/session_sweep_reversal_immediate_rr2_full/session_sweep_reversal_immediate_rr2_full_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Concept: expand only the 2026-positive immediate sweep-reversal branch from script 119 to the full 2023-2026 period. Breakout momentum is intentionally excluded because it was strongly negative in the 2026 quick check.
- Best full-period quality config: `sweep_reversal_immediate`, `price_follow`, `body35_close_extreme`, cooldown 3, retest-candle stop, stop buffer 0.2, max risk 5, hold 30, cap 5.
- Full-period result: 4,332 trades, 4.0298 trades/day, -388.1830P, PF 0.9269, target rate 33.7950%, max drawdown 822.7070P.
- 2026 result for the same config: 432 trades, 3.0423 trades/day, +167.7805P, PF 1.1983, target rate 40.0463%.
- Higher-frequency variant: `close_extreme`, cooldown 0, hold 30 reached 6,120 trades, 5.6930 trades/day, -706.4170P, PF 0.9065. It still does not reach the requested 10-20 trades/day.
- Interpretation: the immediate sweep-reversal signal is much better than the high-frequency breakout/continuation families, but it is still not a complete answer. It is 2026-positive and relatively close to breakeven over 2023-2026, yet it is both full-period negative and too infrequent. The next useful step is to diagnose why 2023-2025 drag it down, not to add the already-failed breakout leg just to inflate frequency.

## Immediate sweep-reversal slice diagnostics

- Script: `src/scripts/121_2m_sweep_reversal_immediate_slice_diagnostics.py`
- Report: `result/sweep_reversal_immediate_slice_diagnostics/sweep_reversal_immediate_slice_diagnostics_report.html`
- Input: script 120 best-quality trades.
- Baseline input: 4,332 trades, 4.0298 trades/day, -388.1830P, PF 0.9269.
- Yearly profile: 2023 -381.6550P, 2024 -279.6180P, 2025 +105.3095P, 2026 +167.7805P.
- Strongest simple slice: `risk_points >= 3.0000`, 535 trades, 0.4977 trades/day, +413.4965P, PF 1.3655. 2026: 230 trades, 1.6197 trades/day, +205.2480P, PF 1.3970.
- Highest-frequency positive slice found: `adr60 >= 30.0000`, 2,557 trades, 2.3786 trades/day, +238.7360P, PF 1.0679. 2026: 432 trades, 3.0423 trades/day, +167.7805P, PF 1.1983.
- Other useful positive slices: `adr20 >= 30.0000`, 2,420 trades, 2.2512 trades/day, +221.0960P, PF 1.0640; `session == asia`, 2,515 trades, 2.3395 trades/day, +58.8330P, PF 1.0194; `vol20 >= 0.0080`, 2,314 trades, 2.1526 trades/day, +0.4765P, PF 1.0001.
- Interpretation: the signal is real in higher-volatility or wider-risk conditions, but its usable frequency is around 2-3 trades/day. Forcing this same signal above that range adds low-quality trades. This branch should be treated as one component in a basket of reversal signals, not the full 10-20 trades/day answer by itself.

## PDH/PDL double-sweep reversal RR2

- Script: `src/scripts/122_2m_pdh_pdl_double_sweep_reversal_rr2.py`
- Report: `result/pdh_pdl_double_sweep_reversal_rr2/pdh_pdl_double_sweep_reversal_rr2_report.html`
- Period report: `result/pdh_pdl_double_sweep_reversal_rr2/pdh_pdl_double_sweep_reversal_rr2_best_period_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Concept: use only previous-day high/low. A trade triggers only on the second or later same-day failed sweep of the same level, entering next 2m open in the reversal direction with fixed 1:2 RR.
- Best full-period config: `price_follow`, `body35_close_extreme`, same-level sweep gap 3-360 bars, stop buffer 0.5, max risk 8, max hold 45, cap 5.
- Full-period result: 485 trades, 0.4512 trades/day, +60.4165P, PF 1.0906, target rate 32.5773%, positive years 3/4, positive-month rate 51.2195%.
- 2026 result for the same config: 50 trades, 0.3521 trades/day, +49.1205P, PF 1.4194.
- Best higher-frequency positive variant: `price_follow`, `close_extreme`, gap 3-360, stop buffer 0.5, max risk 8, hold 45. Full-period: 539 trades, 0.5014 trades/day, +37.6375P, PF 1.0503. 2026: 56 trades, +64.3900P, PF 1.5013.
- Interpretation: this is an independent profitable reversal component, but it is much too infrequent to be a standalone answer. It can contribute about 0.4-0.5 trades/day to a future basket if overlap with the immediate sweep-reversal branch is acceptable.

## Opening-range failed-breakout reversal RR2

- Script: `src/scripts/123_2m_opening_range_failed_breakout_reversal_rr2.py`
- Report: `result/opening_range_failed_breakout_reversal_rr2/opening_range_failed_breakout_reversal_rr2_report.html`
- Period report: `result/opening_range_failed_breakout_reversal_rr2/opening_range_failed_breakout_reversal_rr2_best_period_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Concept: after a session opening-range close breakout, enter reversal if price closes back inside the range within 3-6 bars. Stop beyond the failed-breakout candle, target exactly 2R.
- Focused sweep parameters: OR 8 bars, breakout body minimum 0.25/0.40, fail window 3/6, `price_follow` or `price_fade`, close-extreme displacement, max risk 5/8, hold 20/45.
- Best full-period config: OR 8, fail window 3, breakout body min 0.40, `price_follow`, `body35_close_extreme`, cooldown 3, stop buffer 0.2, max risk 8, hold 45, cap 5.
- Full-period result: 1,917 trades, 1.7833 trades/day, -106.6125P, PF 0.9604, target rate 34.8983%, max drawdown 349.6160P.
- Yearly result for that config: 2023 -203.3400P, 2024 -97.5190P, 2025 +133.6255P, 2026 +60.6210P.
- 2026 result: 259 trades, 1.8239 trades/day, +60.6210P, PF 1.0889.
- Interpretation: this is not yet an independently profitable full-period component. However, it has better frequency than the PDH/PDL double-sweep branch and is positive in 2025-2026. It is worth one more diagnostic pass by volatility/risk/session before discarding.

## Opening-range failed-breakout slice diagnostics

- Script: `src/scripts/124_2m_or_failed_breakout_slice_diagnostics.py`
- Report: `result/or_failed_breakout_slice_diagnostics/or_failed_breakout_slice_diagnostics_report.html`
- Input: script 123 best-quality trades.
- Baseline input: 1,917 trades, 1.7833 trades/day, -106.6125P, PF 0.9604.
- Strongest simple slice: `risk_points >= 3.0000`, 336 trades, 0.3126 trades/day, +255.7460P, PF 1.2816. 2026: 174 trades, 1.2254 trades/day, +79.9310P, PF 1.1479.
- More usable frequency slice: `risk_points >= 1.5000`, 970 trades, 0.9023 trades/day, +215.0310P, PF 1.1193. 2026: 250 trades, 1.7606 trades/day, +61.9960P, PF 1.0922.
- Highest-frequency positive volatility slice: `adr60 >= 30.0000`, 1,139 trades, 1.0595 trades/day, +148.7225P, PF 1.0790. 2026: 259 trades, 1.8239 trades/day, +60.6210P, PF 1.0889.
- Other positive filters: `adr20 >= 30.0000`, 1,069 trades, 0.9944 trades/day, +177.7460P, PF 1.0972; `vol20 >= 0.0080`, 1,052 trades, 0.9786 trades/day, +124.3165P, PF 1.0709; `session == asia`, 1,357 trades, 1.2623 trades/day, +47.7880P, PF 1.0249.
- Interpretation: this branch becomes a valid low-frequency component when restricted to wider-risk or higher-volatility conditions. It contributes about 0.9-1.1 trades/day as a full-period-positive 1:2 RR component, and it is complementary to the immediate sweep-reversal branch.

## RR2 reversal basket

- Script: `src/scripts/125_2m_rr2_reversal_basket.py`
- Report: `result/rr2_reversal_basket/rr2_reversal_basket_report.html`
- Period report: `result/rr2_reversal_basket/rr2_reversal_basket_best_period_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Method: combine already-tested low-frequency fixed 1:2 reversal components, remove near-duplicate entries, and apply a portfolio cap of 5 concurrent positions.
- Best scored basket: `immediate_risk_ge_2 + or_risk_ge_1p5 + pdh_pdl_best`.
- Full-period result: 2,092 trades, 1.9460 trades/day, +349.7370P, PF 1.0961, target rate 34.2256%, max drawdown 200.0635P.
- Yearly result: 2023 -91.9110P, 2024 -29.1135P, 2025 +323.5480P, 2026 +147.2135P.
- 2026 result: 491 trades, 3.4577 trades/day, +147.2135P, PF 1.1220.
- Highest-frequency profitable basket checked: `immediate_adr60_ge_30 + or_risk_ge_1p5 + pdh_pdl_best`, 3,134 trades, 2.9153 trades/day, +212.5685P, PF 1.0461. 2026: 531 trades, 3.7394 trades/day, +139.3635P, PF 1.1111.
- Interpretation: combining positive reversal components preserves profitability and raises frequency to about 2-3 trades/day, but it still falls far short of the requested 10-20 trades/day. This is the strongest fixed 1:2 full-period direction so far: profitable, capped, deduped, but low-frequency.

## Extreme BB / structure reversal add-on

- Script: `src/scripts/126_2m_extreme_bb_structure_reversal_rr2.py`
- Report: `result/extreme_bb_structure_reversal_rr2/extreme_bb_structure_reversal_rr2_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Concept: after a 2m candle wicks outside BB20/2 and/or sweeps a rolling structural high/low, trade the next-open reversal only if the same candle closes back inside the reference level. Stop is beyond the failed-extreme candle, target exactly 2R.
- Focused sweep used after the first broad run was too slow: lookbacks 24/48, `bb_and_structure` and `structure_only`, `price_follow`, `body35_close_extreme`, cooldown 3, stop buffer 0.2/0.5, min risk 1.5/2/3, max risk 5/8, hold 30/45.
- Best quality config: `lookback=48`, `structure_only`, `inside_both`, `price_follow`, `body35_close_extreme`, cooldown 3, stop buffer 0.2, min risk 2.0, max risk 8.0, hold 30, cap 5.
- Full-period result: 105 trades, 0.0977 trades/day, +109.1565P, PF 1.5419, target rate 41.9048%, max drawdown 30.5355P.
- 2026 result: 37 trades, 0.2606 trades/day, +33.9230P, PF 1.3099.
- Interpretation: this is a clean but very small add-on. It is not a frequency solution, but it passes the "standalone positive before combining" rule and can be added to the reversal basket.

## RR2 reversal basket with extreme add-on

- Script: `src/scripts/127_2m_rr2_reversal_basket_with_extreme.py`
- Report: `result/rr2_reversal_basket_with_extreme/rr2_reversal_basket_with_extreme_report.html`
- Period report: `result/rr2_reversal_basket_with_extreme/rr2_reversal_basket_with_extreme_best_period_report.html`
- Best basket: `immediate_risk_ge_2 + or_risk_ge_1p5 + pdh_pdl_best + extreme_structure_best`.
- Full-period result: 2,147 trades, 1.9972 trades/day, +397.8120P, PF 1.1056, target rate 34.4667%, max drawdown 203.9370P.
- Year profile: positive years 2/4; the add-on improves net points but does not fix the weak 2023-2024 profile.
- 2026 result: 517 trades, 3.6408 trades/day, +160.5160P, PF 1.1244.
- Comparison against the prior best basket: adding the extreme-structure component improved full net from +349.7370P to +397.8120P and frequency from 1.9460 to 1.9972 trades/day. This is a constructive incremental improvement, but still nowhere near 10-20 trades/day.

## Session-liquidity walk-forward bucket selector

- Script: `src/scripts/128_2m_session_liquidity_walkforward_bucket_selector.py`
- Report: `result/session_liquidity_walkforward_bucket_selector/session_liquidity_walkforward_bucket_selector_report.html`
- Input: `result/session_liquidity_rr2_sweep/session_liquidity_rr2_best_trades.csv`, the high-frequency session-liquidity candidate with 11.1153 trades/day and -2,892.0330P.
- Concept: avoid same-sample filtering by selecting simple buckets from only the prior N months, then trading matching buckets in the next month. Buckets include combinations of session, level name, signal mode, direction, entry hour, risk bin, and simple daily regime bins.
- Broad grid was slow, so targeted checks were run first:
  - `core`, lookback 1 month, min 5 trades, PF >= 1.0, all selected buckets: 3,083 trades, 2.8679 trades/day, -496.6340P, PF 0.8887. 2026: -229.8655P, PF 0.7941.
  - `signal_hour`, lookback 1 month, min 5 trades, PF >= 1.0, all selected buckets: 3,209 trades, 2.9851 trades/day, -520.3940P, PF 0.8857. 2026: -19.0005P, PF 0.9777.
  - `signal_hour`, lookback 1 month, min 5 trades, PF >= 1.1, avg >= 0.05, top 50 buckets: 2,764 trades, 2.5712 trades/day, -394.4890P, PF 0.8982. 2026: +11.7165P, PF 1.0156.
  - `signal_hour`, lookback 1 month, min 5 trades, PF >= 1.2, avg >= 0.10, top 20 buckets: 2,473 trades, 2.3005 trades/day, -426.8095P, PF 0.8785. 2026: +51.7675P, PF 1.0749.
- Interpretation: recent-month bucket selection improves the 2026 sample but does not rescue the full 2023-2026 period, and it collapses frequency from 11/day to about 2-3/day. This confirms that the high-frequency session-liquidity branch is not just missing a simple walk-forward bucket filter.

## Anchored mean-reversion RR2 sweep

- Script: `src/scripts/129_2m_anchored_mean_reversion_rr2_sweep.py`
- Report: `result/anchored_mean_reversion_rr2_sweep/anchored_mean_reversion_rr2_sweep_report.html`
- Input period: `2023-01-01` to `2026-06-17`.
- Concept: create more frequent reversal opportunities than static liquidity levels by using an expanding session or day anchored mean. When price stretches away from the anchor by a multiple of recent median 2m range and closes back toward the anchor, enter next-open reversal with fixed 1:2 RR. This is volume-free "anchored mean", not true VWAP, because the available CFD data does not expose reliable volume.
- Representative high-frequency check: `session_mean`, wick stretch, body closes toward anchor, no trend bias, close-extreme displacement, min anchor bars 10, distance 1.2x median range, cooldown 3, stop buffer 0.2, max risk 5, hold 20, cap 5.
  - Full-period result: 20,000 trades, 18.6047 trades/day, -10,876.2595P, PF 0.6184, target rate 26.5900%.
  - 2026 result: 3,245 trades, 22.8521 trades/day, -2,079.6630P, PF 0.7070.
- Stronger session-mean quality check: `session_mean`, wick stretch, close back inside band and body toward anchor, `price_follow`, `body35_close_extreme`, min anchor bars 20, distance 1.6x, cooldown 3, stop buffer 0.2, max risk 8, hold 30, cap 5.
  - Full-period result: 1,766 trades, 1.6428 trades/day, +3.1500P, PF 1.0013, target rate 34.6546%.
  - 2026 result: 264 trades, 1.8592 trades/day, -12.5190P, PF 0.9818.
- Stronger day-mean quality check: same as above but `day_mean`.
  - Full-period result: 2,106 trades, 1.9591 trades/day, -98.1025P, PF 0.9664.
  - 2026 result: 319 trades, 2.2465 trades/day, +42.3660P, PF 1.0534.
- Interpretation: anchored mean reversion easily creates enough trades, but the high-frequency fixed 1:2 version is deeply negative. Stronger filters can approach breakeven, but frequency collapses to about 1.6-2.0 trades/day. This branch does not solve the 10/day fixed-RR requirement, though the strict session-mean variant may be useful later as a tiny component only after further validation.

## Next work

## Validated low-frequency alternative: RR2 reversal basket

- Staged runner: `src/scripts/138_2m_rr2_reversal_basket_staged.py`
- Components: immediate session sweep reversal with risk >=2, opening-range
  failed-breakout reversal with risk >=1.5, PDH/PDL double-sweep reversal, and
  the extreme-structure reversal add-on. Entries are deduplicated and capped
  at five concurrent positions.
- Fixed target: exactly 2R. This is a basket of independently tested reversal
  components, not a single high-frequency trigger.
- 2026-01-01 to 2026-06-17: 517 trades, 3.6408/day, +160.5160P, PF 1.1244.
- 2024-01-01 to 2026-06-17: 1,905 trades, 2.4869/day, +489.7230P, PF 1.1397,
  max DD 128.7860P, positive-month rate 50.0%.
- 2023-01-01 to 2026-06-17: 2,147 trades, 1.9972/day, +397.8120P, PF 1.1056,
  max DD 203.9370P, positive-month rate 45.2381%. Yearly net: 2023 -91.9110P,
  2024 -32.2240P, 2025 +361.4310P, 2026 +160.5160P.
- Interpretation: this is the first alternative that satisfies the revised
  1-3 trades/day objective, retains fixed 1:2 RR, and remains positive across
  the 2023-2026 aggregate. It is not profitable in every year, so it should be
  validated in NinjaTrader with broker-specific costs and fill rules before
  live use.
- Staged reports:
  - `result/rr2_reversal_basket_staged/2026/`
  - `result/rr2_reversal_basket_staged/20240101_20260617/`
  - `result/rr2_reversal_basket_staged/20230101_20260617/`

### Final basket configuration with daily cap

- Runner setting: `MAX_TRADES_PER_DAY=3`. The selected basket is
  `immediate_risk_ge_2 + or_risk_ge_1p5 + pdh_pdl_best`; the extreme add-on is
  excluded from the final configuration because it adds little edge after the
  daily cap.
- 2026-01-01 to 2026-06-17: 257 trades, 1.8099/day, `+148.9920P`, PF `1.2308`,
  max DD `98.4535P`.
- 2024-01-01 to 2026-06-17: 1,142 trades, 1.4909/day, `+431.3560P`, PF
  `1.2138`, max DD `112.4825P`, positive-month rate `50.0%`.
- 2023-01-01 to 2026-06-17: 1,331 trades, 1.2381/day, `+370.9260P`, PF
  `1.1671`, max DD `140.3850P`, positive-month rate `42.8571%`.
- This is the recommended alternative under the revised 1-3 trades/day goal:
  fixed 1:2 RR, daily frequency capped at three, staged expansion completed,
  and positive aggregate results across all tested periods. It still has
  losing years/months and requires broker-specific NinjaTrader verification.
- Final staged report folders:
  - `result/rr2_reversal_basket_staged/2026_cap3/`
  - `result/rr2_reversal_basket_staged/20240101_20260617_cap3/`
  - `result/rr2_reversal_basket_staged/20230101_20260617_cap3/`

## Staged search: alternative 2m strategy families

The staged search order is 2026 first, then 2024-2026 and 2021-2026 only for
configs that are profitable and near the target frequency in the shorter
sample. This avoids repeatedly simulating the full 2010-2026 file for weak
ideas.

### Compression-expansion breakout RR2

- Script: `src/scripts/131_2m_compression_expansion_rr2_staged.py`
- Signal: prior bars have compressed ranges, then a strong candle closes beyond
  a rolling high/low. Enter next open, stop at the breakout candle extreme,
  target 2R.
- 2026 focused sweep: the highest-frequency positive result was below 1 trade
  per day. The 8.59 trades/day config returned `-453.2970P`, PF `0.8294`.
- Decision: do not expand to 2024-2026; the 2026 gate failed.

### Session VWAP / EMA pullback RR2

- Script: `src/scripts/132_2m_vwap_ema_pullback_rr2_staged.py`
- Signal: session VWAP (CFD tick-volume proxy) and EMA trend alignment, then a
  shallow EMA pullback that closes back with the trend. Enter next open and
  target 2R.
- 2026 focused sweep: best observed configuration produced about 3.05
  trades/day and `-174.4095P`, PF `0.7709`.
- Decision: do not expand; both frequency and expectancy failed.

### RSI reclaim RR2

- Script: `src/scripts/133_2m_rsi_reclaim_rr2_staged.py`
- Signal: RSI recovery from an oversold/overbought threshold with optional EMA
  or session-VWAP direction filter. Stop is the signal candle extreme and
  target is 2R.
- 2026 focused sweep: best configuration was RSI5 10/90 with VWAP filter,
  19 trades, 0.1338 trades/day, `+23.8195P`, PF `1.8698`.
- Decision: positive but far too infrequent; do not expand as a standalone
  answer to the user's target.

- Current research conclusion: the alternative families screened so far either
  lose money when made frequent or become positive only after collapsing to
  less than 1-3 trades/day. The staged runner is available for future families,
  but no candidate has earned a 2-3 year expansion yet.

### BB20 wick -> EMA pullback RR2

- Script: `src/scripts/135_2m_bb20_wick_ema_pullback_rr2_staged.py`
- Signal: retain the BB20 wick event but replace the BB4 limit with a fixed
  EMA10/20/30 pullback limit, then use the signal-to-fill extreme stop and 2R
  target.
- 2026 best observed positive configuration: EMA10, pending 30, `price_follow`,
  cooldown 3, max risk 5, hold 20; 254 trades, 1.7887 trades/day,
  `+50.5189P`, PF `1.1559`.
- Decision: positive but far below the desired frequency, so it does not earn
  a 2-3 year expansion.

### Micro EMA reclaim RR sweep

- Script: `src/scripts/136_2m_micro_ema_cross_rr_sweep_staged.py`
- Signal: price crosses back through a fast EMA while the fast/slow EMA trend
  agrees; stop uses the recent pullback extreme. Target R was swept across
  `1.0/1.25/1.5/2.0` to test whether the frequency problem was caused only by
  the 2R target.
- 2026 focused result: the best-frequency configurations were about 2.8
  trades/day and remained negative. The 2R example returned about `-165P`, and
  lowering the target did not turn the target-frequency band positive.
- Decision: reject this family before 2-3 year expansion.

### Current constraint diagnosis

- Across the alternative families screened in 2026, frequent configurations
  generally have target rates below the break-even level required by fixed 2R
  plus CFD transaction cost. Positive configurations become sparse, usually
  below 1-3 trades/day.
- The next meaningful research branch must relax at least one constraint: use a
  lower target R, accept a lower frequency, or combine a larger set of
  independently positive low-frequency signals. Forcing weak signals to reach
  10 trades/day has repeatedly produced negative expectancy.

### Session-liquidity target-R staged expansion

- Script: `src/scripts/137_2m_session_liquidity_rr_sweep_staged.py`
- 2026 gate candidate: OR sweep reversal, `price_follow`, `close_extreme`,
  cooldown 3, target 2R, max hold 30; 460 trades, 3.2394/day,
  `+94.6010P`, PF `1.1039`.
- 2024-01-01 to 2026-06-17 expansion using the same fixed configuration:
  3,119 trades, 4.0718/day, `-170.3030P`, PF `0.9587`.
- Decision: the candidate passes the 2026 screen only at low frequency and
  fails the first 2-year-plus expansion, so it is rejected for production or
  further 2021-2026 testing.

- R-multiple relaxation check on the same 2024-2026 sample: 1.0/1.25/1.5R
  were also negative. The best tested lower-R configuration was 1.5R at
  `-421.4515P`, PF `0.8881`, with the same 4.0718 trades/day. Lowering the
  target alone does not repair the regime instability.

- Direction split check: long-only was `-204.6030P`, PF `0.9060`, and short-only
  was a marginal `+34.3000P`, PF `1.0176` over 2024-2026, both below 2.2
  trades/day. The same short-only configuration fell to `-493.2695P`, PF
  `0.8464`, over 2021-2026, so the marginal gain was not stable.

## Full available XAUUSD 2m test

- Test range: `2010-01-01` to `2026-06-17` exclusive, using the full available `xauusd_2m_2010-01-01_2026-06-16.csv` dataset.
- Configuration: `PENDING_BARS=30`, `STOP_BUFFER_POINTS=0.5`, `MIN_RISK_POINTS=0.8`, `MAX_RISK_POINTS=4.0`, `MAX_HOLD_BARS=20`, `MAX_CONCURRENT_POSITIONS=5`, round-turn cost `0.5P`.
- Result: 42,626 trades, 5,125 trading days, 8.3173 trades/day, -27,239.2586P, PF 0.4235, target rate 21.8974%, max drawdown 29,032.3802P.
- Yearly net points: 2010 -2,058.9822P, 2011 -1,593.6097P, 2012 -1,894.7245P, 2013 -2,073.4961P, 2014 -1,646.6467P, 2015 -1,349.8730P, 2016 -1,782.0413P, 2017 -995.1432P, 2018 -1,182.2475P, 2019 -1,285.7136P, 2020 -2,132.6307P, 2021 -2,425.9257P, 2022 -2,007.3068P, 2023 -2,038.5405P, 2024 -2,565.1172P, 2025 -1,917.3770P, 2026 +1,710.1171P.
- Interpretation: the requested 10-trades/day frequency is not stable over the full history, and the fixed 1:2 setup is decisively negative outside the 2026 regime. The current strategy must be treated as a 2026 high-price-regime candidate, not as a full-history production strategy.
- Full-period files: `result/bb20_wick_bb4_rr2_2m_20100101_20260617/bb20_wick_bb4_rr2_overall.csv`, `bb20_wick_bb4_rr2_yearly.csv`, and `bb20_wick_bb4_rr2_monthly.csv`.

## NinjaTrader port for current-regime RR2 candidate

- Strategy: `src/ninjascript/Bb20WickBb4Rr2Xauusd.cs`
- Usage: `src/ninjascript/README_bb20_wick_bb4_rr2.md`
- Primary series is 2-minute XAUUSD/Gold CFD. It calculates BB20/2 from closes and BB4/4 from opens, keeps a pullback limit active for 30 bars, uses a 0.5P extreme buffer, fixed 2R target, 0.8-4.0P risk bounds, 20-bar maximum hold, and exports yearly/monthly CSV reports.
- The default prior-month gate is `prior completed daily close >= 3772.782`, matching the current 2026 high-price regime research condition. It is a conditional research deployment setting, not a general long-term filter.
- The port separates signal detection from order activation so a breakout outside KST 09:00-18:00 can remain pending while fills are accepted only inside that window.
- The local workspace has no NinjaTrader assemblies or C# compiler, so platform compilation and Strategy Analyzer parity remain to be verified inside NinjaTrader. Commission, slippage, bar fill resolution, and same-bar stop/target ordering can change results versus the Python model.

## 2026 current-regime BB20 wick -> BB4 RR2 revalidation

- Fixed configuration: `PENDING_BARS=30`, `STOP_BUFFER_POINTS=0.5`, `MIN_RISK_POINTS=0.8`, `MAX_RISK_POINTS=4.0`, `MAX_HOLD_BARS=20`, `MAX_CONCURRENT_POSITIONS=5`, round-turn cost `0.5P`.
- Script: `src/scripts/105_2m_bb20_wick_bb4_rr2.py`
- 2026-01-01 to 2026-06-17: 2,278 trades, 16.0423 trades/day, +1,713.5867P, PF 1.7411, max DD 49.8110P.
- Monthly net points: January +184.9954P, February +485.5582P, March +392.5776P, April +128.7086P, May +371.4882P, June 1-17 +150.2587P. All six months were positive.
- Same fixed configuration over 2023-01-01 to 2026-06-17: 13,258 trades, 12.3330 trades/day, -4,811.9223P, PF 0.6877. Yearly net: 2023 -2,041.5515P, 2024 -2,566.7746P, 2025 -1,913.7132P, 2026 +1,710.1171P.
- Walk-forward check: using only prior-month data to select a regime condition selected 5 months, February through June 2026, with 1,904 trades, 20.0421 trades per active day, +1,525.1217P, PF reported as infinite because the selected sample had no losing trades. The post-warmup no-filter baseline was 10,691 trades, 16.8894 per active day, -2,770.3705P, PF 0.4010.
- Interpretation: this is the strongest candidate for the originally specified 2026 Jan-Jun sample and the rule is straightforward to port to NinjaScript. It remains regime-dependent and has not been proven across multiple independent regimes. The walk-forward filter must be enabled only from prior-month data; the 2026 result must not be treated as a guarantee for later months.

## Rolling false-breakout reversal RR2

- Script: `src/scripts/130_2m_rolling_false_breakout_reversal_rr2.py`
- Report: `result/rolling_false_breakout_reversal_rr2/rolling_false_breakout_reversal_rr2_report.html`
- Concept: use the prior rolling high/low over 3-48 bars. After a close breaks the level, enter the next 2m open only when a later candle closes back inside it. The stop is beyond the full breakout/failure excursion and the target is fixed at 2R.
- Focused quality run: lookbacks 12/24, fail window 3, breakout body 0.25/0.40, `price_follow`, `body35_close_extreme`, cooldown 3, stop buffer 0.2, max risk 8, hold 30/45.
  - Best quality result in this run: lookback 24, body 0.25, hold 30, 1,421 trades, 1.3219/day, -277.5890P, PF 0.8711. 2026: 207 trades, 1.4577/day, -19.5895P, PF 0.9654.
- Focused frequency run: lookbacks 3/6/12, fail window 1/3, no bias, `close_extreme`, cooldown 0, stop buffer 0.2, max risk 5, hold 20.
  - Lookback 6 / fail window 1: 9,328 trades, 8.6772/day, -4,865.6325P, PF 0.6281. 2026: 1,058 trades, 7.4507/day, -319.2495P, PF 0.8641.
  - Lookback 3 / fail window 1: 12,728 trades, 11.8400/day, -6,375.9350P, PF 0.6416. 2026: 1,535 trades, 10.8099/day, -421.8220P, PF 0.8747.
- Interpretation: this family can reach the requested frequency, but its fixed 1:2 expectancy is decisively negative both over the full sample and over 2026. It should not be combined into the positive reversal basket merely to increase trade count.

1. Add a position-sizing/risk-percent layer for `MAX_CONCURRENT_POSITIONS=5`.
2. Improve regime logic using walk-forward validation, not full-period threshold selection.
3. For fixed 1:2, the next promising branch is still combining independently positive reversal-style signals without adding the negative breakout-momentum leg.
4. Candidate add-on family already tested: extreme-risk-only BB/structure reversal. It was standalone positive, but only adds about 0.05 trades/day after dedupe/cap.
5. Walk-forward bucket selection on the high-frequency session-liquidity candidate did not solve the frequency/profitability trade-off.
6. Continue searching for additional independent positive components, because the current profitable basket reaches only about 2-3 trades/day.
7. Convert capped candidate to NinjaScript only after confirming execution assumptions and deciding whether the lower-frequency profitable reversal branch is acceptable.
8. If fixed RR is still required at 10-20 trades/day, continue searching separately; do not treat this grid candidate as 1:2.
9. Anchored mean reversion was tested and shows the same trade-off: high-frequency is deeply negative, stricter quality is near breakeven but low-frequency.
