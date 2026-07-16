# Daily Trend Candle Reclaim RR2

- Direction: slope of a completed KST daily typical-price SMA
- Candle trigger: completed bullish/bearish intraday candle reclaims its EMA
- Entry: next 5m open after the signal candle
- Exit: ATR risk with 2-point floor, exact 2R, 5m adverse-stop first
- Controls: KST 08:00-23:59, one position, cap 3/day, cost 0.5

Selected config: `timeframe=15min, daily_length=80, intraday_length=10, session_mode=asia, risk_mult=1.0, max_hold_bars=72`

Final decision: **REJECTED**. Profitable chunks: 1/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 201 | 1.4155 | 454.0052 | 1.3182 | 184.1418 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 1157 | 1.2322 | -504.4529 | 0.7287 | 504.0549 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 1189 | 1.2717 | -651.7746 | 0.6444 | 654.2226 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 1130 | 1.2137 | -563.2981 | 0.6557 | 569.4638 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 1331 | 1.4251 | -816.9535 | 0.6609 | 825.472 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 1386 | 1.4871 | -342.9333 | 0.851 | 393.98 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 716 | 1.5771 | 236.3025 | 1.0709 | 274.8676 | True |
| full | 2010-01-01 | 2026-06-17 | 6909 | 1.3481 | -2643.1099 | 0.8023 | 3137.9419 | False |

Parameters were selected on 2026 and frozen for every historical slice.
