# Daily Trend ADR Retest Expansion RR2

- Direction: previous completed daily close versus shifted daily SMA
- Confirmation: first 15m session range, then a completed 5m retest signal
- Risk: prior 20-day ADR fraction; target: exact 2R; round-trip cost: 0.5
- Selection frequency: average 1 to 3 trades per 2026 trading day

Selected config: `sma_length=120, signal_mode=either, retest_window=6, body_min=0.0, risk_fraction=0.5, risk_floor=1.5, max_hold_bars=576`

Final decision: **CONDITIONAL_PASS**. Profitable chunks: 3/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 300 | 2.1127 | 2926.6032 | 1.318 | 1631.6605 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 1683 | 1.7923 | -863.1673 | 0.9228 | 2128.9778 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 1911 | 2.0439 | 269.694 | 1.0282 | 878.0221 | True |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 1925 | 2.0677 | -1092.1518 | 0.8645 | 1400.5857 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 1909 | 2.0439 | -862.4017 | 0.929 | 1437.169 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 1950 | 2.0923 | 2455.634 | 1.1813 | 918.7342 | True |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 953 | 2.0991 | 5997.8238 | 1.3288 | 1631.6605 | True |
| full | 2010-01-01 | 2026-06-17 | 10331 | 2.0158 | 5905.4309 | 1.0812 | 4008.1833 | True |

Parameters are selected only on 2026 and remain fixed in every historical slice.
