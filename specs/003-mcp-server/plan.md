# Implementation Plan: pd-defence MCP Server

**Branch**: `feature/mcp-server` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-mcp-server/spec.md`

## Summary

A small Python service in a new top-level `server/` package. Tool logic is plain
functions over an injected `DataService`; a thin layer binds them to the MCP SDK
(streamable HTTP) behind a shared-secret check. Daily bars come from Tiingo's
free tier (full history, needed for 2024 cases like RYDE), with Massive
(ex-Polygon) free tier as an alternative adapter and an offline adapter that
imports the brokerage payload files the project already has. Filing indexes
come from SEC EDGAR's submissions API. Everything is cached in one DuckDB file
on a Docker volume. GitHub Actions runs tests on a GitHub-hosted runner and, on
`main` only, redeploys with `docker compose` on a self-hosted runner on the
owner's laptop; the owner's existing cloudflared tunnel routes a hostname to
`127.0.0.1:8765`.

## Technical Context

**Language/Version**: Python 3.11+ (image: `python:3.12-slim`)

**Primary Dependencies**: `mcp>=2.2,<3` (official SDK; `MCPServer`, streamable
HTTP), `duckdb>=1.1,<2`, `uvicorn` (pulled in by `mcp`). HTTP to providers uses
stdlib `urllib` so tests need no network mocks library. pandas is not needed.

**Storage**: DuckDB file at `$PD_DATA_DIR/pd.duckdb` (volume `pd-data`).

**Testing**: pytest, fully offline: a `FixtureProvider` and a fake SEC client
serve repo data (`data/events/events_seed.jsonl` RYDE bars,
`data/l14/filings.json` RYDE filings) and synthetic series.

**Target Platform**: Linux container on the owner's laptop (Docker Desktop or
Engine; amd64 or arm64).

**Project Type**: web service (MCP over HTTP) + CI/CD config.

**Performance Goals**: cached check < 2 s; uncached < 15 s (SC-003).

**Constraints**: Tiingo free tier ≈ 50 requests/hour, 500 unique symbols/month;
Massive free 5 requests/minute, 2 years history; SEC ≤ 10 requests/second with a
contact User-Agent. Single user; one process.

**Scale/Scope**: one owner, tens of checks a day, `pump_scan` ≤ 50 symbols.

## Constitution Check

| Principle | How this plan complies | Gate |
|---|---|---|
| I. Read-only | The server has no brokerage client at all. No order tool exists; a test greps `server/` for order-tool names. Positions arrive as tool input from the caller. | PASS |
| II. No lookahead | `DataService.bars(symbol, as_of)` returns only `date <= as_of`; `check()` already raises `LookaheadError`. `was_i_pumped` computes the verdict from a truncated series and the hindsight block separately; a test asserts the verdict is identical with and without later bars stored. | PASS |
| III. Point-in-time | Free sources give no historical float/market cap. Fundamentals are accepted only from the caller and only when `as_of` is today; otherwise unknown. Filings are filtered `filed <= as_of`. | PASS |
| IV. Recall over precision | Verdict logic is reused unchanged; unknowns score worst-case (existing `check()` behaviour). No threshold changes. | PASS |
| V. Data hygiene | Provider adapters drop zero/placeholder bars and synthesized bars; survivor count is in every response. Bad one-bar prints are flagged, not dropped. Metrics carry N. | PASS |
| Scope: defence path | `server/` is an application layer that calls `src/`, `research/check_ticker.py` and `scripts/monitor.py`. It emits no buy signal; every response carries "not a buy signal; no order placed". `src/` imports nothing from `server/`. | PASS |
| Stack: stdlib + pandas | **Deviation**: `mcp` and `duckdb`. Justified below. | PASS (justified) |
| Workflow | Spec Kit 003; cites PLAN.md L2.3; tests before push. | PASS |

## Project Structure

### Documentation (this feature)

```text
specs/003-mcp-server/
├── spec.md
├── plan.md              # this file
├── research.md          # provider, auth, transport, deploy decisions
├── data-model.md        # DuckDB tables
├── quickstart.md        # run + validate
├── contracts/tools.md   # MCP tool contract
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
server/
├── __init__.py          # puts src/ and research/ on sys.path (as scripts/monitor.py does)
├── config.py            # env -> Settings (token, provider, keys, data dir, host)
├── bars.py              # clean_bars(): drop placeholders/synthesized, flag bad prints
├── providers.py         # TiingoProvider, MassiveProvider, PayloadProvider, FixtureProvider, RateLimiter
├── sec.py               # EdgarClient: ticker->CIK, submissions -> filings
├── store.py             # DuckDB schema + reads filtered by as_of
├── data.py              # DataService: cache-first bars/filings, coverage, no-data memo
├── tools.py             # check_ticker, was_i_pumped, pump_scan, monitor_digest, data_status
├── app.py               # MCPServer binding, auth middleware, /healthz, main()
└── requirements.txt

tests/test_server_*.py   # offline tests (bars, store, data, tools, auth)
Dockerfile
docker-compose.yml
.dockerignore
.env.example
.github/workflows/ci.yml       # tests on GitHub-hosted runner, every push/PR
.github/workflows/deploy.yml   # main only: tests, then self-hosted docker compose up
docs/mcp_server.md             # owner runbook: cloudflared, runner, connecting clients
```

**Structure Decision**: a separate `server/` package keeps the service out of
the defence path (`src/` stays pure and SDK-free) and out of `research/`.
`server/__init__.py` reproduces the `sys.path` set-up `scripts/monitor.py`
already uses, so `check_ticker` and `monitor` are imported, not copied (FR-002).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `mcp` dependency | Speaking MCP over streamable HTTP correctly (sessions, JSON-RPC, protocol versions) | Hand-rolled JSON-RPC would drift from the protocol and break clients |
| `duckdb` dependency | The owner asked for it; it is the planned store for the dashboard (Parquet export, SQL over bars) | SQLite would work for this spec but would be migrated in the next one |
| Self-hosted runner | The owner's choice; deploy target is the laptop | A cloud host costs money and the owner wants it private |
