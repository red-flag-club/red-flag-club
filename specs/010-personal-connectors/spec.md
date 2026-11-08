# Feature Specification: Personal connectors: analyse your own accounts on your own machine

**Feature Branch**: `spec/010-personal-connectors`

**Created**: 2026-11-08

**Status**: Draft (phase: Specify)

**Issue**: red-flag-club/red-flag-club#19

**Input**: Maintainer, 2026-11-08: "This platform should provide connectors for
the community to connect their personal account if they want a detailed
analysis. For example my friends and I can connect to Robinhood or Vanguard to
fetch and analyse in my local cache."

## What, why, how

- **What:** a person runs Red Flag Club on their own computer and connects
  their own brokerage data (Robinhood, Vanguard, Fidelity, Schwab and others).
  They get a private report: red flags on every holding, warnings when too much
  is in one tiny stock, "was I pumped?" on past buys, and the position rules for
  anything already held.
- **Why:** the public site can't show price-based analysis (data licences), and
  people's real exposure is in their own accounts. In this project's founding
  story, everything went into one microcap over three days; a private report
  saying "92% of your account is in one stock that matches the pump profile"
  would have been the warning that mattered. Data people fetch from their own
  accounts is theirs to analyse on their own machine.
- **How:** local-only, read-only connectors that import into a local cache.
  Nothing is uploaded, nothing is shared with the public site, nothing can
  place an order. The existing local server (`server/`, Docker) runs the
  checks.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Import a CSV export and get a private report (Priority: P1)

A Vanguard customer downloads their holdings and transactions as CSV from the
Vanguard website, drops the files into Red Flag Club running on their laptop,
and gets a report in their browser at `localhost`.

**Why this priority**: every broker offers CSV export; it needs no password,
no API and no third party, so it works for everyone today.

**Independent Test**: import synthetic CSVs in each supported broker's format;
check the report, and check that no network request leaves the machine except
to the price and SEC sources the user enabled.

**Acceptance Scenarios**:

1. **Given** a holdings CSV, **When** it is imported, **Then** account numbers are dropped (at most the last 4 digits kept for labelling) and holdings are stored only in the local cache.
2. **Given** holdings with 80% in one stock whose filings show 4 or more red flags, **When** the report runs, **Then** it shows a concentration warning first.
3. **Given** past buys, **When** the report runs, **Then** each buy gets a "was I pumped?" answer using only data known on the buy date, with hindsight shown separately.
4. **Given** the user clicks "delete my data", **When** it finishes, **Then** the cache file is gone and a fresh report is empty.

---

### User Story 2 - Robinhood through its official read-only tools (Priority: P2)

A Robinhood customer who uses an AI assistant with Robinhood's own MCP server
asks: "check my holdings with Red Flag Club." The assistant reads positions and
orders with the read-only tools and passes them to the local server's
`monitor_digest` and `was_i_pumped`.

**Why this priority**: it exists in part today (`monitor_digest`); this story
makes it a documented, tested connector.

**Acceptance Scenarios**:

1. **Given** positions passed in from the assistant, **When** the digest runs, **Then** account numbers are discarded and nothing is written except the local cache the user chose.
2. **Given** the connector, **When** its interface is inspected, **Then** it has no method that writes to the brokerage (tested).

---

### User Story 3 - Friends and family (Priority: P3)

The maintainer and friends each want their own analysis.

**Acceptance Scenarios**:

1. **Given** a friend, **When** they want reports, **Then** the default is that they install their own copy (one command), so their data never sits on someone else's machine.
2. [NEEDS CLARIFICATION: should one local install support several people as separate profiles, each encrypted with its own passphrase and with explicit consent, or is "one person, one install" enough?]

---

### User Story 4 - Personal price source for price-based checks (Priority: P3)

For the pump-profile check and charts on their own holdings, the user can plug
in their own free data source: their own Tiingo or Massive key, or a local-only
price fetcher. Data stays on their machine and is labelled "personal use".

**Acceptance Scenarios**:

1. **Given** a personal key, **When** the report runs, **Then** price-based flags appear in the private report and are never exported anywhere.

### Edge Cases

- A CSV in an unknown format: show which columns were found and which are missing; import nothing partially.
- Options, crypto, funds: listed but not scored (the checks are for small-cap stocks).
- The same holding in two accounts: shown per account and combined.
- A user shares a screenshot of their report: the report shows no full account numbers, and a "remove amounts before sharing" toggle hides dollar values.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Connectors MUST be read-only. The connector interface has no order, transfer, alert or watchlist methods, and a test proves it (hard rule 1).
- **FR-002**: Everything MUST run on the user's machine. No hosted service, no telemetry, no upload; the only network calls are to the data sources the user enabled (SEC EDGAR, their own price key, their own brokerage tools).
- **FR-003**: Full account numbers MUST never be stored. Only the last 4 digits may be kept, as a label.
- **FR-004**: The local cache MUST be deletable in one action, and SHOULD be encrypted at rest [NEEDS CLARIFICATION: OS-level disk encryption assumed, or the app's own passphrase?].
- **FR-005**: No credentials MUST be needed for the CSV path. Connectors that need a password to log in to a brokerage on the user's behalf (unofficial APIs, screen scraping) are out of scope: they break brokerage terms and would mean storing passwords.
- **FR-006**: Personal data MUST never reach the public site, the public repos or the scan log. The public build reads no personal tables, and a test proves it.
- **FR-007**: Reports MUST follow the defence-path rules: never a buy signal, never "add to this position", position rules are sell-only.
- **FR-008**: The first supported CSV formats: Vanguard, Robinhood, Fidelity, Schwab [NEEDS CLARIFICATION: confirm order], each with a synthetic sample file and tests.
- **FR-009**: Aggregator services (Plaid, SnapTrade and similar) are out of scope for v1; they would send account data through a third party and need their own privacy review.

### Key Entities

- **Account**: broker, label (last 4 digits at most), owner profile.
- **Holding**: symbol, quantity, average cost, as-of date, account.
- **Trade**: symbol, side, quantity, price, date, account (used for "was I pumped?" and the position rules).
- **Report**: per-holding flags, concentration, past-buy answers, generated-at.

## Success Criteria *(mandatory)*

- **SC-001**: A first-time user imports a CSV and sees a report in under 5 minutes, without writing code.
- **SC-002**: With networking disabled except SEC EDGAR, the CSV path works and makes no other network call (tested).
- **SC-003**: No full account number appears in the cache, logs or report (tested with synthetic numbers).
- **SC-004**: Zero brokerage write calls are possible from the code (tested at the interface).

## Assumptions

- Users can export CSV from their brokerage's website (Vanguard, Fidelity, Schwab and Robinhood all offer this).
- Robinhood's official MCP server is used only through the user's own AI assistant, with read-only tools.
- This builds on the existing local server (spec 003), `monitor_digest` and `was_i_pumped`.
- Constitution note: the public deployment "never stores positions"; this feature stores them only in a personal local install that the user controls, which the plan phase must state explicitly.
