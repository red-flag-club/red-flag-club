# Feature Specification: L1.4 Walk-Forward Harness and L1.5 Tuning

**Feature Branch**: `phase-c/l14-harness`

**Created**: 2026-10-09

**Status**: Implemented; gate not met (recall 0.783, FP 0.782 at defaults, N=295/400)

**Input**: Phase C of `RECONCILE_AND_BUILD_PROMPT.md`. Replay Layer 1 session by
session over the L1.3 event sets using only data dated `<= T`, report recall,
median lead, FP rate and latch precision with N, then tune one knob at a time.

## User Scenarios & Testing

### User Story 1 - Honest replay (P1)

The owner needs to know whether Layer 1 would have blocked each collapse
before its peak, and how often it blocks runs that did not collapse.

**Acceptance Scenarios**:

1. **Given** an event and its filings, **When** replayed, **Then** at each
   session T `layer1_verdict` receives only bars dated `<= T` and an Issuer
   built only from filings and results public by T.
2. **Given** filings or results dated after the event, **When** added to the
   input, **Then** the replay does not change (truncation test).
3. **Given** RYDE's real filing index, **When** replayed, **Then** it returns
   BLOCK on or before its 2024-09-06 peak.
4. **Given** an input that cannot be known point-in-time (float, market cap,
   and anything the filing index does not cover), **Then** it is scored both as
   clear (`lo`) and as a red flag (`hi`), never silently as a pass.

### User Story 2 - Metrics with N (P1)

**Acceptance Scenarios**:

1. Recall, recall with lead >= 2, median lead, FP rate and latch precision are
   reported for every bound (`hi`, `lo`, pump-only) with N positives and N
   controls, for all positives and for positives without data-quality flags.

### User Story 3 - One-knob tuning (P2)

**Acceptance Scenarios**:

1. Knobs are tuned in PLAN order (structural threshold, latch, k, release
   ratio), one at a time, full re-run after each. `window` stays 5.
2. Every run is saved; the chosen value is the one that meets the gate with the
   least FP, or, if none meets it, the shortfall is reported and the defaults
   stay.

## Requirements

- **FR-001**: No brokerage writes. Filing indexes and financials come from
  read-only tools.
- **FR-002**: Every point-in-time input carries its rule and its unknown case
  (`src/harness.py` docstring table).
- **FR-003**: Events: every L1.3 positive plus a seeded (42) sample of 400
  controls; the control weight (population / sample) is applied to latch
  precision.
- **FR-004**: Results are reported for all positives and for positives without
  `suspect_bad_print` or `stale_quote`.
- **FR-005**: Collapse labels and L1.3 data are not changed.

## Success Criteria

- **SC-001**: PLAN.md gate: recall >= 0.85, median lead >= 2, FP <= 0.35, on
  the `hi` bound; or the shortfall is reported and Layer 1 stays a manual
  checklist.
- **SC-002**: RYDE replay BLOCKs on or before 2024-09-06; DJT stays WARN (not
  checkable: DJT is outside the < $500M universe and no DJT fixture exists).

## Assumptions

- The event sets are survivors only (L1.3 bias).
- The filing index has coverage holes (research R1); those make
  `stale_disclosure` unknown, not true.
