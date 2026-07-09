# XAUUSD Session KTR Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run the first-pass XAUUSD session KTR backtest from the approved design.

**Architecture:** Add one focused Python script that loads XAUUSD 10-minute data, derives sessions, computes direction models A/B, simulates KTR-based exits, and writes CSV/JSON/HTML outputs. Add a small test file for deterministic helpers around Asia KTR, session conversion, SMA, and exit resolution.

**Tech Stack:** Python standard library only, CSV input/output, JSON summary, static HTML report.

---

### Task 1: Tests First

**Files:**
- Create: `backTestData/tests/test_xauusd_session_ktr.py`
- Create later: `backTestData/src/scripts/73_xauusd_session_ktr.py`

- [ ] **Step 1: Write failing tests**

Create tests for SMA, Asia KTR capping, session reset conversion, and conservative same-bar exit resolution.

- [ ] **Step 2: Run tests to verify failure**

Run: `python tests/test_xauusd_session_ktr.py` from `backTestData`.
Expected: failure because `73_xauusd_session_ktr.py` does not exist yet.

### Task 2: Backtest Script

**Files:**
- Create: `backTestData/src/scripts/73_xauusd_session_ktr.py`

- [ ] **Step 1: Implement helper functions**

Implement data loading, SMA, daily range, Asia KTR, session generation, and conservative trade exit helpers.

- [ ] **Step 2: Run tests**

Run: `python tests/test_xauusd_session_ktr.py` from `backTestData`.
Expected: all tests pass.

### Task 3: Run Backtest And Report

**Files:**
- Output: `backTestData/data/session_ktr_trades.csv`
- Output: `backTestData/data/session_ktr_summary.json`
- Output: `backTestData/result/session_ktr_backtest_report.html`

- [ ] **Step 1: Run script**

Run: `cd data && python ../src/scripts/73_xauusd_session_ktr.py`.
Expected: ASCII console summary and output files.

- [ ] **Step 2: Inspect summary**

Open the JSON/HTML outputs and check that model A/B, sessions, stop/TP grid, Asia KTR diagnostics, and yearly rows are present.
