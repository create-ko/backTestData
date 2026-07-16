# Walk-Forward Candle Trend Bucket RR2

- Base: shifted daily SMA trend, first-15m session range, completed 5m retest candle
- Monthly selector: enable buckets using only the preceding fixed lookback outcomes
- Exit: prior ADR20 risk, exact 2R, 0.5-point cost
- The selector observes all prior hypothetical base signals, including disabled buckets

Selected config: `scope=global, lookback_months=12, minimum_trades=20, pf_threshold=1.0, concurrency_cap=5`

Final decision: **CONDITIONAL_PASS**. Profitable chunks: 2/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 277 | 1.9507 | 2077.13 | 1.2393 | 1544.3608 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 395 | 0.4207 | -1030.0624 | 0.7304 | 1622.2574 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 704 | 0.7529 | -685.6784 | 0.8317 | 727.0695 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 253 | 0.2718 | -453.3854 | 0.7105 | 560.6051 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 705 | 0.7548 | -1171.7461 | 0.7888 | 1234.5405 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 860 | 0.9227 | 700.7294 | 1.1011 | 1063.5457 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 895 | 1.9714 | 4912.6428 | 1.2862 | 1544.3608 | True |
| full | 2010-01-01 | 2026-06-17 | 3812 | 0.7438 | 2272.4999 | 1.0581 | 4956.5435 | False |

Meta-parameters are selected on 2026; every monthly decision uses only earlier trades.
