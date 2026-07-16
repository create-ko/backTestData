# New Candidate: H1 Breakout, 120SMA Retest, 24-Hour Validity

## Rules

- Detect an hourly double-Bollinger breakout.
- Keep the breakout valid for up to 24 hours.
- On the 10-minute chart, enter when price first touches the 120SMA.
- Place three equal entries at the SMA and 10-point adverse spacing.
- After price reaches breakeven, activate a 5-point trailing stop.
- Include 0.4 points of round-trip cost per filled unit.

## Full test

The 2010-01-01 to 2026-06-17 test produced 2,852 trades, 0.5565 trades/day, +1,600.95 points, PF 2.5892, and 360.09 points maximum drawdown.

Three-year chunks were -114.69P (2010-2013), -11.31P (2013-2016), -168.49P (2016-2019), +1.42P (2019-2022), -10.87P (2022-2025), and +1,904.88P (2025-2026). The apparent edge is therefore concentrated in the latest period and is not stable enough for live use.

## Rejected new family

The independent 10-minute EMA20/EMA50 + Donchian breakout + EMA pullback strategy produced 6,803 trades, -3,686.35 points, and PF 0.6767 on the full period. It is rejected.

## Decision

This is a research candidate, not a production strategy. No tested new strategy currently satisfies both long-history stability and the desired 1-3 trades/day frequency.
