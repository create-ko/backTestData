# XAUUSD Session KTR Backtest Design

Date: 2026-07-01
Scope: first-pass system trading backtest for XAUUSD

## Goal

Build a testable system strategy for XAUUSD that trades both long and short, uses session-specific direction resets, and aims for about 2-3 trade opportunities per day without turning into high-frequency scalping.

This is a research/backtest specification, not financial advice.

## Fixed Assumptions

- Instrument: XAUUSD.
- Primary entry timeframe: 10-minute bars.
- Higher context: session-derived 1-hour observation window.
- Trading style: both long and short.
- Operation window: 24 hours, with direction reset by session.
- Trade frequency target: average 2-3 trades per day.
- Initial limit: maximum 1 trade per session and maximum 3 trades per day.
- A session trade is normally closed by stop or take-profit. For the first pass, also report a `forced_session_close` variant that exits any still-open position at the next session reset open, so the effect of carrying positions across resets is visible.
- Intrabar fill assumptions must avoid same-bar look-ahead. If entry, stop, and take-profit can occur in the same 10-minute bar, the implementation must either resolve with lower timeframe data or use a conservative ordering rule.

## Session Schedule

Session reset times are defined from local market times and converted to KST with daylight saving time handled by timezone rules.

- Asia: 08:00 KST fixed.
- Europe: 08:00 Europe/London local time, converted to KST.
- New York: 09:30 America/New_York local time, converted to KST.

Each session has a 1-hour observation window. Trading is allowed only after this first hour has completed.

Examples:

- Europe reset is 16:00 KST during UK summer time and 17:00 KST outside UK summer time.
- New York reset is 22:30 KST during US daylight saving time and 23:30 KST outside US daylight saving time.
- London and New York daylight saving transitions must be handled separately because their transition dates do not always match.
- A session's active entry window starts after its 1-hour observation window and ends at the next session reset.

## Direction Models To Compare

Two direction models will be tested with the same entry, stop, and take-profit rules.

### Model A: First-Hour Candle + 20 SMA

At the end of the session's first 1-hour observation window:

- Long bias if the 1-hour candle is bullish and its close is above the 20 SMA.
- Short bias if the 1-hour candle is bearish and its close is below the 20 SMA.
- Neutral otherwise.

The 20 SMA is calculated on completed 1-hour candles derived from the 10-minute data. No in-progress 1-hour candle is used except the completed observation candle itself.

An optional small-body filter can be added after the first test pass. For the first pass, record body size metrics but do not filter unless the implementation needs a deterministic neutral rule.

### Model B: First-Hour Box Breakout

During the session's first 1-hour observation window:

- Store the observation high and low as the session box.
- Bias remains neutral until a later 10-minute candle closes outside the box.
- Long bias after a 10-minute close above the session box high.
- Short bias after a 10-minute close below the session box low.

For the first pass, only the first valid breakout direction is used for that session.

## KTR Rules

KTR remains the volatility unit for entries, stops, and take-profits.

### Europe And New York KTR

For the first pass:

- Use the session observation range as raw KTR:
  - `raw_KTR = observation_high - observation_low`
- Use `effective_KTR = raw_KTR`.

### Asia KTR

Asia KTR is treated differently because the Asia open can create a distorted KTR.

The first-pass Asia KTR rule is:

```text
raw = max(today_08_00_10m_high, previous_trading_day_close)
      - min(today_08_00_10m_low, previous_trading_day_close)

avg10 = average(daily_high - daily_low) over the previous 10 trading days

effective_asia_KTR = min(raw, 0.25 * avg10)
```

Notes:

- The previous 10 trading days are Monday-Friday trading days with available XAUUSD data.
- `previous_trading_day_close` is the last available close before the current Asia session date.
- This rule does not disable Asia trades. It only prevents an abnormal Asia opening move from inflating the KTR used by the system.
- Record `raw`, `avg10`, `effective_asia_KTR`, and `raw / avg10` in output for diagnostics.

## Entry Model

The first pass uses a simple pullback-and-recovery entry after a session bias is available.

Long setup:

- Session bias is long.
- A 10-minute candle pulls back toward the 20 SMA or lower volatility band area.
- The candle closes back in the long direction.
- Entry is at the next 10-minute candle open.

Short setup:

- Session bias is short.
- A 10-minute candle pulls back toward the 20 SMA or upper volatility band area.
- The candle closes back in the short direction.
- Entry is at the next 10-minute candle open.

The implementation should start with a deterministic version:

- Long trigger: candle low is at or below 10-minute SMA20 and candle close is above SMA20.
- Short trigger: candle high is at or above 10-minute SMA20 and candle close is below SMA20.

Band-based variants can be added after the baseline result is known.

## Stop And Take-Profit Grid

The first test compares a small risk/return grid:

- Stop distance: `1.0 KTR`, `1.5 KTR`.
- Take-profit: `1.0R`, `1.5R`, `2.0R`.

For a long:

- Stop = entry - stop_distance.
- TP = entry + stop_distance * tp_R.

For a short:

- Stop = entry + stop_distance.
- TP = entry - stop_distance * tp_R.

If both stop and TP are touched in the same 10-minute candle and no lower timeframe path is available, count the stop first in the baseline result.

## Position And Frequency Limits

- One open position at a time.
- Maximum 1 entry per session.
- Maximum 3 entries per KST trading day.
- If a position remains open into the next session, the next session may update diagnostics but does not open a new position until the current position closes.

## Costs And Output

The first pass should report gross results and net results.

Baseline net result subtracts `0.40` points per completed round trip. Also report sensitivity at `0.20`, `0.30`, `0.40`, and `0.50` points.

Required output columns:

- direction model: A or B.
- session: Asia, Europe, NewYork.
- KST entry date and time.
- direction.
- entry price.
- exit price.
- KTR raw/effective.
- stop multiplier.
- TP R.
- gross points.
- net points.
- R result.
- holding bars.
- exit reason.
- exit mode: normal hold or forced session close variant.

Required summary:

- trades per day.
- trades per session.
- win rate.
- average R.
- total R.
- profit factor.
- max drawdown by R.
- yearly breakdown.
- model A vs model B comparison.
- Asia raw KTR ratio diagnostics.

## First Implementation Plan Candidate

1. Build a script under `backTestData/src/scripts/` that reads `data/xauusd_10m_2010-01-01_2026-06-16.csv`.
2. Convert timestamps to KST-aware datetimes.
3. Build daily ranges and previous trading-day closes.
4. Generate session windows with Asia fixed KST and Europe/New York timezone conversion.
5. Compute Model A and Model B biases.
6. Generate 10-minute pullback entries after the observation window.
7. Simulate exits with conservative same-bar handling.
8. Write trade CSVs to `data/` and an HTML/JSON summary to `result/`.

## Open Items After First Result

- Whether the deterministic SMA20 pullback trigger is too narrow or too broad.
- Whether Asia KTR cap at `0.25 * avg10` should be tuned.
- Whether Model A or Model B produces better frequency and drawdown.
- Whether session max 1 trade is too restrictive for New York.
- Whether 1-minute data should be used for intrabar exit resolution.
