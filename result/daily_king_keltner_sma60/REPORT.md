# REJECTED: Daily King Keltner SMA60 UTC-Calendar Candidate

> Boundary audit found that the UTC calendar aggregation contained 873 short partial daily bars, mostly Sunday opens. On proper New York 17:00 trading-day bars, SMA60 lost its parameter-neighborhood robustness. Use the NY17 SMA50 candidate instead.

- Daily UTC XAUUSD bars
- Trend: completed HLC3 SMA60 slope
- Entry: next-day stop at SMA60 plus/minus simple TR-average40
- Exit: next-day stop at the latest completed SMA60
- Gap-aware fills, one position, 0.5-point round-trip cost

2026 selection window: 3 trades, net 204.96, PF 1.6761.
Full: 190 trades, net 2414.97, PF 1.7654, DD 432.90.
Positive years: 12/17; positive 3-year chunks: 6/6.
Frequency: 0.0371 trades per trading day.

SMA60 neighborhood: 25/25 ATR-length/band combinations were positive in all chunks.
Neighborhood full PF range: 1.7050-2.1172.
Worst result among every SMA60 config's weakest chunk: 6.34 points.

Decision: strong low-frequency research candidate, but not a clean 2026-selected result because 2026 contains only three trades.
It also fails the requested 1-3 entries/day requirement and needs genuinely future data before live confirmation.

Chronological audit: a stability-and-turnover rule using only 2010-2018 selected SMA60/TR40/1ATR. The unseen 2019-2026 holdout returned 88 trades, +1966.55 points, PF 2.1346, and 3/3 profitable chunks. The rule was designed during this research process, so this is supportive evidence rather than pristine prospective confirmation.
