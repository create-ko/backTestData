# Asia Keltner Trailing Validation

- Candle trigger: next-bar break of the completed Keltner channel
- Trend: completed typical-price SMA slope
- Exit: initial ATR stop followed by completed center line
- Entry scope: Asia session within KST 08:00-23:59
- Execution: 5m adverse-stop first, one position, cap 3/day, cost 0.5
- Important: variable-R trend exit, not fixed 2R

Selected config: `timeframe=30min, ma_length=40, atr_length=40, band_mult=1.0, session_mode=asia, risk_mult=1.5, max_hold_bars=576`

Final decision: **CONDITIONAL_PASS**. Profitable chunks: 2/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 148 | 1.0423 | 1577.681 | 1.9179 | 307.0717 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 855 | 0.9105 | 202.0785 | 1.1056 | 221.5724 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 888 | 0.9497 | -106.774 | 0.9396 | 264.4398 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 944 | 1.014 | -101.7261 | 0.9344 | 276.3337 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 919 | 0.9839 | -205.8674 | 0.9125 | 353.8335 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 926 | 0.9936 | -607.9629 | 0.7789 | 623.5665 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 501 | 1.1035 | 1934.472 | 1.485 | 318.5925 | True |
| full | 2010-01-01 | 2026-06-17 | 5033 | 0.982 | 1114.22 | 1.0778 | 1234.374 | False |

The numeric parameters were selected only on 2026 and then frozen.
Research caveat: the Asia-only family was introduced after inspecting prior full-history session decomposition, so this is secondary exploration rather than pristine OOS evidence.
