# Session Open Retest 5m Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate 2026 XAUUSD 5m backtest and chart report for the session first-candle close retest strategy.

**Architecture:** Create one focused strategy/report script that reuses the existing CSV data style and session reset rules. Add a small test file that validates session construction, retest detection, entry/exit math, and report shell behavior before running the full 2026 backtest.

**Tech Stack:** Python standard library, existing XAUUSD 5m CSV, static HTML/SVG/JavaScript report.

---

### Task 1: Strategy Core Tests

**Files:**
- Create: `tests/test_session_open_retest_5m.py`
- Create: `src/scripts/83_session_open_retest_5m.py`

- [ ] **Step 1: Write failing tests**

Create tests for:
- bullish first session candle generates a long setup;
- bearish first session candle generates a short setup;
- long retest requires `low <= level` and `close >= level`;
- short retest requires `high >= level` and `close <= level`;
- entry is next bar open after the retest candle;
- stop is the first candle body midpoint;
- take profit is entry plus/minus two times risk;
- same-bar SL/TP conflict resolves as SL first.

- [ ] **Step 2: Run tests and verify RED**

Run:
`C:\Users\sh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\test_session_open_retest_5m.py`

Expected: FAIL because `83_session_open_retest_5m.py` does not exist or lacks the tested functions.

- [ ] **Step 3: Implement minimal strategy core**

Implement:
- `Bar`
- `Session`
- `build_session_resets`
- `session_first_bar`
- `setup_from_first_bar`
- `is_retest`
- `resolve_exit`
- `backtest`
- `summarize`

- [ ] **Step 4: Run tests and verify GREEN**

Run:
`C:\Users\sh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tests\test_session_open_retest_5m.py`

Expected: PASS.

### Task 2: 2026 Outputs And Interactive Report

**Files:**
- Modify: `src/scripts/83_session_open_retest_5m.py`

- [ ] **Step 1: Add output writers**

Write:
- `data/session_open_retest_5m_2026_trades.csv`
- `data/session_open_retest_5m_2026_summary.json`
- `result/session_open_retest_5m_2026_report.html`

- [ ] **Step 2: Add one-frame chart report**

The HTML must include:
- dropdown per trade;
- continuous 5m candles around setup, retest, entry, and exit;
- first session candle marker;
- retest candle marker;
- entry, SL, TP, and exit lines;
- summary cards and trade details.

- [ ] **Step 3: Run backtest**

From `data/`, run:
`C:\Users\sh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe ..\src\scripts\83_session_open_retest_5m.py`

Expected: console prints summary and writes all three output files.

- [ ] **Step 4: Verify outputs**

Run tests again and inspect generated JSON summary for non-empty structured output.
