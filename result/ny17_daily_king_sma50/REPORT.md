# NY17 Daily King Keltner SMA50

- Trading day: New York 17:00 to next New York 17:00, DST aware
- Trend: completed HLC3 SMA50 slope
- Entry: next trading-day stop at SMA50 plus/minus simple TR40
- Exit: next trading-day stop at latest completed SMA50
- Gap-aware fills, one position, round-trip cost 0.5

Daily-OHLC reference: 169 trades, net 2406.14, PF 1.7640, DD 414.68.
Authoritative chronological 5m execution: 169 trades, net 2403.55, PF 1.7626, DD 414.68.
Positive chunks: 6/6; positive years: 12/17.
Unseen 2019-2026 holdout: 79 trades, net 1919.43, PF 2.0487, DD 359.80.
Frequency: 0.0330 trades per trading day.

Training-only selection: on 2010-2018, SMA50 was the slowest MA length whose 25/25 TR/band neighbors were positive in all three training chunks.
Both holiday-partial handling variants retained 25/25 profitable six-chunk neighbors. The later 5m execution audit also retained 25/25, although the weakest individual chunk was only +2.91 points.

Tail-risk audit: the largest win supplied 44.37% of total net and the top five supplied 100.26%; removing the top five changed net to -6.23. Long trades made +3045.15 while short trades lost -641.60. See `../ny17_daily_king_sma50_5m_robustness/REPORT.md`.

Decision: parameter-stable but tail-dependent low-frequency swing research candidate on proper NY17 bars.
It still fails the original 1-3 entries/day requirement and requires prospective data before live deployment.
