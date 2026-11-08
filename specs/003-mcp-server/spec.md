# Feature Specification: pd-defence MCP Server

**Feature Branch**: `feature/mcp-server`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "A read-only pd-defence MCP server packaged as a
Docker service. It exposes the defence-path verdicts as MCP tools (check_ticker,
pump_scan, was_i_pumped, monitor_digest). Market data comes from a free-tier
provider plus SEC EDGAR filing indexes, cached in a local DuckDB file. It never
places orders and stores no account numbers. Runs on the owner's laptop via
docker compose, exposed through their existing cloudflared tunnel with a bearer
token, deployed by a GitHub Actions workflow on a self-hosted runner. Repo stays
private."

**PLAN.md item**: L2.3 cross-check (`is_pumping(symbol)`), delivered as a
service so any chat agent can run it. It does not replace L2.1/L2.2 (the daily
scan log); it gives that later work a data store and a delivery channel.

## Why

Today every check needs a Claude session to pull ~14 months of bars through the
brokerage MCP (large payloads, spilled to files, re-parsed) and then run a
script. That costs tokens on every question and only works where the brokerage
connector is attached. A server that owns its data and answers with a short
verdict lets the owner ask "is XYZ a pump?" from any agent, at a fraction of the
tokens, and gives the later dashboard and community pages one source of truth.

The brokerage MCP remains the only source for the owner's **own** positions and
orders. This server never sees brokerage credentials.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask about a ticker before buying (Priority: P1)

The owner is pitched a penny stock, or is about to buy one. From a chat agent
they ask the server to check the symbol. They get back the Layer 1 verdict
(VETO / CAUTION / NO FLAGS), the reasons, the run-up numbers, the FINRA
structural score with what was unknown, and the earnings date if known — in a
few hundred words, not a payload.

**Why this priority**: This is the question that would have prevented the
owner's loss. Everything else builds on the same data path.

**Independent Test**: Load the RYDE fixture bars and filings into the store,
ask for a check as of 2024-09-06, and get VETO; ask for DJT as of its October
2024 window and get anything but VETO-on-structure.

**Acceptance Scenarios**:

1. **Given** a symbol with a ≥100% run-up in ≤10 sessions, **When** checked,
   **Then** the verdict is VETO and the reason names the run-up.
2. **Given** a symbol whose float or market cap cannot be resolved, **When**
   checked, **Then** the report says which inputs were unknown and scores them
   as red flags in the worst case, never as a pass.
3. **Given** any request, **When** answered, **Then** the text never contains a
   buy recommendation, a price target, or an entry signal.
4. **Given** a symbol the data provider does not know, **When** checked,
   **Then** the server returns a clear "no data" answer, not a NO FLAGS verdict.

---

### User Story 2 - "Was I pumped?" (Priority: P1)

Someone who lost money gives a symbol and the date they bought. The server
answers, using only what was knowable on that date, whether the stock matched
the pump-and-dump profile then, and separately shows what happened after
(peak-to-trough drawdown, return 5, 20 and 60 sessions later).

**Why this priority**: It is the owner's own story and the core of the planned
community feature; it also proves the no-lookahead rule end to end.

**Independent Test**: Ask about RYDE bought 2024-09-09. The verdict part must
be identical whether or not bars after 2024-09-09 are in the store; the outcome
part shows the collapse.

**Acceptance Scenarios**:

1. **Given** a buy date, **When** answered, **Then** the verdict uses only bars
   and filings dated on or before the buy date (truncation test).
2. **Given** a buy date less than 5 sessions ago, **When** answered, **Then**
   outcome horizons that have not elapsed are reported as "not yet", not
   estimated.
3. **Given** a buy date before the first available bar, **When** answered,
   **Then** the server says there is no data for that date.

---

### User Story 3 - Scan a list for pump profiles (Priority: P2)

The owner (or a scheduled job) passes a list of up to 50 symbols and gets a
compact table: symbol, verdict, run-up over 5/10 sessions, volume versus its
own baseline, sorted worst first.

