# Three-Session Volatility-Scaled RR2

- One scheduled entry at each Asia, Europe, and US-open session
- Direction selected on 2026: long, short, or prior 120-SMA state
- Stop distance: prior median 2-minute range times a fixed multiplier with a fixed floor
- Target: exactly 2R; cost: 0.5 points; same-bar ambiguity: stop-first

Selected config: `direction_rule=short, volatility_mult=15.0, risk_floor=0.8, max_hold_bars=480`

Final decision: **REJECTED**.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 360 | 2.5352 | 1208.7255 | 1.1281 | 1475.6572 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 2392 | 2.5474 | -2144.5405 | 0.8019 | 2348.088 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 2382 | 2.5476 | -698.6615 | 0.9083 | 898.5405 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 2375 | 2.551 | -1350.9255 | 0.7979 | 1344.343 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 2382 | 2.5503 | -1657.8597 | 0.8414 | 1702.859 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 2378 | 2.5515 | -2156.6253 | 0.8209 | 2441.6253 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 1154 | 2.5419 | -1499.0472 | 0.9243 | 4205.2825 | False |
| full | 2010-01-01 | 2026-06-17 | 13063 | 2.5489 | -9507.6597 | 0.859 | 12223.0925 | False |

No parameter is re-selected in historical slices.
