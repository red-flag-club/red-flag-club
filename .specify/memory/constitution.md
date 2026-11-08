# pd-defence Constitution

This constitution restates the hard rules in `CLAUDE.md` in Spec Kit form so that
`/speckit-plan` and `/speckit-analyze` can gate against them. `CLAUDE.md` is the
source of truth: if the two ever disagree, `CLAUDE.md` wins and this file is
amended to match.

## Core Principles

### I. Read-Only Against the Brokerage (NON-NEGOTIABLE)

No spec, plan, task or implementation may call an order-placing or otherwise
state-changing brokerage tool — `place_*_order`, `cancel_*_order`,
`create_alert`, `create_watchlist`, `create_scan`, `update_scan_*`, watchlist
edits, or any other write. Read-only tools (`get_*`, `preview_scan`) are
permitted. There is no standing exception: a task that seems to need a write
stops and asks the owner.

Rationale: the project exists because of a real five-figure loss; a defence system
that can place orders is a liability.

### II. No Lookahead (NON-NEGOTIABLE)

Every backtest or data-loading function takes an `as_of` date and touches only
data dated `<= as_of`. Every new data-loading function ships with a test proving
it, including a truncation test (cutting the series cannot add a signal).

Rationale: a backtest that leaks future data produces confident wrong numbers,
which is worse than no backtest.

### III. Point-in-Time Data Only

Values read from a live API today (float, market cap, shares outstanding) MUST
NOT be used as historical inputs. Historical structural inputs come from
filings dated `<= as_of`, with an explicit `source` field on every value.

Rationale: RYDE's float reads ~110M today; it was 3.0M in September 2024.

### IV. Recall Over Precision

Every threshold is biased toward false positives. No change may raise precision
by lowering recall without stating so explicitly. Event definitions (e.g. the
collapse label) MUST NOT be loosened to manufacture positives; if a target count
is unreachable, the honest result is to report the shortfall and stop.

Rationale: a false positive costs one skipped trade; a false negative cost
a five-figure loss.

### V. Honest Data Hygiene and Reporting

- Bars with `interpolated == true` are dropped before any calculation, and the
  survivor count is recorded.
- Every metric is reported with the sample size that produced it.
- Every known bias (survivorship, unsampled ranges, synthetic fixtures) is
  stated next to the result it affects.
- Expensive collected data (universe snapshots, event sets) is committed to git
  so a lost workspace cannot erase it.

## Scope Constraints

- **Defence path** (`src/`, Layers 1-3) decides only *not* to trade. It never
  emits a buy signal, sizes up, or recommends entry.
- **Research track** (`research/`) may import from `src/`; `src/` never imports
  from `research/`. No research finding relaxes a defence-path threshold.
- **Stack:** Python 3.11+, stdlib and pandas only unless justified. Pure
  functions in `src/`; nothing stateful in the scoring path. Data access is
  injected (MCP tools are not callable from plain Python), so tests run offline.
- **Reference cases** RYDE (BLOCK on 2024-09-06) and DJT (WARN, never BLOCK)
  are re-run after any threshold change.

## Development Workflow

- Features follow Spec Kit: `/speckit-specify` → `/speckit-plan` →
  `/speckit-tasks` → `/speckit-implement`. Specs live in `specs/NNN-name/`.
- `PLAN.md` remains the project roadmap; each Spec Kit feature implements one
  `PLAN.md` item and cites it.
- `python3 -m pytest -q` from the repo root MUST pass before every push.
- `PROGRESS.md` is updated at the end of every session.
- Phase gates in `PLAN.md` are hard stops: if a gate fails, report and stop.
  No real money before Phase 6 forward validation.

## Governance

This constitution supersedes conflicting guidance in specs, plans and tasks;
`CLAUDE.md` supersedes this constitution. Amendments require the owner's
approval, a matching change to `CLAUDE.md` where a hard rule is affected, and a
version bump: MAJOR for removing or redefining a principle, MINOR for adding
one, PATCH for wording. `/speckit-analyze` reports any plan or task that
conflicts with a principle as CRITICAL.

**Version**: 1.0.0 | **Ratified**: 2026-10-08 | **Last Amended**: 2026-10-08
