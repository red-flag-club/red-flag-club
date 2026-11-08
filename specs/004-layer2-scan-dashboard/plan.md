# Implementation Plan: Layer 2 Scan Log and Private Dashboard

**Branch**: `feature/layer2-scan-dashboard` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

## Summary

Extend the spec 003 server. A `MarketSource` returns one session's bars for the
whole market (Massive grouped daily; brokerage payload files or fixtures
offline). `server/scan.py` keeps a `market_daily` table, screens each new
session (pure function), runs `check_ticker.check()` on hits using only
`market_daily` rows dated ≤ that session plus SEC filings filed ≤ it, and
appends to `scan_log`. `server/outcomes.py` labels logged symbols with
`find_runs` once 30 sessions have passed. `server/dashboard.py` renders one
self-contained HTML page with inline SVG charts. An in-process scheduler runs
the idempotent refresh at 10:00, 12:30, 15:00 and 17:30 ET on weekdays. Two
new MCP tools: `is_pumping`, `scan_latest`. The page is served at
`/dashboard/` behind the existing token gate (`/t/<token>/dashboard/`).

## Technical Context

**Language/Version**: Python 3.11+ (image python:3.12-slim)

**Primary Dependencies**: unchanged (`mcp`, `duckdb`); no chart library —
SVG is generated in Python, so the page has no external requests.

**Storage**: same DuckDB file; new tables `market_daily`, `splits`,
`scan_runs`, `scan_log`, `outcomes` (data-model.md). Weekly Parquet export of
`scan_log` + `outcomes` to `/data/exports/` as the backup-friendly asset.

**Testing**: pytest, offline; synthetic market snapshots plus the RYDE seed.

**Target Platform**: the spec 003 container on the owner's laptop.

**Performance Goals**: a refresh with no new session < 10 s; one new session
(~10k symbols, ~50 hits) < 2 min; first backfill 60 sessions (~12 min at 5
calls/min; was ~290 before spec 005), resumable.

**Constraints**: free tier 5 calls/min; laptop may be off; no paid services.

**Scale/Scope**: ~10k symbols/session, ~3M `market_daily` rows/year (DuckDB
handles this in a few hundred MB).

## Constitution Check

| Principle | Compliance | Gate |
|---|---|---|
| I. Read-only | No brokerage calls; scan writes only to the server's own DB. Order-tool grep test extended to new files. | PASS |
| II. No lookahead | Screen and verdict for session D read `market_daily WHERE date <= D` and filings `filed <= D`; truncation test on the log. Outcomes are labels, written only after 30 sessions, and never feed a verdict. | PASS |
| III. Point-in-time | Float/market cap unknown → not applied as filters (FR-001), scored worst-case in the check. Splits handled by truncating history at the split, not by back-adjusting with later knowledge. | PASS |
| IV. Recall over precision | Screen widened by dropping unknown filters; OR of the 5-session and 21-session run-up rules. Stated in spec FR-001. | PASS |
| V. Hygiene / N | Non-positive bars dropped and counted per session; bad prints flagged; every metric with N; backfilled rows excluded from forward metrics. | PASS |
| Scope | Server-side application code; `src/` unchanged; no buy signal. | PASS |

## Project Structure

```text
specs/004-layer2-scan-dashboard/   spec, plan, research, data-model, contracts/, quickstart, tasks
server/market.py      MarketSource: MassiveGrouped (+ splits), PayloadSnapshots, FixtureSnapshots
server/scan.py        screen() (pure), refresh(): catch up sessions, log hits, filings refresh
server/outcomes.py    label_outcomes(), forward_metrics()
server/dashboard.py   build_page() -> HTML string with inline SVG; write_page()
server/schedule.py    next_run(), run_forever() for the in-process scheduler
server/store.py       + new tables and append-only insert
server/tools.py       + is_pumping, scan_latest
server/app.py         + tools, /dashboard/ route, scheduler in lifespan
tests/test_server_scan.py, tests/test_server_dashboard.py
run.sh                + scan, dashboard
docs/mcp_server.md    + scan/dashboard section
```

## Complexity Tracking

| Choice | Why | Simpler alternative rejected |
|---|---|---|
| In-process scheduler | Laptop-only deploy; no extra container or cron to configure; idempotent runs catch up after sleep | GitHub scheduled workflow: UTC-only, delayed, and needs the self-hosted runner online anyway |
| Hand-written SVG | No external requests (privacy, offline), no JS dependency to pin | A chart library from a CDN adds a third-party request to a private page |
