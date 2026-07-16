# Formula Reference

## Inferred ktrlots.com Gold Formula

For Gold, screenshots imply `V = $100` per point per 1.0 lot.

Let `N` be entry count, `i` be a 1-based entry number, `K` KTR points, and `R` total risk dollars.

```text
D_i = (N - i + 1) * K
```

### Equal Loss

```text
L_i = (R / N) / (D_i * V)
```

### Declining Loss

```text
W_i = 2^(N-i)
L_i = [R * W_i / (2^N - 1)] / (D_i * V)
```

This allocates loss budget from earliest to latest entry in a 50%, 25%, 12.5%, ... pattern.

## Custom Grid Formula

Use a custom KTR stop offset rather than the site's implied `N * KTR` stop.

For each entry, define `d_i` as its KTR distance to the actual stop. With cost `C` points per completed lot:

```text
loss_per_lot_i = d_i * K * V + C * V
```

Equal loss:

```text
L_i = (R / N) / loss_per_lot_i
```

Declining loss:

```text
L_i = [R * 2^(N-i) / (2^N - 1)] / loss_per_lot_i
```

For a six-entry, 1-KTR grid with a final stop at `E1 - 5.5KTR` (long) or `E1 + 5.5KTR` (short):

```text
d = [5.5, 4.5, 3.5, 2.5, 1.5, 0.5]
```

For a three-entry grid with a final stop at `E1 - 2.5KTR` or `E1 + 2.5KTR`:

```text
d = [2.5, 1.5, 0.5]
```
