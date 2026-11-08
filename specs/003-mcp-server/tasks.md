# Tasks: pd-defence MCP Server

**Input**: `specs/003-mcp-server/` (plan.md, spec.md, research.md, data-model.md, contracts/tools.md, quickstart.md)

**Tests**: required. The constitution (II) requires a lookahead test for every
new data-loading function; SC-001/004/005/006 are test-verified.

Format: `- [ ] [ID] [P?] [Story?] Description with file path`

## Phase 1: Setup

- [X] T001 Create `server/__init__.py` that puts `src/` and `research/` on `sys.path` the way `scripts/monitor.py` does, and `server/requirements.txt` pinning `mcp>=2.2,<3` and `duckdb>=1.1,<2`
- [X] T002 [P] Create `server/config.py`: `Settings` from env (`PD_MCP_TOKEN`, `PD_HOST` default `127.0.0.1`, `PD_PORT` 8765, `PD_PROVIDER` `tiingo|massive|payload|fixture`, `TIINGO_API_KEY`, `MASSIVE_API_KEY`, `PD_SEC_CONTACT`, `PD_DATA_DIR`, `PD_ALLOWED_HOSTS`, `PD_TODAY_TTL_MIN` 240, `PD_PAYLOAD_DIR`); `validate()` raises if no token and host is not `127.0.0.1` (FR-008)
- [X] T003 [P] Add `server` + `serve` commands to `run.sh` and install server requirements in `setup`

## Phase 2: Foundational (blocks every story)

- [X] T004 [P] `server/bars.py`: `clean_bars(rows, as_of)` → `(bars, stats)`; drop `interpolated`, non-positive prices and duplicate dates only; keep flat bars; `suspect_bad_prints(bars)` using `ISOLATED_SPIKE_RATIO` and below-median volume from `src/event_sets.py`; raise `LookaheadError` on bars after `as_of`
- [X] T005 [P] `server/providers.py`: `Provider` protocol `daily(symbol, start, end) -> list[dict]`; `TiingoProvider` (adjusted OHLCV, `raw_c`, `splitFactor`), `MassiveProvider` (`adjusted=true`), `PayloadProvider` (brokerage historicals files in a dir), `FixtureProvider` (in-memory); `RateLimiter(calls, per_seconds)`; `RateLimited` and `NoData` errors; stdlib `urllib` only
- [X] T006 [P] `server/sec.py`: `EdgarClient(contact, fetch=urllib)`: ticker→CIK from `company_tickers.json`, `filings(symbol)` from `submissions/CIK##########.json` (+ `filings.files` pages) → `[{form, filed}]`; 5 req/s; User-Agent `pd-defence <contact>`; refuses to run without a contact
- [X] T007 `server/store.py`: DuckDB schema per data-model.md (`bars`, `coverage`, `filings`, `filings_coverage`, `checks`, `provider_calls`); `bars(symbol, start, as_of)` filtered `date <= as_of`; upserts; a lock around the single connection
- [X] T008 `server/data.py`: `DataService(store, provider, sec, today)`: `bars(symbol, as_of, lookback_days=430)` cache-first per the coverage rule ("a hit when `first_date <= start` and `last_date >= min(as_of, last completed session)`, and, if `as_of` is today, `fetched_at` is younger than `PD_TODAY_TTL_MIN`"); `no_data` memo for 24 h; `filings(symbol, as_of)` filtered `filed <= as_of`; serve from cache on `RateLimited` when covered, else raise `DataUnavailable`
- [X] T009 [P] Tests `tests/test_server_data.py`: `clean_bars` drops/keeps (flat bar kept, placeholder dropped, REED-style print flagged), lookahead raise, store round-trip filtered by `as_of`, cache hit makes no provider call, `no_data` memo, rate-limit fallback, filings truncation

## Phase 3: User Story 1 — check a ticker (P1) 🎯 MVP

Independent test: RYDE fixture as of 2024-09-06 → VETO; DJT-like large domestic filer → not a structural VETO.

- [X] T010 [US1] `server/tools.py`: `check_ticker(ds, symbol, as_of=None, position_usd=250, account_usd=1000, fundamentals=None, earnings=None, detail=False)` calling `check_ticker.check()` + compact text; validate symbol `^[A-Z][A-Z0-9.\-]{0,9}$`; refuse future dates; ignore `fundamentals` unless `as_of` is today; `NO DATA` verdict when the provider knows nothing; `data{bars, dropped, source, adjusted, splits, suspect_bad_prints}`; log to `checks`
- [X] T011 [US1] Tests `tests/test_server_tools.py`: RYDE (bars from `data/events/events_seed.jsonl`, filings from `data/l14/filings.json`) → VETO on 2024-09-06; DJT-like synthetic (130M float, $9B cap, ten 8-Ks) → no structural veto; unknown symbol → NO DATA; text never contains a buy recommendation; fundamentals ignored for past `as_of`; answer < 2,500 chars (SC-002)

