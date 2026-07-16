# MTF Trend Candle Pullback RR2

- Trend: only completed 15m EMA state and slope
- Entry: first 5m EMA pullback rejection/engulfing candle per KST day/session, next-bar open
- Exit: signal-wick ATR stop, exact 2R, 0.5-point cost, stop-first ambiguity
- Execution: one position at a time; average frequency target 1 to 3 per trading day

Selected config: `ema_fast=20, ema_slow=50, slope_bars=3, pattern=either, wick_mult=1.5, touch_atr=0.25, stop_buffer_atr=0.25, max_risk_atr=3.0, max_hold_bars=24`

Final decision: **REJECTED**. Profitable chunks: 0/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 142 | 1.0 | 166.4745 | 1.2207 | 173.4733 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 660 | 0.7029 | -316.295 | 0.6163 | 314.8589 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 448 | 0.4791 | -197.5705 | 0.6035 | 206.7607 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 374 | 0.4017 | -207.263 | 0.4865 | 212.7352 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 629 | 0.6734 | -355.9903 | 0.6193 | 367.272 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 749 | 0.8036 | -370.2467 | 0.6675 | 372.4341 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 446 | 0.9824 | -15.4212 | 0.9901 | 221.99 | False |
| full | 2010-01-01 | 2026-06-17 | 3306 | 0.6451 | -1462.7867 | 0.7258 | 1635.7355 | False |

Parameters are selected on 2026 and remain fixed in every historical slice.
