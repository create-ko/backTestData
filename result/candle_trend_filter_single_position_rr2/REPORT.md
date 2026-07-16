# Candle Trend Filter Single Position RR2

- Base signal: daily SMA120 trend plus first-15m range and completed 5m retest
- Quality candidates: trend distance, prior daily candle, and five-day SMA slope
- Risk: prior ADR20 times 0.50, minimum 1.5; target: exact 2R; cost: 0.5
- Execution: one position at a time

Selected config: `max_hold_bars=144, trend_strength_min=0.0, candle_mode=any, previous_body_min=0.0, slope_mode=any`

Final decision: **REJECTED**. Profitable chunks: 2/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 183 | 1.2887 | 926.5145 | 1.2499 | 525.6858 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 1008 | 1.0735 | -385.4113 | 0.9051 | 592.5292 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 1126 | 1.2043 | -469.0617 | 0.8704 | 636.5864 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 1167 | 1.2535 | -914.558 | 0.7158 | 933.1312 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 1148 | 1.2291 | -443.9081 | 0.902 | 551.5451 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 1149 | 1.2328 | 495.6808 | 1.102 | 291.1637 | True |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 576 | 1.2687 | 1633.569 | 1.2212 | 525.6858 | True |
| full | 2010-01-01 | 2026-06-17 | 6174 | 1.2047 | -83.6894 | 0.997 | 2524.0235 | False |

The filter is selected on 2026 only and then fixed for all historical slices.
