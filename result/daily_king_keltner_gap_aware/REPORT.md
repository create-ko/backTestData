# Daily King Keltner Gap-Aware Validation

- Daily UTC bars built from XAUUSD 5m data
- Trend: slope of typical-price SMA40
- Entry: next-day stop at SMA40 plus/minus simple TR-average40
- Exit: next-day stop at current SMA40
- Gap rule: adverse next-day open is used when it crosses the stop
- One position at a time; round-trip cost 0.5 points

Full: 251 trades, net 1492.59, PF 1.3932, DD 410.38.
Positive calendar years: 10/17. Positive 3-year chunks: 5/6.
Average frequency: 0.0490 trades per trading day.

This is the robust low-frequency benchmark; it does not meet the 1-3 entries/day requirement.
