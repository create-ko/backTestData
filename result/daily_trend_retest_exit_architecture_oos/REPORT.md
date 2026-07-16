# Daily Trend Session Retest: Exit Architecture OOS

- Entry family unchanged: completed daily trend, first 15m session range, completed 5m breakout/retest, next 5m open.
- Exit search: target 1R to 3R; optional 0.75R/1R breakeven trigger; time exit 144/288/576 bars.
- Stop gaps use adverse 5m opening prices; ambiguous bars use stop first; cost is 0.5 round trip.
- All parameters selected on 2026 only, then frozen for 2010-2026.

## Selected on 2026

- SMA 60; signal either; retest 3; body 0.0; ADR risk 0.5.
- Hold 576; target 3.0R; breakeven trigger 0.0R (0 means disabled).
- 295 trades, 2.0775/day, net 3787.01, PF 1.4145.

## Frozen validation

- Full: 10339 trades, 2.0174/day, net 8812.58, PF 1.1168, DD 3004.67.
- Profitable chunks: 3/6; worst chunk -650.74.
- Top-12 2026 rows with 6/6 profitable chunks: 0.
- Cost 0.0 gives 6/6 chunks; cost 0.5 gives 3/6; cost 1.0 gives 2/6.
- Every chunk stays positive only below a 0.1593-point round-trip cost; the required cost is 0.5.

## Decision

**REJECTED**. A pass requires 1-3 trades/day in every fixed period, positive full net/PF, and 6/6 profitable chunks.