**Why this priority**: Feeds the planned 4×-daily dashboard and watchlist
checks; less urgent than a single-name check.

**Independent Test**: A fixture list mixing a pump-profile series and flat
series returns the pump first with VETO.

**Acceptance Scenarios**:

1. **Given** more than 50 symbols, **When** submitted, **Then** the request is
   refused with the limit stated.
2. **Given** some symbols with no data, **When** scanned, **Then** they are
   listed as "no data" and do not stop the rest.

---

### User Story 4 - Rule check on positions the caller passes in (Priority: P2)

The chat agent may already hold the user's positions (from a brokerage's own read-only tools).
It passes symbol, quantity, average cost and optional order history; the server
returns the daily digest alerts (EXIT RULE, TIME STOP, EARNINGS, ABANDONED,
LOSS, VETO) using its own market data.

**Why this priority**: Moves the daily monitor's heavy part (bars) off the
chat's token budget. The personal data stays with the caller.

**Independent Test**: Pass one position below its 200-day average and confirm
EXIT RULE and LOSS; confirm nothing about the request is written to disk or
logs.

**Acceptance Scenarios**:

1. **Given** positions with an account number field, **When** submitted,
   **Then** the account number is ignored and never echoed back, stored, or
   logged.
2. **Given** a position, **When** the digest is built, **Then** the response
   carries the "no orders were placed" statement.

---

### User Story 5 - Run it on the laptop, deploy on push (Priority: P2)

The owner runs the server as a container on their laptop behind their existing
Cloudflare tunnel. A push to `main` that passes tests rebuilds and restarts it
through a self-hosted runner on the same laptop. Data survives restarts.

**Why this priority**: Required for the service to exist, but the tools above
are testable without it.

**Independent Test**: Build the image, start it with a token, call the health
endpoint, call a tool with and without the token.

**Acceptance Scenarios**:

1. **Given** no token configured, **When** the server starts listening on a
   non-local address, **Then** it refuses to start.
2. **Given** a request without the correct token, **When** received, **Then**
   it is rejected and no tool runs.
3. **Given** a redeploy, **When** the container restarts, **Then** cached data
   is still there.
4. **Given** a failing test suite, **When** pushed, **Then** the deploy job
   does not replace the running container.

### Edge Cases

- Provider rate limit hit mid-request: serve from cache if the cache covers the
  `as_of` date, otherwise answer "data unavailable, try later" — never a verdict
  on partial data.
- Provider returns synthesized/gap-fill or zero-volume placeholder bars: drop
  them and report the survivor count (hard rule 5).
- One-bar bad prints (REED-style): flagged in the report, not silently dropped.
- Reverse splits (common in penny stocks): the report states whether bars are
  split-adjusted; a run-up computed across an unadjusted split is flagged.
- SEC has no CIK for the symbol (OTC, delisted, renamed): filing inputs are
  unknown, scored as red flags in the worst case.
- `as_of` in the future, or a non-trading day: future dates are refused;
  non-trading days resolve to the last session on or before them.
- A tool call that would need a brokerage write: does not exist; the server has
  no brokerage connection at all.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The server MUST expose exactly these tools: `check_ticker`,
  `was_i_pumped`, `pump_scan`, `monitor_digest`, plus a `data_status` tool that
  reports cache coverage and provider health. No tool may place, change or
  cancel an order, create an alert or edit a watchlist.
- **FR-002**: Every verdict MUST be computed by the existing defence-path and
  check logic (Layer 1, Layer 3, check_ticker, monitor) — not by a re-implementation —
  so the RYDE and DJT reference cases hold for the server too.
- **FR-003**: Every tool that takes a date MUST use only bars and filings dated
  on or before it for the verdict. Outcome data after the date MAY be shown only
  in a section labelled as hindsight.
- **FR-004**: Point-in-time fields that the free sources cannot give
  historically (float, market cap) MUST be reported as unknown for any `as_of`
  before today and scored in the worst case.
