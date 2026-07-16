# Intraday King Keltner RR2

- Trend: completed intraday typical-price SMA slope
- Entry: next signal-bar stop at center plus/minus ATR channel
- Exit: ATR risk with 2-point floor, exact 2R, 0.5 cost, 5m stop-first execution
- Controls: one position at a time and at most three entries per KST day

Selected config: `timeframe=1h, ma_length=20, atr_length=20, band_mult=1.0, risk_mult=2.0, max_hold_bars=144`

Final decision: **CONDITIONAL_PASS**. Profitable chunks: 2/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 237 | 1.669 | 2329.4457 | 1.5126 | 817.3188 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 1750 | 1.8637 | 173.9486 | 1.0277 | 341.7254 | True |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 1745 | 1.8663 | -367.5564 | 0.9316 | 496.9393 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 1675 | 1.7991 | -682.3292 | 0.8409 | 730.7312 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 1683 | 1.8019 | -688.9278 | 0.8969 | 729.3268 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 1730 | 1.8562 | -155.4695 | 0.9802 | 498.5802 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 773 | 1.7026 | 2931.6091 | 1.2993 | 817.3188 | True |
| full | 2010-01-01 | 2026-06-17 | 9356 | 1.8256 | 1211.2747 | 1.0301 | 2162.996 | True |

Parameters are selected on 2026 and remain fixed in all historical slices.
