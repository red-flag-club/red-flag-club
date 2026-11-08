# Feature Specification: Layer 2 Scan Log and Private Dashboard

**Feature Branch**: `feature/layer2-scan-dashboard`

**Created**: 2026-10-15

**Status**: Draft

**Input**: Owner, 2026-10-15: a page refreshed 4 times a day during US market
hours with pump-and-dump data, "if it detects some true penny stocks where
high volume of pump is happening", stored locally in DuckDB with good graphs;
keep infrastructure cost as low as possible; private for now.

**PLAN.md items**: L2.1 (the screen), L2.2 (daily snapshot logger and outcome
backfill), L2.3 (`is_pumping` cross-check). It produces the forward,
lookahead-free dataset L2.4 needs; L2.4 itself (re-running the harness on six
months of log) is a later spec.

## Why

Layer 1 can only be judged on history it was tuned on (gate not met: recall
0.783, FP 0.782, N=295/400). Layer 2's real job is a forward record: every day,
which small caps ran up, what Layer 1 said about them that day, and — once 20
sessions have passed — whether they collapsed. That record cannot leak the
future, because it is written before the future happens. The dashboard is how
the owner (and later the community) sees it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Daily scan log (Priority: P1)

After each session, the system screens the whole US market for small-cap
run-ups, appends every hit to a permanent log with that day's Layer 1 verdict,
and never rewrites a past entry.

**Why this priority**: The log is the asset; every day not logged is lost for
good.

**Independent Test**: Feed three sessions of synthetic market snapshots with one
pumping symbol; the log gains exactly the expected rows, re-running adds none,
and the verdict recorded for day N is identical whether or not days N+1..N+3
exist.

**Acceptance Scenarios**:

1. **Given** a session's market snapshot, **When** the scan runs, **Then**
   every symbol meeting the screen is logged with its date, close, returns,
   relative volume, the reason it was logged, and its Layer 1 verdict as of
   that date.
2. **Given** a session already logged, **When** the scan runs again, **Then**
   no row is added, changed or removed.
3. **Given** missed sessions (laptop off), **When** the scan next runs,
   **Then** each missed session is scanned in date order, each using only data
   up to its own date.
4. **Given** a split took effect inside the look-back window, **When** the
   screen computes run-ups, **Then** it uses only bars after the split and the
   row notes the split.

---

### User Story 2 - Outcome labels (Priority: P1)

For every logged symbol, once enough sessions have passed, the system records
whether it met the collapse definition (≥100% in ≤10 sessions, then ≥70% down
within 20). Forward recall and false-positive rate of Layer 1 are computed from
these labels, with N.

**Why this priority**: Without outcomes the log cannot validate anything.

**Independent Test**: A synthetic pump that collapses 8 sessions after its peak
is labelled positive only once 30 sessions after first being logged have
elapsed; before that it is "pending".

**Acceptance Scenarios**:

1. **Given** a logged symbol with fewer than 30 sessions since first logged,
   **Then** its outcome is pending.
2. **Given** enough sessions, **Then** the label follows the L1.2 definition
   exactly (shared code, not a copy).
3. **Given** labelled outcomes, **Then** forward metrics report recall (a VETO
   logged on any session up to the peak) and FP rate (a VETO anywhere in a
   non-collapsing episode), with N.

---

### User Story 3 - "Is it pumping?" (Priority: P2)

From any chat agent, ask whether a symbol is on the scan: today, how many of the
last 20 sessions, first and last seen, and the current Layer 1 verdict.

**Independent Test**: A symbol logged on 3 of the last 20 sessions returns
`days_on_scan = 3` and the dates; an unlogged symbol returns `on_scan_today =
false` plus its check.

**Acceptance Scenarios**:

1. **Given** a symbol never logged, **Then** the answer says so and still gives
   the Layer 1 check.
2. **Given** any answer, **Then** it is not a buy signal and says so.

---

### User Story 4 - Private dashboard (Priority: P2)

The owner opens one bookmarked page and sees: the latest scan (hits, verdicts,
a small price chart per hit), hits per day over the last three months, and the
forward-validation table. It refreshes four times on market days without
anyone doing anything.

**Independent Test**: Build the page from fixture data; it lists the fixture
pump with VETO, shows its chart, and the validation table shows N.

**Acceptance Scenarios**:

1. **Given** no token in the URL, **When** the dashboard is requested,
   **Then** it is refused.
