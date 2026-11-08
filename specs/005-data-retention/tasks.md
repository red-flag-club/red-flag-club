# Tasks: Local Data Retention

- [X] T001 `server/store.py`: `coverage.accessed_at` (ALTER ... ADD COLUMN IF NOT EXISTS), `touch()`, `prune_bars(window_start, idle_cutoff)`, `prune_market(keep)` marking `pruned`, `sessions_all()`, `db_size()`
- [X] T002 `server/data.py`: `CACHE_DAYS=430`, `IDLE_DAYS=30`, `window_start()`, `EphemeralCache` (32), `bars()`/`hindsight()` route pre-window ranges to the provider + memory only; padding clamped to the window; `maybe_prune()` once a day
- [X] T003 `server/scan.py`: `MARKET_KEEP_SESSIONS=70`, `BACKFILL_SESSIONS=60`, `CHECK_SESSIONS=60`; skip `pruned` in `load_sessions`; prune after each refresh
- [X] T004 `server/outcomes.py`: index episodes on loaded + pruned sessions
- [X] T005 `server/tools.py` / `server/dashboard.py`: "fetched for this answer, not stored" provenance; storage line in `data_status` and on the page
- [X] T006 Tests `tests/test_server_retention.py`: SC-001, eviction, window clamp, market keep ≤ 70 with outcomes intact and no re-fetch, ephemeral cache hit, truncation still identical
- [X] T007 Docs: specs 003/004 notes, `docs/mcp_server.md`, CLAUDE.md, PROGRESS.md; full suite; container check
- [X] T008 (found while measuring) drop the `market_daily` primary key, add weekly `Store.compact()` (copy + atomic rename), mark old empty weekdays `no_session` at once
