# NY17 SMA50 Regime Intraday Candle RR2

- Regime: gap-aware NY17 daily HLC3 SMA50 / simple TR40 King Keltner position
- Regime begins only after the daily entry trading-day bar has completed
- Trigger: completed intraday candle pattern relative to EMA
- Entry: next 5m open; exit: fixed 2R with 5m adverse-stop first
- Controls: KST 08:00-23:59, one position, cap 3/day, cost 0.5

Selected config: `timeframe=15min, ema_length=40, signal_mode=aligned, session_mode=asia, risk_mult=2.0, max_hold_bars=144`

Final decision: **REJECTED**. Profitable chunks: 1/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 172 | 1.2113 | 514.9067 | 1.2475 | 280.7951 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 760 | 0.8094 | -254.8306 | 0.8453 | 293.0064 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 726 | 0.7765 | -288.7763 | 0.803 | 306.2894 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 772 | 0.8292 | -172.268 | 0.8726 | 256.0601 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 797 | 0.8533 | -657.9954 | 0.6936 | 672.6402 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 948 | 1.0172 | -382.2699 | 0.8462 | 385.9886 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 537 | 1.1828 | 742.1479 | 1.167 | 280.7951 | True |
| full | 2010-01-01 | 2026-06-17 | 4540 | 0.8859 | -1013.9922 | 0.9251 | 1754.0849 | False |

Intraday parameters were selected on 2026 and frozen historically.
