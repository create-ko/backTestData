# Walk-Forward Session Direction RR2

- Scheduled Asia, Europe, and US-open entries
- Direction uses only completed prior hypothetical long/short outcomes
- Fixed 2R target, volatility-scaled stop, 0.5-point cost, five-position cap

Selected config: `volatility_mult=6.0, risk_floor=0.8, max_hold_bars=120, lookback=120, scope=session`

Final decision: **REJECTED**.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 360 | 2.5352 | 488.491 | 1.118 | 464.318 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 2392 | 2.5474 | -946.272 | 0.8217 | 955.924 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 2382 | 2.5476 | -864.019 | 0.7856 | 905.255 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 2375 | 2.551 | -1256.862 | 0.6523 | 1255.506 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 2382 | 2.5503 | -1262.439 | 0.7726 | 1350.3185 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 2378 | 2.5515 | -1419.728 | 0.7786 | 1604.123 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 1154 | 2.5419 | 203.467 | 1.0239 | 605.1055 | True |
| full | 2010-01-01 | 2026-06-17 | 13063 | 2.5489 | -5545.853 | 0.834 | 6159.819 | False |

The walk-forward rule and parameters remain fixed in all historical slices.
