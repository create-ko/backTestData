# Corrected H1 Breakout / 2m SMA120 Retest

- Long-only completed H1 double-Bollinger breakout
- First 2m retest of prior-bar-known SMA120 within six hours
- Three buy-limit units at 10-point spacing; hard stop 5 points below unit 3
- Close-confirmed 5-point trailing stop; one position at a time
- Gap-aware fills and 0.5-point round-trip cost per filled unit

Full: 751 trades, 0.1465/day, net 175.82, PF 1.0387, DD 418.15.
Positive 3-year chunks: 5/6.

This corrects same-bar SMA look-ahead and overlapping independent trades in the legacy result.
