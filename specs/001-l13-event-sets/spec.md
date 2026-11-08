# Feature Specification: L1.3 Event Sets

**Feature Branch**: `phase-b/l1.3-event-sets`

**Created**: 2026-10-08

**Status**: Implemented (full universe swept, N=2,429 + 2 seeds; 349 positives; US4 result 0/5)

**Input**: User description: "Phase B of RECONCILE_AND_BUILD_PROMPT.md — rebuild the L1.3
small-cap universe and the collapse/control event sets, commit them so they cannot be lost again,
scale up in resumable batches, report the positive count honestly, and validate `float_as_of`
against live filings."

Implements `PLAN.md` L1.3 and the outstanding L1.1 live check. Governed by
`.specify/memory/constitution.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Labelled event sets that survive the session (Priority: P1)

The owner needs a committed set of collapse events (positives) and non-collapse runs (controls)
from small-cap US stocks, so that L1.4 can measure Layer 1's recall and false-positive rate.

**Why this priority**: L1.4 and L1.5 cannot start without it, and the previous attempt was lost
because nothing was committed.

**Independent Test**: Run the event-set builder over stored price payloads for a handful of
symbols that include RYDE and RETO; the committed output lists RYDE's Sep-2024 run as a positive,
and a fresh clone reproduces the same counts.

**Acceptance Scenarios**:

1. **Given** RYDE daily bars, **When** the builder labels them, **Then** the run peaking
   2024-09-06 is a positive with drawdown ≥ 70%.
2. **Given** a run whose peak is fewer than 20 sessions before the data end and which has not yet
   fallen 70%, **When** labelled, **Then** it is recorded as *pending*, never as a control.
3. **Given** bars flagged `interpolated` or with non-positive prices, **When** labelled, **Then**
   they are dropped first and the dropped count is recorded per symbol.
4. **Given** an `as_of` date, **When** any bar dated after it is passed in, **Then** the builder
   refuses (lookahead guard) rather than silently using it.

---

### User Story 2 - Resumable scale-up with an honest running count (Priority: P2)

The owner needs the sweep to proceed in batches across sessions, with a progress file recording
which symbols are done, and a report of positives, controls, pending and symbols processed after
every batch.

**Why this priority**: the pilot found 0 positives in 25 symbols; reaching ≥ 100 positives needs
thousands of symbols and will not finish in one sitting.

**Independent Test**: Process two batches, delete the working payloads, re-run the builder; the
done-set is unchanged and no symbol is processed twice.

**Acceptance Scenarios**:

1. **Given** a progress file listing completed symbols, **When** the next batch is requested,
   **Then** only symbols not yet completed are returned, in a fixed seeded order.
2. **Given** a completed batch, **When** the report runs, **Then** it prints positives, controls,
   pending, symbols processed and the positive rate, each with its N.
3. **Given** the positive count is below 100 when the budget is exhausted, **Then** the report
   says so and the collapse definition is unchanged.

---

### User Story 3 - Universe snapshot from read-only scans (Priority: P2)

The owner needs today's list of US-listed stocks under $500M market cap, including the
sub-$73.8M range the pilot never sampled, captured without any brokerage write.

**Why this priority**: the event sweep iterates this list; without it there is nothing to sweep.

**Independent Test**: Merge stored scan payloads; the snapshot lists every band with its
`total_items`, no band exceeds the 200-row cap, and tickers are de-duplicated.

**Acceptance Scenarios**:

1. **Given** a scan band whose `total_items` exceeds the rows returned, **When** merged, **Then**
   the band is flagged *saturated* and must be split before the snapshot counts as complete.
2. **Given** overlapping bands, **When** merged, **Then** each ticker appears once.

---

### User Story 4 - Live check of the historical float resolver (Priority: P3)

The owner needs to know how often `float_as_of` can read a real IPO prospectus, because the
fallback path is weaker and L1.4's results must carry that caveat if it dominates.

**Independent Test**: Run `float_as_of` against live filings for 5 recent small-cap IPOs and
record the source used and the share count for each.

**Acceptance Scenarios**:

1. **Given** 5 symbols, **When** resolved, **Then** the hit rate for `ipo_prospectus` is recorded
   as k/5, alongside each symbol's result or error.

### Edge Cases

- Pre-listing placeholder bars with all-zero OHLC that are not flagged `interpolated` (seen on
  RYDE 2024-02-29..03-04).
- Prices adjusted for big reverse splits (RETO trades at $244,000 split-adjusted in 2023): ratio
  tests are unaffected, absolute-price filters must not be applied.
- A symbol returning no bars at all, or only interpolated bars.
- A run that both collapses and is followed by a later run in the same symbol (each is its own
  event).
- A symbol that appears in the seed list and in the universe (counted once).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The universe MUST be built only with read-only tools (`preview_scan`); no scan is
  created or modified.
- **FR-002**: The universe snapshot MUST cover market cap $0–$500M in bands each returning
  fewer rows than the 200-row cap, record every band's bounds and `total_items`, and be committed.
- **FR-003**: The builder MUST drop `interpolated` bars and bars with any non-positive OHLC before
  labelling, and record kept/dropped counts per symbol.
- **FR-004**: The builder MUST label runs using the unchanged L1.2 definition (≥ 100% in ≤ 10
  sessions, then ≥ 70% drawdown within 20 sessions).
- **FR-005**: Runs with fewer than 20 sessions after the peak and no ≥ 70% drawdown yet MUST be
  labelled *pending* and excluded from both positives and controls.
- **FR-006**: Every builder function MUST take `as_of` and reject input bars dated after it.
- **FR-007**: Each event record MUST store symbol, ramp start, peak, trough, run-up, drawdown,
  label, and the OHLCV window from 60 sessions before ramp start to the end of the trough window,
  so L1.4 can replay it without re-fetching.
- **FR-008**: Progress MUST be persisted after every batch in a committed file; batches are drawn
  in a fixed seeded order from symbols not yet done.
- **FR-009**: The report MUST print positives, controls, pending, symbols processed, positive rate,
  and the positives:controls ratio, each with N, plus the stated biases.
- **FR-010**: Known positives found outside the scan path (RYDE, RETO) MUST be included as a
  separately tagged seed set and never double-counted.
- **FR-011**: The float check MUST record, per symbol, the `source`, share count, and any error.

### Key Entities

- **Universe snapshot**: date, band list (bounds, total_items, rows, saturated), de-duplicated
  ticker list with market cap at snapshot time.
- **Event record**: one labelled run with its replay window and provenance (batch id, origin:
  `scan` or `seed`).
- **Progress file**: snapshot used, seed, ordered symbol list, completed symbols with their bar
  stats, batch history.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Universe snapshot and event sets are in git; a fresh clone reproduces the report.
- **SC-002**: 100% of processed symbols have recorded bar-hygiene stats.
- **SC-003**: Either ≥ 100 positives and ≥ 300 controls are reached (PLAN.md gate), or the report
  states the shortfall with N and the work stops without changing the collapse definition.
- **SC-004**: The float check reports a hit rate over exactly 5 symbols.
- **SC-005**: The RYDE and RETO reference events are reproduced by the builder in tests.

## Assumptions

- Today's universe is a survivorship-biased proxy for 2022→present: names that already delisted
  are absent, and "market cap < $500M" is measured today, not at each run's start.
- Daily bars from 2022-01-01 are sufficient; intraday data is out of scope.
- The 200-row cap applies per preview; there is no pagination.
- No scanner write is authorized; if read-only scans prove insufficient, work stops and asks.
