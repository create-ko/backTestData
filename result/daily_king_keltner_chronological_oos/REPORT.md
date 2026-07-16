# Daily King Keltner Chronological OOS

## Fixed chronological holdout

The parameter grid is selected using only 2010-2018. Eligibility requires all three training chunks to be profitable.
Selected config: SMA 50, simple TR 20, band 0.75.
Training: 137 trades, net 525.36, PF 1.3690.
Unseen 2019-2026 holdout: 126 trades, net 1617.76, PF 1.7321, DD 443.91.
Positive holdout chunks: 2/3.

## Three-year walk-forward

Each test chunk uses the single best eligible configuration from only the immediately preceding three-year chunk.
Combined OOS: 188 trades, net 1741.65, PF 1.6197, DD 529.23.
Positive OOS chunks: 4/5.

No test-period result participates in its parameter selection.
This validates the low-frequency family chronologically, but does not solve the 1-3 entries/day requirement.
