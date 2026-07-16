# Fixed RR2 Candidate Validation

- Selection window: 2026-01-01 to 2026-06-17
- Data: XAUUSD 2-minute signals with intrabar execution inherited from component tests
- Orders: structural stop and fixed 2R target; round-trip cost 0.5 points
- Controls: minimum risk 2.0 / 1.5 points, dedupe, max 5 concurrent positions, max 3 entries per day
- Fixed candidate: immediate session sweep + opening-range failed breakout + PDH/PDL double sweep

## Result

Final decision: **REJECTED**. The candidate passed the 2026 selection window but failed fixed-parameter historical validation.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 257 | 1.8099 | 148.992 | 1.2308 | 98.4535 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 465 | 0.4952 | -211.867 | 0.6149 | 212.829 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 426 | 0.4556 | -123.598 | 0.7186 | 133.324 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 346 | 0.3716 | -95.103 | 0.6609 | 101.607 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 683 | 0.7313 | -232.2275 | 0.7298 | 236.518 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 740 | 0.794 | -118.296 | 0.8643 | 178.842 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 829 | 1.826 | 437.966 | 1.2705 | 112.4825 | True |
| full | 2010-01-01 | 2026-06-17 | 3489 | 0.6808 | -340.6665 | 0.9262 | 837.444 | False |

## Interpretation

The 2026 edge is concentrated in the recent high-volatility gold regime. Every earlier three-year chunk loses money, so the strategy is not accepted for live use. No parameters were re-selected inside the historical chunks.

Historical chunk pass count: 1/6.
