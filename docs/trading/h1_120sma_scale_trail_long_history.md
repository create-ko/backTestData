# H1 120SMA Scale-Out Trail: Long-History Validation

## Candidate

- Setup: hourly double-Bollinger breakout.
- Entry: after the breakout, wait for a touch of the lower-timeframe 120SMA.
- Tested execution timeframe: 10 minutes.
- Entries: three equal units at the 120SMA and 10-point adverse spacing.
- Exit: after price reaches breakeven, arm a 5-point trailing stop; each unit carries a 0.4-point round-trip cost.
- Test range: 2010-01-01 through 2026-06-17.

## Result

The 10-minute candidate produced 1,021 trades, 0.199 trades/day, +845.10 points, PF 3.487, and 76.07 points of maximum drawdown. Three-year chunk results were -24.61P, +72.48P, -44.85P, +44.36P, +42.01P, and +755.71P. The final 2025-2026 chunk contributes most of the total profit, so this is not yet a robust live-trading candidate.

The SMA60 variant increased frequency to 0.320 trades/day but reduced total profit to +604.67P and had negative results in each chunk before 2022-2025. Extending the wait window to 24 or 48 hours increased frequency to 0.557 and 0.607 trades/day, but the 2010-2024 chunks remained mostly negative.

## Decision

The original reversal basket is rejected for long-history use. This scale-out candidate is useful as a research direction, but it does not satisfy the requested 1-3 trades/day target and should not be deployed without further out-of-sample validation.
