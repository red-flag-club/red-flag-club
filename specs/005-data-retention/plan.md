# Implementation Plan: Local Data Retention

**Spec**: [spec.md](spec.md) | **Date**: 2026-10-16

## Summary

`server/data.py` gains a cache window (430 days before the last session).
Requests whose range starts inside it go through the existing persistent
cache (fetch padding clamped to the window); older ranges go to an in-memory
LRU (`EphemeralCache`, 32 entries) and never reach DuckDB. `coverage` gains
`accessed_at`; `Store.prune(window_start, idle_cutoff)` deletes old and idle
bars. `server/scan.py` keeps 70 market sessions (`MARKET_KEEP_SESSIONS`),
marks older ones `pruned`, backfills 60, checks hits on 60 sessions.
`server/outcomes.py` indexes sessions including `pruned` so episodes are
grouped the same way after pruning.

## Constitution Check

| Principle | Effect | Gate |
|---|---|---|
| II No lookahead | Unchanged: all reads still cut at `as_of`; ephemeral fetches are `[start, as_of]` | PASS |
| IV Recall | VETO inputs unaffected (≤ 11 bars + filings). 200-day/52-week cautions weaker at scan time — stated in spec | PASS (stated) |
| V Hygiene | Ephemeral rows pass through the same `clean_bars` | PASS |

## Files

`server/data.py`, `server/store.py`, `server/scan.py`, `server/outcomes.py`,
`server/tools.py` (provenance text, data_status), `server/dashboard.py`
(storage line), tests in `tests/test_server_retention.py`, docs.
