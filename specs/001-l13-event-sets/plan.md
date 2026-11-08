# Implementation Plan: L1.3 Event Sets

**Branch**: `phase-b/l1.3-event-sets` | **Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)

## Summary

Build L1.3's labelled event sets from a read-only universe snapshot. brokerage MCP tools can only
be called from an agent turn, and large responses spill to JSON files on disk. The design splits
the work accordingly: the agent makes the MCP calls, and a stdlib CLI (`scripts/l13.py`) ingests
the spilled payload files into compact, committed records. All labelling logic is a pure module
(`src/event_sets.py`) built on the unchanged L1.2 `find_runs`.

## Technical Context

**Language/Version**: Python 3.11+ (runs on 3.13 here)
**Primary Dependencies**: stdlib only; pytest for tests
**Storage**: JSON / JSONL files under `data/`, committed to git via `.gitignore` carve-outs
**Testing**: pytest, offline, synthetic and recorded fixtures
**Target Platform**: Claude Code session (cloud container) with the brokerage MCP server
**Project Type**: single project (library + CLI)
**Performance Goals**: one 10-symbol, 2022→today daily payload ingests in < 2 s
**Constraints**: ≤ 10 symbols per `get_equity_historicals`; ≤ 200 rows per `preview_scan`, no
pagination; no brokerage writes; no lookahead
**Scale/Scope**: ~2,000–3,500 symbols in the $0–500M universe; 100–300 expected positives
market-wide (PLAN.md), far fewer reachable from survivors

## Constitution Check

| Principle | How the design complies | Status |
|---|---|---|
| I. Read-only | Universe via `preview_scan` (persists nothing). No `create_scan`. | PASS |
| II. No lookahead | Every `event_sets` entry point takes `as_of` and raises `LookaheadError` on any later bar; truncation test included. | PASS |
| III. Point-in-time | Market cap is today's value, used only to *select* the universe, never as a model input. Stated as a bias. | PASS (bias stated) |
| IV. Recall over precision | `find_runs` thresholds untouched; censored runs go to *pending*, which cannot inflate either set. Shortfall is reported, not engineered away. | PASS |
| V. Honest hygiene | Interpolated and zero-price bars dropped and counted; report prints N for every number; data committed. | PASS |
| Fence | `src/event_sets.py` imports `src.collapse_events`; nothing under `research/` imports it, so the `research/` path convention is unaffected. | PASS |

Post-design re-check: PASS. One convention changes: `src/event_sets.py` is the first `src` module
that imports another `src` module, so CLAUDE.md's rule is restated as "modules that `research/`
imports must not import other `src` modules".

## Project Structure

### Documentation (this feature)

```text
specs/001-l13-event-sets/
├── spec.md
├── plan.md              # this file
├── research.md          # decisions and rejected alternatives
├── data-model.md        # record shapes on disk
├── quickstart.md        # the agent/CLI loop, step by step
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output
```

### Source Code (repository root)

```text
src/event_sets.py            # pure: clean_bars, label_events, EventRecord, LookaheadError
scripts/l13.py               # IO CLI: universe-add, universe-build, next-batch, ingest, report
scripts/float_check.py       # NOT BUILT: small-cap filings 404 (research R8)
tests/test_event_sets.py     # hygiene, censoring, lookahead, RYDE/RETO fixtures
tests/test_l13_cli.py        # band merge, saturation, resume, idempotent ingest
tests/fixtures/l13/          # trimmed real payloads (RYDE, RETO, a scan band)
data/universe/               # bands.jsonl, snapshot_<date>.json      (committed)
data/events/                 # events_<batch>.jsonl                  (committed)
data/l13/progress.json       # resume state                          (committed)
```

**Structure Decision**: single project. Pure logic in `src/` per the constitution; IO lives in
`scripts/` so `src/` stays side-effect free.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Agent-in-the-loop data fetch | MCP tools are not callable from Python | A direct HTTP client to the brokerage would need credentials this project does not hold and would bypass the MCP read-only surface |
