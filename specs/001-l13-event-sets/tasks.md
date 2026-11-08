# Tasks: L1.3 Event Sets

**Input**: `specs/001-l13-event-sets/` (spec, plan, research, data-model, quickstart)
**Tests**: required — the constitution mandates a lookahead test for every data loader.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Carve `data/universe/`, `data/events/`, `data/l13/` out of the `data/` ignore rule in `.gitignore`
- [x] T002 [P] Add trimmed real fixtures to `tests/fixtures/l13/` (RYDE, RETO daily bars; one scan band)
- [x] T003 [P] Restate the `src` import rule in `CLAUDE.md` Conventions (plan, Constitution Check)

## Phase 2: Foundational

- [x] T004 Write failing tests in `tests/test_event_sets.py`: hygiene (interpolated + zero-price), lookahead guard, truncation cannot add a positive
- [x] T005 Implement `clean_bars(raw, as_of)` and `LookaheadError` in `src/event_sets.py`

## Phase 3: User Story 1 — labelled event sets (P1) 🎯 MVP

- [x] T006 [US1] Tests: RYDE 2024-09-06 positive; RETO 2023-08-18 and 2026-09-15 positives; censored run → pending
- [x] T007 [US1] Implement `label_events(symbol, bars, as_of, origin, batch)` with 60-session pre-window
- [x] T008 [US1] Implement `scripts/l13.py ingest` (payload → events JSONL + progress), idempotent
- [x] T009 [US1] Live: fetch RYDE, RETO; ingest as batch `seed`; commit

## Phase 4: User Story 3 — universe snapshot (P2)

- [x] T010 [P] [US3] Tests in `tests/test_l13_cli.py`: band parse, replace-by-bounds, saturation, gaps, dedupe
- [x] T011 [US3] Implement `universe-add` / `universe-build`
- [x] T012 [US3] Live: preview bands $0–500M, splitting until complete; commit snapshot

## Phase 5: User Story 2 — resumable sweep (P2)

- [x] T013 [US2] Tests: seeded order stable, `next-batch` skips done, missing symbols → `no_data`, report counts
- [x] T014 [US2] Implement `next-batch` and `report`
- [x] T015 [US2] Live: run batches, commit after each, report positives with N; stop at ≥100 positives / ≥300 controls or when budget is spent, without touching thresholds

## Phase 6: User Story 4 — float check (P3)

- [ ] T016 [US4] ~~Implement `scripts/float_check.py` record/replay around `float_as_of`~~ — not built: every small-cap filing 404s, so there is nothing to replay (see research R8)
- [x] T017 [US4] Live: 5 small caps; hit rate 0/5 on every path → `data/l13/float_check_2026-10-08.json`

## Phase 7: Polish

- [x] T018 Update `PLAN.md` L1.3 status and `PROGRESS.md` with counts and N
- [x] T019 `python3 -m pytest -q` green; RYDE replay still BLOCK
- [x] T020 Sweep the rest of the universe (b011–b026) on `phase-b/l1.3-event-sets`; all 2,431 done
- [x] T021 Audit positives: add the `stale_quote` flag for ghost quotes (research R10), backfill it from the stored windows, and report positives without either flag

## Dependencies

T001 → T008. T004 → T005 → T006 → T007 → T008 → T009. T010 → T011 → T012 → T013 → T014 → T015.
T016 → T017 is independent of the sweep. T018–T019 last.
