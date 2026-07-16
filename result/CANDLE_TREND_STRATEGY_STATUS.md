# XAUUSD Candle and Trend Strategy Status

## Retained research candidate

**NY17 Daily King Keltner SMA50**

- Trading day: 17:00 America/New_York to the next 17:00, DST aware.
- Candle input: completed daily HLC3 and True Range.
- Trend: slope of HLC3 SMA50.
- Long entry: next-day stop at `SMA50 + simple TR40` when SMA50 is rising.
- Short entry: next-day stop at `SMA50 - simple TR40` when SMA50 is falling.
- Entry order expires after one trading-day candle.
- Exit: next-day stop at the latest completed SMA50.
- One position at a time.
- Gap fills use the adverse opening price.
- Round-trip cost: 0.5 points.
- Exit is variable-R trend following, not fixed 2R.

### Evidence and limitations

- Chronological 5m execution, full 2010-2026: 169 trades, +2403.55 points, PF 1.7626, DD 414.68.
- Six fixed three-year chunks: 6/6 profitable.
- Calendar years: 12/17 profitable.
- SMA50 5m-executed parameter neighborhood: 25/25 TR-length/band-width combinations produced 6/6 profitable chunks, but the weakest individual chunk was only +2.91 points.
- Cost 1.0: +2321.64, PF 1.7235, chunks 6/6.
- Training-only rule using 2010-2018 selected SMA50 without holdout data.
- Unused 2019-2026 holdout: 79 trades, +1919.43, PF 2.0487, DD 359.80, chunks 3/3.
- Keeping or removing sub-100-bar holiday sessions did not change the 25/25 neighborhood pass count.
- The largest win contributed 44.37% of total net; the top five contributed 100.26%. Removing those five changed net to -6.23.
- Long trades: +3045.15, PF 3.5536. Short trades: -641.60, PF 0.6725.
- IID trade bootstrap: 3.79% non-positive endings, net p05 +169.13, DD p95 1184.92. Calendar-year blocks: 0.53%, net p05 +567.12, DD p95 613.31.

### Files

- Pine: `src/finescript/daily_king_keltner_ny17_sma50_v6.pine`
- TradingView guide: `result/ny17_daily_king_sma50/TRADINGVIEW_GUIDE.md`
- Detailed validation: `result/ny17_daily_king_sma50/REPORT.md`
- 5m execution validation: `result/ny17_daily_king_sma50_5m_execution/REPORT.md`
- 5m neighborhood/bootstrap/tail audit: `result/ny17_daily_king_sma50_5m_robustness/REPORT.md`
- Fixed-2R retest filter audit: `result/daily_trend_retest_rr2_filtered_oos/REPORT.md`
- NY17 daily-trend session close-breakout audit: `result/ny17_daily_trend_session_breakout_oos/REPORT.md`
- Cross-family meta-analysis: `result/strategy_family_meta_analysis/REPORT.md`
- Full NY17 grid: `result/ny17_daily_king_full_grid/REPORT.md`
- Boundary audit: `result/daily_king_keltner_boundary_sensitivity/REPORT.md`
- Corrected intraday extension: `result/ny17_sma50_regime_intraday_candle_rr2/REPORT.md`
- Corrected session-first extension: `result/ny17_sma50_regime_session_first_candle_rr2/REPORT.md`

## Rejected or invalidated

- UTC-calendar SMA60: invalidated because 873 short partial bars, mostly Sunday opens, created false parameter stability.
- NY17 SMA50 regime plus continuous 15m/30m candle fixed-2R entries: 2026 passed, but full history lost 1013.99 points with PF 0.9251.
- NY17 SMA50 regime plus first session 15m candle: every configuration meeting 1-3 entries/day lost money in 2026.
- Earlier daily-trend ADR, retest, Keltner intraday, and candle reclaim fixed-2R families remained regime-dependent or historically negative.
- A 2026-only direction/session/signal filter audit of the strongest daily-trend 15m/5m retest family found 52 eligible variants, but 0/52 later achieved six profitable historical chunks. The actually selected row remained at 3/6 and was rejected.
- Expanding that same entry family to 1R-3R targets and optional 0.75R/1R breakeven moves selected 3R with no breakeven on 2026. The frozen row and all top 12 2026 alternatives still produced at most 3/6 profitable chunks, so exit architecture did not repair the regime dependence.
- For that 3R row, zero cost produced 6/6 positive chunks, but the required 0.5-point round trip reduced it to 3/6. The weakest chunk's gross edge supports only about 0.1593 points of round-trip cost, so the apparent signal edge is not tradable under the stated cost assumption.
- A separate NY17 completed-daily trend plus session 5m/15m close-breakout family selected 1.63 trades/day and PF 1.365 on 2026, but froze to -2224.50 points, PF 0.9156, and only 1/6 profitable chunks. Even zero cost reached only 3/6, so direct breakout was rejected independently of the retest family.
- A 2026-ranked portfolio of the 3R retest and session-breakout families retained 2.48 trades/day but passed only 2/6 historical chunks. Repairing all chunks with the low-frequency swing would require 22.51x swing exposure, which is unacceptable given its five-trade profit concentration.

## Decision

The NY17 SMA50 strategy is the strongest correctly aggregated candle-and-trend **swing research candidate**. Its parameter neighborhood is stable, but its realized profit is strongly dependent on a handful of large long trends. It is suitable for TradingView comparison and forward paper testing, not for treating the historical average as a dependable live expectation.

It is not a confirmed live strategy because:

- Frequency is only 0.033 trades per trading day, not the requested 1-3 entries/day.
- Only three trades occurred in the 2026 selection window.
- The short side was historically negative and the top five wins account for more than all net profit.
- The robustness-selection rule was formulated during this research process, so genuinely future data is still needed.

No tested strategy currently satisfies all of: candle plus trend logic, 1-3 entries/day, 0.5 cost, fixed 2R, and stable 2010-2026 three-year chunks.

The 2025-2026 chunk also has the sample's highest normalized daily volatility and trend efficiency. Because multiple strategy families were redesigned after inspecting earlier failures, 2010-2025 can no longer serve as a genuinely untouched holdout for another iteration. Confirmation now requires post-2026-06-16 data or an explicit relaxation of the frequency/cost/exit constraints.
