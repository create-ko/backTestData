# Session-Focused Keltner Trailing

- Candle trigger: next-bar break of the completed HTF Keltner channel
- Trend: completed typical-price SMA slope
- Exit: initial ATR stop followed by completed HTF center line
- Controls: KST 08:00-23:59, one position, cap 3/day, cost 0.5
- Important: variable-R trend exit, not fixed 2R

Selected config: `timeframe=1h, ma_length=20, atr_length=20, band_mult=1.0, session_mode=all, risk_mult=2.0, max_hold_bars=576`

Final decision: **CONDITIONAL_PASS**. Profitable chunks: 1/6.

| period | start | end | trades | trades_per_trading_day | net_points | profit_factor | max_drawdown_points | passed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selection_2026 | 2026-01-01 | 2026-06-17 | 154 | 1.0845 | 1937.4275 | 1.9007 | 459.7963 | True |
| 3y_chunk | 2010-01-01 | 2013-01-01 | 1312 | 1.3972 | -60.7426 | 0.9834 | 333.5735 | False |
| 3y_chunk | 2013-01-01 | 2016-01-01 | 1318 | 1.4096 | -239.6992 | 0.9238 | 571.6719 | False |
| 3y_chunk | 2016-01-01 | 2019-01-01 | 1226 | 1.3169 | -362.0552 | 0.8521 | 450.7451 | False |
| 3y_chunk | 2019-01-01 | 2022-01-01 | 1284 | 1.3747 | -291.8219 | 0.9266 | 366.7333 | False |
| 3y_chunk | 2022-01-01 | 2025-01-01 | 1316 | 1.412 | -676.5073 | 0.8556 | 924.1771 | False |
| 3y_chunk | 2025-01-01 | 2026-06-17 | 565 | 1.2445 | 2607.0139 | 1.5065 | 459.7963 | True |
| full | 2010-01-01 | 2026-06-17 | 7021 | 1.37 | 976.1878 | 1.0423 | 1974.6126 | True |

Only 2026 selected the parameters; all historical chunks use the frozen configuration.