2. **Given** a refresh run, **Then** the page shows when its data was last
   updated and which session that data is from.
3. **Given** free end-of-day data, **Then** the page says prices update once a
   day after the close; intraday refreshes pick up new SEC filings and catch up
   missed sessions.

### Edge Cases

- Market snapshot not yet published for today: the run scans what exists and
  retries the missing session on the next run.
- First run with no history: backfill enough sessions for the screen and the
  Layer 1 check (60 sessions since spec 005; first draft said 14 months) before logging; rows logged during backfill
  are marked `backfilled` so they are never mixed with true forward rows in
  forward metrics.
- Free-tier rate limit mid-backfill: stop cleanly, resume next run.
- A symbol changes ticker or is delisted: its log rows stay; its outcome may
  stay pending forever and is reported as such.
- One-bar bad prints: flagged on the row (REED rule), still logged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The screen MUST implement PLAN.md L2.1 with the inputs free data
  provides: close between $1 and $30, and a 5-session run-up ≥ 50% or a
  21-session run-up ≥ 50% (the after-close variant). Relative volume against
  the symbol's own 30-session average is recorded, not required. Market-cap
  and float filters MUST NOT be applied while those inputs are unknown; this
  widens the screen (more false positives), which is the permitted direction.
- **FR-002**: The scan log MUST be append-only and keyed by (session, symbol);
  no code path updates or deletes a log row.
- **FR-003**: The Layer 1 verdict on a row MUST be computed from data dated on
  or before that row's session (truncation-tested).
- **FR-004**: Rows created by backfill MUST be marked and excluded from forward
  metrics.
- **FR-005**: Outcomes MUST use `src/collapse_events.find_runs` and be decided
  only once 30 sessions after first logged have elapsed.
- **FR-006**: The system MUST expose `is_pumping` and `scan_latest` as
  read-only MCP tools.
- **FR-007**: A refresh MUST run four times on US market days (default 10:00,
  12:30, 15:00 and 17:30 ET), be idempotent, and be runnable by hand.
- **FR-008**: The dashboard MUST be a self-contained static page (no external
  scripts or fonts), regenerated on each refresh, served only behind the same
  token as the MCP endpoint, and say "not investment advice / not a buy signal".
- **FR-009**: Charts MUST be readable in light and dark mode and carry their N.
- **FR-010**: Every metric MUST show the N that produced it, and the page MUST
  state the Layer 1 gate status.
- **FR-011**: No new paid service; no order tools; no personal data on the page.

### Key Entities

- **Market snapshot**: every US stock's OHLCV for one session.
- **Scan run**: when a refresh ran, which sessions it scanned, how many hits,
  what failed.
- **Scan log row**: session, symbol, close, returns, relative volume, reason,
  flags (split, bad print, backfilled), Layer 1 verdict and reasons.
- **Outcome**: symbol, first logged session, label (pending / collapsed /
  no collapse), peak, drawdown, decided-on date.

## Success Criteria *(mandatory)*

- **SC-001**: On fixture data, the synthetic pump is logged on its first
  qualifying session, and RYDE (real 2024 bars) is logged on 2024-09-05 (+74%
  in 5 sessions) with VETO on 2024-09-06, its peak, and later labelled
  collapsed.
- **SC-002**: Re-running any refresh changes zero existing log rows (tested).
- **SC-003**: Truncation test: verdicts logged for day N are identical with and
  without later sessions present.
- **SC-004**: The dashboard page is under 1 MB, loads with no network requests
  beyond itself, and is refused without the token.
- **SC-005**: Running cost stays $0 beyond what spec 003 already uses.
- **SC-006**: After six months of forward rows, the L2.4 harness can read the
  log without transformation.

## Assumptions

- **Market-wide data**: one call per session returns every US stock's daily bar
  (Massive "grouped daily", free tier, 5 calls/minute). Third-party sources
  did not confirm this endpoint is on the free plan; the plan makes the owner's
  first run verify it and documents the fallback.
- **Prices are end-of-day**: free tiers have no intraday data, so the four
  daily refreshes change prices once (after the close) and otherwise refresh
  SEC filings, catch up missed sessions and rebuild the page.
- **Private**: the page is for the owner. Showing provider prices publicly needs
  a data licence and is out of scope (going-public spec).
- **Runs on the laptop** inside the spec 003 container; laptop off means missed
  runs, caught up next time.
