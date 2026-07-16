---
name: gold-ktr-lot-sizing
description: Calculate Gold CFD KTR grid lot sizes from account risk, KTR, grid count, final stop distance, and equal-loss or declining-loss allocation. Use when sizing Gold/XAUUSD KTR grids, comparing 3- or 6-entry risk, or adapting the ktrlots.com formula to a custom stop structure.
---

# Gold KTR Lot Sizing

Use USD risk and Gold CFD point value unless the user provides broker-specific values.

1. Set total risk: `R = equity * risk_percent / 100`.
2. Use `V = $100` per point per 1.0 Gold lot only when it matches the broker contract.
3. Define each entry's distance to the final stop in KTR units.
4. Add round-trip cost per lot to each entry's dollar loss before calculating lot size.
5. Round lots down to the broker's permitted lot increment.

For formulas and the validated site inference, read [references/formulas.md](references/formulas.md).

## Required Inputs

- Equity and risk percent
- KTR in points
- Grid entry count and final stop location
- `point_value_per_lot`
- `round_trip_cost_points`
- Allocation mode: `equal_loss` or `declining_loss`

## Output

Return each entry's lot size, total lots, maximum modeled loss, and 1-KTR profit by entry. State that calculations are sizing estimates and must be checked against the broker's contract specification.
