# NY17 SMA50 5m Robustness and Tail-Risk Audit

## Central 5m execution

- 169 trades, net 2403.55, PF 1.7626, DD 414.68.
- Round-trip cost 0.5; NY17 DST-aware daily signals; chronological 5m stop execution.

## 5m parameter neighborhood

- Six profitable three-year chunks: 25/25 configurations.
- Full-net positive: 25/25; PF range 1.7195 to 2.0921.
- Worst single chunk across all neighbors: 2.91 points.

## Resampling risk

- IID trade bootstrap (20,000): loss probability 3.79%, net p05 169.13, DD p95 1184.92, DD p99 1565.74.
- Calendar-year block bootstrap (10,000): loss probability 0.53%, net p05 567.12, DD p95 613.31, DD p99 764.55.

## Tail concentration

- Largest win contributes 44.37% of total net; top five contribute 100.26%.
- Positive rolling 30-trade windows: 88.57%; longest losing streak: 11.
- Trend following is expected to be right-tail dependent, but this concentration limits confidence in the historical point estimate.

## Decision

Retain only as a low-frequency research and forward-paper candidate. It is not evidence for a 1-3 entries/day strategy and is not ready for live deployment.
