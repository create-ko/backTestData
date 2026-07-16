# LEGACY REGIME TEST: Daily King Regime Intraday Candle RR2

> This run used the later-invalidated UTC SMA60 daily regime. The corrected NY17 SMA50 rerun is `result/ny17_sma50_regime_intraday_candle_rr2/REPORT.md` and is also rejected.

- Regime: gap-aware daily HLC3 SMA60 / simple TR40 King Keltner position
- Regime timing: active only after the daily entry bar has fully completed
- Trigger: completed intraday candle pattern relative to its EMA
- Entry: next 5m open; exit: ATR risk with 2-point floor and exact 2R
- Controls: adverse-stop first, KST 08:00-23:59, one position, cap 3/day, cost 0.5

Selected config: `timeframe=15min, ema_length=40, signal_mode=aligned, session_mode=asia, risk_mult=2.0, max_hold_bars=144`

Final decision: **REJECTED**. Profitable chunks: 1/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 173 | 1.2183 | 414.6157 | 1.1945 | 330.6728 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 784 | 0.8349 | -253.0124 | 0.8494 | 292.8684 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 729 | 0.7797 | -324.4864 | 0.7818 | 341.9996 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 788 | 0.8464 | -205.472 | 0.8519 | 279.3356 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 814 | 0.8715 | -590.9705 | 0.7292 | 604.3044 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 961 | 1.0311 | -405.4259 | 0.8393 | 403.4259 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 545 | 1.2004 | 648.4918 | 1.1433 | 330.6728 | True |
| full | 2010-01-01 | 2026-06-17 | 4621 | 0.9017 | -1130.8755 | 0.918 | 1777.3121 | False |

Intraday parameters were selected on 2026 and frozen historically.
Research caveat: the SMA60 daily regime was discovered during full-history exploration.
