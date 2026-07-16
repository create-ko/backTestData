# Anchored Mean RR2 Daily-2 Full Validation

- Signal: wick stretch from the expanding KST day mean, then candle reclaim toward the mean
- Confirmation: price-follow bias and body-35 close-extreme displacement
- Entry: next 2-minute open after at least 20 anchor bars and 1.6 median-range stretch
- Exit: signal-extreme stop plus 0.2 points, fixed 2R target, maximum hold 30 bars
- Risk bounds: 0.8-8.0 points; round-trip cost: 0.5 points
- Frequency: retain the first three entries per trading day; required average: 2.0-3.0

Final decision: **REJECTED**.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 207 | 1.4577 | 11.3525 | 1.021 | 80.86 | False |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 1047 | 1.115 | -475.723 | 0.5361 | 477.272 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 887 | 0.9487 | -338.331 | 0.5692 | 343.777 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 587 | 0.6305 | -156.895 | 0.6322 | 156.341 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 1125 | 1.2045 | -342.9955 | 0.6908 | 348.5375 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 1298 | 1.3927 | -359.1855 | 0.718 | 388.9785 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 752 | 1.6564 | 128.562 | 1.094 | 91.7875 | False |
| full | 2010-01-01 | 2026-06-17 | 5696 | 1.1114 | -1544.568 | 0.742 | 1748.1045 | False |

The 2026-selected parameters remain fixed in every historical slice.
