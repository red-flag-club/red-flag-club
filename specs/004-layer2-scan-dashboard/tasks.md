# Tasks: Layer 2 Scan Log and Private Dashboard

**Input**: `specs/004-layer2-scan-dashboard/` (spec, plan, research, data-model, contracts/tools.md, quickstart)

**Tests**: required (constitution II; SC-002/003/004).

## Phase 1: Setup

- [X] T001 Add settings `PD_SCAN_SOURCE` (`massive|payload|fixture|off`, default `off`), `PD_SCHEDULE` (`on|off`), `PD_SCAN_TIMES` (default `10:00,12:30,15:00,17:30`) to `server/config.py`
- [X] T002 [P] Add new tables to `server/store.py` per data-model.md (`market_daily`, `sessions`, `splits`, `scan_log`, `outcomes`, `scan_runs`); `log_hits()` uses `INSERT OR IGNORE` — "there is no UPDATE or DELETE on this table anywhere in the code"

## Phase 2: Foundational

- [X] T003 `server/market.py`: `MarketSource` protocol `session(date) -> list[{symbol,o,h,l,c,v}]` and `splits(date) -> list[{symbol, ratio}]`; `MassiveGrouped` (grouped daily + splits endpoint, own `RateLimiter(5, 60, max_wait=65)`), `PayloadSnapshots(dir)`, `FixtureSnapshots(rows_by_symbol)`; `check_source()`
- [X] T004 `server/scan.py`: `screen(history_by_symbol, session, splits)` pure; per R2: close 1–30, `ret_5 >= 0.50` or `ret_21 >= 0.50`, `rel_vol_30` recorded; history truncated at the latest split ≤ session; flags `split`, `possible_split`, `bad_print`, `short_history`
- [X] T005 Tests `tests/test_server_scan.py` (screen): thresholds, split truncation (1:10 reverse split not a hit), bad print flagged, price band

## Phase 3: US1 — daily scan log (P1) 🎯 MVP

- [X] T006 [US1] `server/scan.py`: `load_sessions(store, source, until)` catch-up in date order, `sessions` status/retry, stop cleanly on RateLimited; `log_session(store, ds, session)`: screen with `market_daily WHERE date <= session`, `check()` on each hit with those bars + filings `filed <= session`, append rows; `backfilled` if session older than 5 sessions at run time; `refresh()` = load + log + filings refresh + outcomes + page, under a lock, recorded in `scan_runs`
- [X] T007 [US1] Tests: synthetic pump logged on its first qualifying session with VETO; RYDE seed logged on or before 2024-09-04; re-run adds/changes nothing (SC-002); truncation (SC-003); missed sessions scanned in order; grep for UPDATE/DELETE on `scan_log`

## Phase 4: US2 — outcomes (P1)

- [X] T008 [US2] `server/outcomes.py`: episodes (first log after ≥ 20 sessions without one), `label_outcomes(store, as_of)` with `find_runs` on closes from 10 sessions before to 30 after; pending until 30 sessions; `forward_metrics(store)` excluding backfilled rows, with N and "too few to judge" below N=30
- [X] T009 [US2] Tests: pending → collapsed only after 30 sessions; no_collapse case; backfilled rows excluded from metrics

## Phase 5: US3 — is_pumping / scan_latest (P2)

- [X] T010 [US3] `server/tools.py`: `is_pumping(ds, symbol)`, `scan_latest(ds, session=None, limit=25)` per contracts/tools.md; register both in `server/app.py` with `readOnlyHint`
- [X] T011 [US3] Tests: days_on_scan counts, never-logged symbol, limit cap 200, app lists 7 tools

## Phase 6: US4 — dashboard and schedule (P2)

- [X] T012 [US4] `server/dashboard.py`: `build_page(store, now)` → self-contained HTML (inline CSS/SVG, light/dark tokens, no external URLs): header with data session + built time + gate status; hits table with sparklines; hits-per-session bar chart (60 sessions) with N; validation table with N; disclaimers; `write_page(path)`
- [X] T013 [US4] `server/app.py`: `GET /dashboard/` serving the built page (`no-store`), 503 if none; scheduler started from the MCP lifespan when `PD_SCHEDULE=on`
- [X] T014 [US4] `server/schedule.py`: `next_run(now, times)` (weekdays, ET), `run_forever(refresh)`; tests for next_run across a weekend and after the last slot
- [X] T015 [US4] Tests `tests/test_server_dashboard.py`: page contains the pump row, N, disclaimers, no `http://`/`https://` resource URLs, < 1 MB; `/dashboard/` refused without token, served with path token

## Phase 7: Polish

- [X] T016 [P] `run.sh`: `scan [--as-of D] [--backfill N] [--check-source] [--fixture]`, `dashboard`; `server/jobs.py` CLI behind them
- [X] T017 [P] `.env.example`, `docker-compose.yml`: new env vars; `docs/mcp_server.md` scan/dashboard section; README, CLAUDE.md, PROGRESS.md
- [X] T018 Extend the order-tool grep test to new files; full `python3 -m pytest -q`; rebuild and run the image with the fixture source; mark tasks done

## Dependencies

T001–T002 → T003–T005 → US1 → US2 → (US3, US4) → Polish. US3 and US4 are independent of each other.

## Implementation strategy

MVP = US1: the append-only log, because every session not logged is lost.
Then outcomes (the reason the log exists), then the tools and page.
