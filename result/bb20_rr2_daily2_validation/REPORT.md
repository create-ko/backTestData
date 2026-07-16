# BB20/BB4 RR2 Daily-2 Validation

- Signal: 2-minute BB20 wick breakout followed by opposite BB4 pullback entry
- Exit: structural stop, fixed 2R target, maximum hold 20 bars
- Cost: 0.5 points round trip
- Frequency control: keep the first three entries of each trading day
- Pass rule: 2.0-3.0 entries per full trading day, positive net points, PF above 1.0
- Frequency interpretation: average across all trading days; every-day 2+ is reported separately

Final decision: **REJECTED**.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 348 | 2.4507 | 539.3451 | 3.1139 | 16.1115 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 2236 | 2.3813 | -1784.3783 | 0.2551 | 1784.5637 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 2203 | 2.3561 | -1936.4206 | 0.1943 | 1935.25 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 2027 | 2.1772 | -1633.1813 | 0.2095 | 1631.6674 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 2222 | 2.379 | -1739.3886 | 0.3068 | 1738.0579 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 2302 | 2.47 | -1700.0211 | 0.3153 | 1698.3153 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 1122 | 2.4714 | 238.1134 | 1.1895 | 363.9361 | True |
| full | 2010-01-01 | 2026-06-17 | 12112 | 2.3633 | -8555.2765 | 0.3476 | 9150.3567 | False |

No parameters are re-selected inside the historical chunks.
