# Bb20WickBb4Rr2Xauusd

This is the NinjaTrader 8 port of the current-regime 2-minute fixed 1:2
research candidate.

## Rule

- Primary chart: XAUUSD / Gold CFD, 2 minutes.
- Long setup: the bar high is above BB20 with multiplier 2, then submit a
  limit order at the lower BB4 band calculated from opens with multiplier 4.
- Short setup: the bar low is below BB20 with multiplier 2, then submit a
  limit order at the upper BB4 band calculated from opens with multiplier 4.
- A limit order remains active for 30 bars.
- Stop: the extreme from the breakout bar through the fill bar plus/minus
  0.5 points.
- Target: exactly 2 times the initial risk.
- Risk bounds: 0.8 to 4.0 points.
- Maximum holding period: 20 bars.
- Entry window: KST 09:00 to 18:00.

## Current-regime gate

The research candidate is regime-dependent. By default, the strategy permits
trades only when the most recent completed daily close before the current month
is at least 3772.782. Set `UsePriorMonthGate=false` to disable this gate for
diagnostic comparison, not as a production recommendation.

## Installation and testing

Copy `Bb20WickBb4Rr2Xauusd.cs` into:

```text
Documents\NinjaTrader 8\bin\Custom\Strategies\
```

Compile it in the NinjaScript Editor, then run Strategy Analyzer on a 2-minute
Gold CFD series. Configure the broker-specific commission and slippage; the
Python research used a 0.5-point round-turn cost, while NinjaTrader applies
the configured instrument/account settings.

At termination, yearly and monthly CSV reports are written to:

```text
Documents\NinjaTrader 8\Bb20WickBb4Rr2Reports\
```

This port is intended for platform verification. Its historical order-fill
behavior can differ from the Python bar-based model, especially when a bar
touches both a limit and a stop/target.