- **FR-005**: Bars that are synthesized, gap-filled or all-zero placeholders
  MUST be dropped before any calculation and the survivor count reported.
- **FR-006**: Market data MUST be cached locally; repeat questions for the same
  symbol and range MUST NOT call the provider again. The cache MUST survive
  container restarts.
- **FR-007**: The market data source MUST be swappable without changing tool
  logic, and the server MUST run fully offline against cached or fixture data.
- **FR-008**: The server MUST require a shared secret on every tool request when
  reachable from outside the machine, and MUST refuse to start without one in
  that mode.
- **FR-009**: The server MUST NOT store or log account numbers, positions, or
  order history passed to `monitor_digest`. Logs record tool name, symbol(s),
  duration and outcome only.
- **FR-010**: Responses MUST be compact by default (a short text report plus a
  small structured summary) with an option for full detail.
- **FR-011**: Every tool response MUST say that it is not a buy signal and that
  no orders were placed.
- **FR-012**: The service MUST be packaged as a container started with one
  command, with data on a persistent volume and a health endpoint.
- **FR-013**: A CI workflow MUST run the full test suite on every push and pull
  request; a deploy workflow MUST rebuild and restart the container on the
  owner's laptop only after tests pass on `main`.
- **FR-014**: SEC requests MUST identify the requester as SEC requires and stay
  within its published request-rate limit; provider requests MUST stay within
  the free tier's limit.
- **FR-015**: Secrets (server token, provider key, SEC contact) MUST come from
  the environment or the CI secret store, never from the repository.

### Key Entities

- **Bar**: one daily session for a symbol — date, open, high, low, close,
  volume, source, adjusted flag, fetched-at.
- **Filing**: one SEC filing index entry — symbol, CIK, form type, filed date.
- **Fundamentals snapshot**: today's float / market cap where available, with
  the date it was read; never used for a past `as_of`.
- **Check record**: tool name, symbol, as_of, verdict, timestamp — for the
  scorecard. No personal data.

## Success Criteria *(mandatory)*

- **SC-001**: RYDE checked as of 2024-09-06 returns VETO; DJT as of
  2024-10-29 does not VETO on structure — through the server, on fixture data.
- **SC-002**: A single-ticker check answer is under 2,500 characters by default
  — at least 10× smaller than the bar payload the chat pulls today for the
  same question.
- **SC-003**: A cached check answers in under 2 seconds on the owner's laptop;
  an uncached one in under 15 seconds within free-tier limits.
- **SC-004**: 100% of requests without the token are rejected (tested).
- **SC-005**: `was_i_pumped` verdicts are byte-identical with and without
  post-date data present (tested on RYDE and a synthetic series).
- **SC-006**: Zero order-tool names appear in the server code (tested), and the
  service has no brokerage credentials.
- **SC-007**: From a merge to `main`, the laptop runs the new version within 10
  minutes without manual steps.

## Assumptions

- **Free data source**: a free-tier end-of-day provider with a personal API key
  is used for daily bars; SEC EDGAR (free, no key, contact string required) for
  filing indexes. The concrete provider is chosen in the plan. Intraday data is
  out of scope.
- **Who connects**: the owner's own chat agents (Claude Code and claude.ai).
  If a client cannot send a custom header, a secret-path URL is the fallback;
  the plan documents the trade-off.
- **Private**: the repository stays private; the server is for the owner. Going
  public (licensing, community features, dashboard) is a later spec.
- **Hosting**: the owner's laptop with Docker and an existing cloudflared tunnel;
  the tunnel's own config (hostname, routing) is the owner's and is documented,
  not automated. The laptop being off means the service is off.
- **Not a scanner of the whole market**: `pump_scan` checks a list it is given.
  A market-wide scan (L2.1/L2.2) is a later spec.
- **Layer 1 status**: the L1.4/L1.5 gate is not met (recall 0.783, FP 0.782,
  N=295/400), so every verdict is presented as a checklist aid, not a validated
  classifier.
