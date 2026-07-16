# Daily Trend ADR Robustness

Full-period passing configurations: 3/6.

## Parameter Neighbors

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selected | 2010-01-01 | 2026-06-17 | 0 | 2.4888 | 4535.0956 | 1.05 | 6366.2489 | True |
| sma60_r50_h1440 | 2010-01-01 | 2026-06-17 | 0 | 2.5182 | 2797.8051 | 1.0304 | 5958.2061 | True |
| sma120_r50_h720 | 2010-01-01 | 2026-06-17 | 0 | 2.4888 | 1916.1075 | 1.0254 | 5826.9477 | True |
| sma60_r30_h720 | 2010-01-01 | 2026-06-17 | 0 | 2.5182 | -1788.5745 | 0.9699 | 4619.072 | False |
| sma120_r30_h720 | 2010-01-01 | 2026-06-17 | 0 | 2.4888 | -1302.5227 | 0.9778 | 4665.1226 | False |
| sma20_fade_r30_h1440 | 2010-01-01 | 2026-06-17 | 0 | 2.5393 | -4334.949 | 0.9329 | 6254.2519 | False |

## Cost Sensitivity

round_trip_cost,net_points,profit_factor,max_drawdown_points
0.3,7086.0956,1.0795,4432.2489
0.5,4535.0956,1.05,6366.2489
0.7,1984.0956,1.0215,8300.2489
1.0,-1842.4044,0.9805,11209.36

