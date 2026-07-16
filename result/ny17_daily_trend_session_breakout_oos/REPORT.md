# NY17 Daily Trend Session Close Breakout OOS

- Trend uses only the latest completed 17:00 America/New_York daily candle.
- Signal is a completed 5m/15m candle close beyond the session opening range in the daily trend direction.
- Entry is the next 5m open; one position; maximum three entries per day.
- Risk is completed simple daily TR average times a fraction; target 2R/3R; adverse gaps and stop-first ambiguity; cost 0.5.
- Parameters selected on 2026 only and frozen historically.

## Selected on 2026

- 5min bars, opening 3 bars, body 0.0; NY17 SMA 50 price trend.
- TR 40 x 0.3 risk; target 3.0R; hold 72 5m bars.
- 231 trades, 1.6268/day, net 1009.32, PF 1.3654.

## Frozen validation

- Full: 8235 trades, 1.6068/day, net -2224.50, PF 0.9156, DD 3791.51.
- Profitable chunks: 1/6; worst chunk -920.63.
- Top-12 2026 rows with 6/6 chunks: 0.
- Cost 0/0.5/1.0 profitable chunks: 3/1/1 of 6.

## Decision

**REJECTED**. A pass requires 1-3 trades/day in every fixed period, positive full net/PF, and 6/6 profitable chunks.
