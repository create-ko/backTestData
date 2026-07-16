# NY17 Daily King Keltner SMA50 with 5m Execution

- Daily signal and channel: completed NY17 SMA50 / simple TR40
- Entry order: active for the next NY17 trading session only
- SMA exit: active immediately after entry and updated at each NY17 boundary
- Same-5m entry/SMA touches: conservatively treated as entry then stop
- Carried-position gaps through SMA: adverse 5m opening price
- One position, round-trip cost 0.5

5m execution: 169 trades, net 2403.55, PF 1.7626, DD 414.68.
Positive chunks: 6/6. Same-5m round trips: 0.
Prior daily-OHLC model: 169 trades, net 2406.14, PF 1.7640.

The 5m result supersedes the daily-OHLC result for execution validity.

The subsequent 25-configuration and tail-risk audit is in `../ny17_daily_king_sma50_5m_robustness/REPORT.md`. It retained 25/25 six-chunk passes but found that the top five wins account for more than all historical net profit.
