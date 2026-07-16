# Daily Filter Intraday Keltner RR2

- Base: completed 1h King Keltner trend breakout, ATR2 risk, exact 2R
- Daily filter: only prior completed KST daily candles and SMA state
- Execution: 5m stop-first, one position, at most three KST-day entries, cost 0.5

Selected config: `sma_length=120, slope_days=5, daily_mode=none, distance_min=0.25, candle_mode=any, session_mode=all`

Final decision: **CONDITIONAL_PASS**. Profitable chunks: 2/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 216 | 1.5211 | 2968.0015 | 1.8052 | 394.3554 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 1466 | 1.5612 | 223.1835 | 1.0419 | 333.024 | True |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 1663 | 1.7786 | -307.8294 | 0.94 | 452.3364 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 1599 | 1.7175 | -676.9375 | 0.8366 | 724.1503 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 1614 | 1.7281 | -877.5105 | 0.8643 | 911.5824 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 1687 | 1.8101 | -196.3475 | 0.9746 | 524.0701 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 750 | 1.652 | 3553.9073 | 1.3977 | 394.3554 | True |
| full | 2010-01-01 | 2026-06-17 | 8779 | 1.713 | 1718.4659 | 1.0455 | 2353.3838 | True |

Daily filter parameters are selected on 2026 and fixed in all historical slices.
