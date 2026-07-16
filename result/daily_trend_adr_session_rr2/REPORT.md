# Daily Trend ADR Session RR2

- Direction: prior completed day close versus prior daily SMA
- Risk: prior 20-day ADR times a fixed fraction, with a fixed floor
- Entries: first Asia, Europe, and US-open opportunity
- Exit: exact 2R target, 0.5-point cost, stop-first ambiguity handling

Selected config: `sma_length=120, direction_mode=trend, risk_fraction=0.5, risk_floor=0.8, max_hold_bars=1440, concurrency_cap=10`

Final decision: **CONDITIONAL_PASS**.
Profitable three-year slices: 3/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 360 | 2.5352 | 2222.6408 | 1.1916 | 2719.8204 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 2084 | 2.2194 | -1098.4327 | 0.9206 | 2773.8052 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 2382 | 2.5476 | 173.5057 | 1.0144 | 1052.3382 | True |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 2375 | 2.551 | -1506.8017 | 0.8496 | 1982.0345 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 2382 | 2.5503 | -1457.7528 | 0.9045 | 2220.7199 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 2378 | 2.5515 | 945.5697 | 1.0548 | 1251.0057 | True |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 1154 | 2.5419 | 7479.0075 | 1.3361 | 2719.8204 | True |
| full | 2010-01-01 | 2026-06-17 | 12755 | 2.4888 | 4535.0956 | 1.05 | 6366.2489 | True |

Daily features are shifted by one completed trading day; parameters stay fixed in all historical slices.
