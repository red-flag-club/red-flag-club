# Feature Specification: Local Data Retention

**Feature Branch**: `feature/layer2-scan-dashboard` (amends specs 003 and 004 before merge)

**Created**: 2026-10-16

**Status**: Implemented

**Input**: Owner, 2026-10-16: "Just for RYDE I don't want to store 2 years of
old data. Take a decision about local historical data storage and better user
experience."

## Decision

Store only what the checks need to answer *today's* questions, and the record
that cannot be rebuilt. Fetch everything else on demand and keep it in memory
only.

| Data | Before | After | Why this much |
|---|---|---|---|
| Whole-market daily bars (`market_daily`) | ~14 months backfilled, kept forever | **rolling 70 sessions** | screen needs 32, outcome labels 41, sparklines 60; no VETO rule looks back more than 11 bars |
| First scan backfill | 320 sessions (~70 min) | **60 sessions (~12 min)** | 22 warm-up + ~38 sessions of history on the first page |
| Per-symbol bars (`bars`) | every range ever asked, forever | **last ~14 months only, for symbols asked about in the last 30 days** | the 200-day average and 52-week range of a current check |
| Historical questions (e.g. RYDE in 2024) | fetched, then stored | **fetched, answered, kept in memory only** (small in-process cache, gone on restart) | a one-off question should not grow the disk |
| Scan log, outcomes, check log, SEC filing index | forever | **forever** | the forward record cannot be rebuilt; tiny (~12k rows/year) |

## User Scenarios & Testing

### User Story 1 - Ask about the past without storing it (P1)

The owner asks `was_i_pumped RYDE 2024-09-09`. The answer is the same as
before, says the history was fetched for this answer and not stored, and the
disk does not grow by two years of RYDE bars.

**Acceptance**: after the call, no RYDE bar older than the cache window is in
the database; the verdict is unchanged (VETO); asking again in the same server
session makes no new provider call.

### User Story 2 - The disk stays small without attention (P1)

**Acceptance**: after any number of refreshes the market table holds at most
70 sessions; symbols not looked up for 30 days are dropped; `data_status` and
the dashboard show the database size and the retention policy.

### User Story 3 - Faster first run (P2)

**Acceptance**: a new install shows a useful dashboard after one ~12-minute
backfill instead of ~70.

### Edge Cases

- A pending outcome needs bars from 10 sessions before first logged to 30
  after (41 sessions); 70 kept covers it, so pruning never removes bars a
  pending label needs (tested).
- Pruned sessions are remembered as `pruned` so they are never re-fetched and
  episode grouping (20-session gaps) still counts them.
- Recall: scan-time checks see 60 sessions instead of 300. The VETO rules
  (pump: 11 bars; ghost quote: last bar; structural: filings) are unaffected.
  Only cautions that use the 200-day average or 52-week high lose that input,
  and say so. Stated per CLAUDE.md hard rule 4: recall unchanged, some
  cautions weaker.

## Requirements

- **FR-001**: Per-symbol bars older than the cache window (430 days) are never
  written to disk.
- **FR-002**: Requests that need older bars are served from the provider and
  an in-memory cache of at most 32 symbol ranges; they are not persisted.
- **FR-003**: Symbols not accessed for 30 days are evicted; pruning runs at
  most once a day and after each scan refresh.
- **FR-004**: `market_daily` keeps the last 70 loaded sessions; older sessions
  are marked `pruned`, never re-fetched.
- **FR-005**: Scan log, outcomes, checks and filing indexes are never pruned.
- **FR-006**: Every answer built from un-stored history says so; `data_status`
  and the dashboard report database size and the policy.
- **FR-007**: No-lookahead guarantees and truncation tests are unchanged.

## Success Criteria

- **SC-001**: `was_i_pumped RYDE 2024-09-09` stores zero pre-window RYDE bars.
- **SC-002**: A 10k-symbol market for one year of refreshes keeps ≤ 70 sessions
  (~770k rows) on disk.
- **SC-003**: All existing reference-case tests pass unchanged (RYDE VETO,
  RYDE collapsed, truncation).

## Result

Simulated year (10,000 symbols, 260 sessions, refresh every 20 sessions): the
file is 27.8 MB with weekly compaction, against 142.4 MB with pruning but no
compaction (DuckDB reuses but never returns deleted space, and the market
table's primary-key index was larger than its data, so it was dropped).
