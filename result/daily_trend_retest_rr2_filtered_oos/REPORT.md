# Daily Trend Session Retest RR2: 2026 Filter Selection

- Base family: prior completed daily close versus shifted SMA; first 15m session range; completed 5m breakout/retest; next 5m open entry.
- Stop: prior 20-day ADR fraction; target: fixed 2R; round-trip cost: 0.5.
- Base parameter candidates, direction, session set, and signal type were ranked using 2026 only.
- Historical chunks were not used to choose the selected configuration.

## Selected on 2026

- Parameter rank: 1; SMA 120; base signal either; retest window 6; ADR risk 0.5; hold 576 bars.
- Filters: direction both; sessions all; signal both.
- 2026: 300 trades, 2.1127/day, net 2926.60, PF 1.3180.

## Frozen historical validation

- Full: 10331 trades, net 5905.43, PF 1.0812, DD 4008.18.
- Profitable three-year chunks: 3/6; worst chunk -1092.15.
- Among all 52 2026-eligible variants, 0 later showed 6/6 profitable historical chunks. This count is diagnostic, not a selection rule.

## Decision

**REJECTED**. The 2026-selected row must retain positive full net/PF, 1-3 trades/day, and 6/6 profitable fixed chunks.
