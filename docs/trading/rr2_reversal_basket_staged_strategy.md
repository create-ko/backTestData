# 2m RR2 Reversal Basket

This is the recommended alternative after changing the requested frequency to
1-3 trades per day.

## Portfolio rule

- Chart/data: XAUUSD Gold CFD, 2-minute bars.
- Target: fixed 2R for every component trade.
- Maximum new trades per KST day: 3.
- Maximum simultaneous positions: 5.
- Duplicate entries at the same 2-minute time, direction, price, and stop are
  reduced to one trade.
- The component signals are independent reversal setups; the basket is the
  portfolio strategy.

## Components

1. Immediate session sweep reversal with initial risk at least 2 points.
2. Opening-range failed-breakout reversal with initial risk at least 1.5
   points.
3. Previous-day high/low double-sweep reversal.

Each component enters on the next 2-minute open after confirmation, places the
stop beyond the confirmation candle with a 0.2-point buffer, and calculates the
target as entry plus/minus two times the initial risk. CFD commission and
slippage must be added in NinjaTrader separately.

## Staged evidence

| Period | Trades | Trades/day | Net points | PF | Max DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-01 to 2026-06-17 | 257 | 1.8099 | +148.9920 | 1.2308 | 98.4535 |
| 2024-01 to 2026-06-17 | 1,142 | 1.4909 | +431.3560 | 1.2138 | 112.4825 |
| 2023-01 to 2026-06-17 | 1,331 | 1.2381 | +370.9260 | 1.1671 | 140.3850 |

The staged runner is
`src/scripts/138_2m_rr2_reversal_basket_staged.py`. It filters precomputed
component trades to the selected date range, deduplicates them, applies the
portfolio and daily caps, and writes yearly/monthly reports.
