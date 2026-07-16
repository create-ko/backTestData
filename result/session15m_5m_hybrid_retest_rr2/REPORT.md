# 15m Range + 5m Hybrid Retest RR2

- Session range: first completed 15 minutes
- Trigger: 5m close outside the range
- Entry signal: continuation retest or failed-break return, whichever first matches prior-day trend
- Entry: next 5m open; stop: signal wick plus ADR-scaled buffer; target: exact 2R
- Direction: previous completed daily close versus shifted daily SMA
- Cost: 0.5 points; same-bar ambiguity: stop-first; one trade per session

Selected config: `sma_length=60, retest_window=12, body_min=0.35, buffer_fraction=0.0, min_risk=1.5, max_hold_bars=24`

Final decision: **REJECTED**. Profitable chunks: 0/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 290 | 2.0423 | 42.205 | 1.031 | 241.6335 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 876 | 0.9329 | -329.656 | 0.7637 | 339.96 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 623 | 0.6663 | -232.142 | 0.7456 | 254.881 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 389 | 0.4178 | -193.953 | 0.6268 | 199.283 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 952 | 1.0193 | -563.723 | 0.6718 | 597.954 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 1135 | 1.2178 | -558.772 | 0.7211 | 564.617 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 851 | 1.8744 | -70.5505 | 0.9748 | 334.1025 | False |
| full | 2010-01-01 | 2026-06-17 | 4826 | 0.9417 | -1948.7965 | 0.7915 | 2222.175 | False |
