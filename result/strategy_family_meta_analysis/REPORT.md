# Strategy Family Meta-Analysis

- Six independently tested candle/trend or reversal families are aligned by entry month and fixed three-year chunks.
- Component families and portfolio priority are ranked with 2026 only.
- The chosen portfolio enforces a maximum of three accepted entries per day; single-position and concurrent modes are both considered on 2026.

## 2026 selection

- Top component families: session_breakout, retest_3r.
- Chosen portfolio: retest_3r__session_breakout__daily_cap3.
- 2026: 352 trades, 2.4789/day, net 3568.35, PF 1.4594, positive months 100.00%.

## Frozen historical validation

- Full: 12710 trades, 2.4800/day, net 3231.34, PF 1.0472, DD 3937.50.
- Profitable chunks: 2/6; frequency-valid chunks: 6/6.
- Making every chunk non-negative with the low-frequency NY17 swing requires at least 22.51x swing exposure versus 1x portfolio exposure.
- That overlay is not accepted because the swing result is already concentrated in five outlier wins and scaling it multiplies the tail risk.

## Regime and research limit

- 2025-2026 mean daily TR was 86.48 points / 2.13% of price, versus prior chunk ranges of 14.46-27.57 points / 1.15-1.56%.
- Its trend efficiency was 0.1004, the highest fixed chunk in the sample.
- Repeated strategy redesign after inspecting 2010-2025 failures means those years are now research data, not a fresh independent holdout.

## Decision

**REJECTED**. Acceptance requires all six chunks to pass performance and frequency without a leveraged swing overlay.