## Phase 4: User Story 2 — was I pumped (P1)

Independent test: RYDE bought 2024-09-09 → `at_the_time` identical with and without later bars stored.

- [X] T012 [US2] `server/tools.py`: `was_i_pumped(ds, symbol, buy_date)`: `at_the_time` = `check_ticker` as of `buy_date`; `hindsight` from bars after it (peak, drawdown from buy close, ret_5/20/60, `"not yet"` when not elapsed); refuse dates before the first bar
- [X] T013 [US2] Tests in `tests/test_server_tools.py`: truncation (SC-005) on RYDE and a synthetic series; `"not yet"` horizons; pre-history date refused

## Phase 5: User Story 3 — pump scan (P2)

- [X] T014 [US3] `server/tools.py`: `pump_scan(ds, symbols, as_of=None)`; ≤ 50 symbols; rows `{symbol, verdict, run_up_5, run_up_10, volume_ratio_20, last_close, reason}` sorted VETO first then `run_up_10` desc; per-symbol `NO DATA` without aborting
- [X] T015 [US3] Tests in `tests/test_server_tools.py`: ordering, 51 symbols refused, missing symbol listed as NO DATA

## Phase 6: User Story 4 — monitor digest (P2)

- [X] T016 [US4] `server/tools.py`: `monitor_digest(ds, positions, orders=None, as_of=None)` using `scripts/monitor.holding_report` and `parse_orders`; whitelist `{symbol, quantity, average_cost}` from each position (account numbers discarded); nothing persisted
- [X] T017 [US4] Tests in `tests/test_server_tools.py`: EXIT RULE + LOSS on a position below its 200-day; account number absent from output and from the DuckDB file; note says no orders were placed

## Phase 7: User Story 5 — service, container, deploy (P2)

- [X] T018 [US5] `server/app.py`: `build_app(settings, ds)` → Starlette app with `MCPServer` tools (`readOnlyHint`), stateless JSON streamable HTTP at `/mcp`, `/healthz`, auth middleware (Bearer header or `/t/<token>/` prefix, `hmac.compare_digest`), allowed hosts; `data_status` tool; `main()` runs uvicorn; logs tool name, symbols, duration, outcome only (FR-009)
- [X] T019 [US5] Tests `tests/test_server_app.py`: `/healthz` open; MCP call without token → 401; wrong token → 401; Bearer and path forms → tool result; refuses to start without token on `0.0.0.0`; grep `server/` for order-tool names (SC-006)
- [X] T020 [P] [US5] `Dockerfile` (python:3.12-slim, non-root user, `HEALTHCHECK`), `.dockerignore` (excludes `raw/`, `results/`, `.env`, `.venv`), `docker-compose.yml` (port `127.0.0.1:8765:8765`, volume `pd-data`, `restart: unless-stopped`), `.env.example`
- [X] T021 [P] [US5] `.github/workflows/ci.yml`: push + PR, `ubuntu-latest`, Python 3.12, install server requirements, `pytest -q`
- [X] T022 [P] [US5] `.github/workflows/deploy.yml`: push to `main` + `workflow_dispatch`; test job on `ubuntu-latest`; deploy job `runs-on: [self-hosted, pd-defence]`, `if: github.event_name != 'pull_request'`; tag running image `previous`, `docker compose up -d --build`, poll `/healthz` 30×2 s, roll back on failure; secrets via env only

## Phase 8: Polish

- [X] T023 [P] `docs/mcp_server.md`: runbook — keys, `.env`, cloudflared ingress, runner registration, connecting Claude Code and claude.ai, token rotation, self-hosted-runner warning before going public
- [X] T024 [P] README section + `CLAUDE.md` / `PROGRESS.md` updates (server status, how to run)
- [X] T025 Run `python3 -m pytest -q`; build the image if Docker is available; mark tasks done

## Dependencies

Setup → Foundational → US1 → (US2, US3, US4 in any order; all reuse `check_ticker`) → US5 → Polish.
US5's container/workflow files (T020–T022) do not depend on US2–US4 and can be written in parallel with them.

## Parallel examples

- Phase 2: T004, T005, T006 together (separate files); then T007 → T008.
- Phase 7: T020, T021, T022 together while T018/T019 are in progress.

## Implementation strategy

MVP = Phases 1–3: a server that answers `check_ticker` from cache or Tiingo.
Then US2 (the owner's own question), US3/US4, and the deploy pipeline. Each
phase ends with `python3 -m pytest -q` green.
