# Alternative Fixed-2R Strategy Search

## Constraints

- Instrument: XAUUSD
- Selection period: 2026-01-01 through 2026-06-16
- Required frequency: 2.0-3.0 entries per full trading day
- Exit target: fixed 2R
- Round-trip cost: 0.5 points
- Historical validation: fixed parameters in three-year slices and 2010-2026 overall

## Candidates

| Candidate | 2026 entries/day | 2026 net | 2026 PF | Full entries/day | Full net | Full PF | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Anchored day-mean wick reversal | 1.4577 | 11.3525 | 1.0210 | 1.1114 | -1544.5680 | 0.7420 | Frequency fail |
| Three-session opening-range reversal | 2.0282 | -46.4625 | 0.9561 | n/a | n/a | n/a | 2026 performance fail |
| Three-session SMA direction, session exit | 2.5352 | 292.6895 | 1.1483 | 2.5489 | -6038.9940 | 0.6692 | Historical fail |
| Walk-forward session direction | 2.5352 | 488.4910 | 1.1180 | 2.5489 | -5545.8530 | 0.8340 | Historical fail |
| Prior-day trend + ADR session entries | 2.5352 | 2222.6408 | 1.1916 | 2.4888 | 4535.0956 | 1.0500 | Conditional pass |

## Best Alternative Candidate

The best new candidate is the prior-day trend plus ADR session strategy:

- One scheduled opportunity at the Asia, Europe, and US-open sessions.
- Direction follows the previous completed day's close relative to its shifted 120-day SMA.
- Stop distance is 50% of the previous completed 20-day ADR, with a 0.8-point floor.
- Target is exactly 2R and maximum holding time is 1,440 two-minute bars.
- A maximum of ten concurrent positions is enforced.

It passes 2026 and the 2010-2026 aggregate, and two neighboring parameter sets also pass the aggregate. However, only three of six historical slices are profitable and most aggregate profit comes from 2025-2026. It is a conditional research candidate, not an unconditional live-trading recommendation.

## Conclusion

One alternative satisfies frequency, 2026 profitability, and aggregate full-history profitability at the same time. Its edge is regime-dependent: pre-2025 results are negative in aggregate, while 2025-2026 contributes most of the final profit. Cost sensitivity remains positive at 0.7 points but turns negative at 1.0 point.
