# Feature Specification: Personal connectors in the browser: your own accounts, your own data, your own machine

**Feature Branch**: `spec/010-personal-connectors`

**Created**: 2026-11-08 · **Revised**: 2026-11-12 (browser-only design)

**Status**: Draft (phase: Specify)

**Issue**: red-flag-club/red-flag-club#19

**Input**: Maintainer, 2026-11-08: "This platform should provide connectors for
the community to connect their personal account if they want a detailed
analysis." Revised 2026-11-12: "Let community members connect their own
account created in Tiingo, Massive or Robinhood, configured with their API key
or MCP interface. The GitHub Pages application should pull the relevant data
and store it in the local browser cache. Nothing is stored in the public
GitHub repo, but users can connect, pull and query historical data. It should
all run locally on the user's machine. Provide the option to pull data from
different sources through their own personal account."

## What, why, how

- **What:** a "My data" section of the public site
  (red-flag-club.github.io) where a person connects **their own** data
  sources: a Tiingo or Massive API key, their Robinhood account through
  Robinhood's read-only MCP tools, or files exported from any brokerage. The
  page pulls the data straight from the source into **that browser's own
  storage**, and runs the full Red Flag Club analysis there: price-based pump
  checks, the market-wide risk scan, look-ups with history, red flags on their
  holdings, "was I pumped?" on past buys, and the position rules.
- **Why:** free data plans and brokerage data are licensed to the person who
  holds the account, for personal use; the project can't republish them (see
  spec 009). But that person *can* analyse their own data on their own
  machine. Doing it in the browser means no install, no server, no Red Flag
  Club account, and nothing for the project to store, leak or be asked to hand
  over. Friends and family each use their own browser with their own keys.
- **How:** the site's code runs in the visitor's browser. Requests go from
  the browser directly to the provider the person chose. Results go into the
  browser's local database (IndexedDB) and never leave it. The site's servers
  (GitHub Pages) only ever serve the same static files to everyone.

## Trust model (what the person is trusting, stated on the page)

- **Red Flag Club never sees keys, account data or results.** There's no
  backend; GitHub Pages serves static files only.
- **Keys and data live in this browser only**, on this device, for this site's
  address. Clearing site data deletes them. They are not synced to other
  devices.
- **The person trusts the site's code.** Anyone who could change the published
  JavaScript could, in principle, read keys in the browser. Mitigations are in
  FR-009 to FR-012. The page says so plainly, and links to the exact source.
- **Their provider's terms still apply.** Using your own key for your own
  analysis is personal use; the page reminds people not to share exports.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect your own market-data key (Priority: P1)

A community member creates a free Tiingo or Massive account, copies their API
key into "My data → Connect a source", and chooses what to pull: the stocks
they care about, or (Massive) the whole market for the last N sessions. The
page pulls the data into their browser, showing progress and the provider's
free-tier limits, and can resume after a reload. Then the Top 100, the risk
scan and every look-up work with prices and history, for them only.

**Why this priority**: it unlocks the full price-based analysis that the
public site can't publish, for anyone, with a free key.

**Independent Test**: with a mock provider served from a test origin, connect
a fake key, pull synthetic data, and check that (a) the requests go only to
the provider's host, (b) the data is in IndexedDB, (c) the look-up for the
RYDE-shaped symbol shows VETO on 2024-09-06, (d) no request goes anywhere
else.

**Acceptance Scenarios**:

1. **Given** a valid key, **When** the person pulls 70 sessions of the whole market from Massive's free tier, **Then** the page respects the rate limit (5 calls a minute), shows time remaining, and can be closed and resumed.
2. **Given** pulled data, **When** the person looks up a ticker, **Then** they see the full check (pump profile, structural flags from SEC, history), marked "from your data, on this device".
3. **Given** a bad or expired key, **When** a pull starts, **Then** the page says so in plain words and stores nothing.
4. **Given** the person chooses "don't remember my key", **When** they close the tab, **Then** the key is gone and the data stays.

---

### User Story 2 - Connect Robinhood through its read-only MCP tools (Priority: P2)

A Robinhood customer clicks "Connect Robinhood", signs in on Robinhood's own
page (the standard MCP sign-in flow), and the site reads their positions,
orders and price history through Robinhood's MCP server, read-only. They get
red flags on each holding, a concentration warning, "was I pumped?" for past
buys and the sell-only position rules.

**Why this priority**: it's the account the founding story happened in, and
the place most at-risk people already hold stocks. It depends on research
item R2.

**Independent Test**: against a mock MCP server that exposes both read and
write tools, connect, pull, and check that only allowlisted read tools are
ever called, and that calling any other tool is impossible from the code.

**Acceptance Scenarios**:

1. **Given** a connected account, **When** data is pulled, **Then** only tools on the read-only allowlist are called (FR-004), and account numbers are dropped except the last 4 digits.
2. **Given** the MCP server offers order-placing tools, **When** the client starts, **Then** it never lists them in its UI and refuses to call them (tested).
3. **Given** the sign-in is cancelled or expires, **When** a pull runs, **Then** nothing is stored and the person is asked to reconnect.

---

### User Story 3 - Import files from any brokerage (Priority: P2)

A Vanguard, Fidelity or Schwab customer (or anyone whose provider can't be
reached from a browser) downloads their holdings and trades as CSV and drops
the files on the page. The files are read in the browser; nothing is
uploaded.

**Why this priority**: works for every brokerage today, with no key and no
sign-in.

**Acceptance Scenarios**:

1. **Given** a supported CSV, **When** it is dropped on the page, **Then** holdings and trades appear in "My data" and the file never leaves the browser (no network request during import, tested).
2. **Given** an unknown CSV layout, **When** it is dropped, **Then** the page shows which columns it found and imports nothing partially.

---

### User Story 4 - Query your own history (Priority: P3)

With data pulled, the person can filter and sort it ("small caps up 50% or more
in 5 sessions in March", "my buys that matched the pump profile"), see a
chart, and download their results as CSV to their own computer.

**Acceptance Scenarios**:

1. **Given** pulled data, **When** a query runs, **Then** it runs entirely in the browser and its results are only offered as a local download.

---

### User Story 5 - Manage and delete (Priority: P1)

"My data" lists each connected source, what was pulled, how much space it
uses, and when; with buttons to refresh, disconnect, forget the key, and
**delete everything**.

**Acceptance Scenarios**:

1. **Given** any stored data, **When** "delete everything" is confirmed, **Then** IndexedDB, local storage and any cached keys for the site are cleared, and the page shows an empty state.

### Edge Cases

- **A provider doesn't allow browser requests** (CORS): the page says so, and offers the CSV path or the optional local helper (FR-014) for that provider. It never routes keys through a third-party proxy.
- **Browser storage limits:** the page estimates the size before a pull (whole-market history can be hundreds of MB), asks the browser for persistent storage, and offers a smaller window.
- **Private/incognito windows:** data disappears when the window closes; the page warns.
- **Two people sharing one computer account:** they share the browser profile and therefore the data; the page recommends separate browser profiles.
- **The public site's code updates:** stored data keeps working (versioned schema with migrations).

## Requirements *(mandatory)*

### Functional Requirements

**Sources**
- **FR-001**: The person MUST be able to connect any of: Tiingo (API key), Massive (API key), Robinhood (MCP sign-in), and CSV files from Vanguard, Fidelity, Schwab and Robinhood [NEEDS CLARIFICATION: confirm the first CSV formats]. Each source is a connector with the same interface: describe, connect, pull(window), status, disconnect.
- **FR-002**: Connectors MUST call only their provider's documented endpoints, from the browser, with the person's own credentials. No Red Flag Club server, and no third-party proxy, is ever in the path.
- **FR-003**: Pulls MUST respect each provider's published free-tier limits, be resumable, and show progress and the provider's name on every result ("data: your Tiingo account").

**Read-only, enforced**
- **FR-004**: The Robinhood connector MUST call only an explicit **allowlist of read-only tools** (positions, orders, historicals, fundamentals, SEC filing index, quotes). Any tool whose name or description indicates a write (place, cancel, create, update, delete, add, remove, exercise, follow, review an order) MUST be unreachable from the code, with a test that runs against a mock server exposing such tools (hard rule 1).
- **FR-005**: No connector MAY place, cancel or change an order, alert, watchlist or transfer. The connector interface has no write method (tested).

**Local only**
- **FR-006**: All pulled data, results and settings MUST be stored only in the visitor's browser (IndexedDB / local storage) for the site's origin. Nothing is written to any repository, server or analytics service.
- **FR-007**: The site MUST make no network request with personal data except to the provider the person connected. The public data files the site already serves (spec 006/009) are fetched as before, without any personal data in the request.
- **FR-008**: Full account numbers MUST never be stored; at most the last 4 digits as a label.

**Keys and code integrity**
- **FR-009**: API keys MUST be kept only for the session by default. "Remember on this device" is opt-in, and stores the key encrypted with a passphrase the person chooses (WebCrypto, AES-GCM with a PBKDF2- or Argon2-derived key), never in plain text.
- **FR-010**: The site MUST ship a strict Content Security Policy: scripts only from the site itself, no inline scripts, and `connect-src` limited to the site, SEC EDGAR and the supported providers' API hosts, so injected code can't send keys elsewhere.
- **FR-011**: The site MUST load no third-party scripts, fonts, analytics or trackers (as today).
- **FR-012**: Each published build MUST be reproducible from a tagged commit of the public code repo, and list its commit and file hashes on the About page, so anyone can check the code they're running.

**Same analysis as everywhere else**
- **FR-013**: Verdicts computed in the browser MUST match the reference Python implementation (`src/`) on the shared synthetic fixtures (conformance tests), including both reference cases: RYDE blocks on 2024-09-06 with the pump trigger on 2024-09-04; DJT only warns. [Decided in plan: run `src/` in the browser via Pyodide, or port to JavaScript with conformance tests.]
- **FR-014**: An optional **local helper** (the existing server in `server/`, run with Docker on the person's own machine) MAY be offered for providers a browser can't reach, and for people who prefer a desktop setup. It follows the same rules: local only, read-only.
- **FR-015**: Results MUST follow the defence-path rules: never a buy signal, never "add to this position", position rules sell-only, no claim that any company is a fraud.

**Delete**
- **FR-016**: "Delete everything" MUST remove all stored keys, data and settings for the site in one action (tested).

### Key Entities

- **Source**: provider, kind (api-key, mcp, file), status, last pull, data window, size.
- **Bar**: symbol, date, OHLCV, provider, interpolated flag (filtered before any calculation, hard rule 5).
- **Account / Holding / Trade**: as in the earlier draft, with account labels limited to the last 4 digits.
- **Result**: check, symbol, as-of date, verdict, flags, computed-at.

## Success Criteria *(mandatory)*

- **SC-001**: A first-time visitor with a free Massive or Tiingo key goes from "Connect" to a full price-based look-up in under 10 minutes, with no install.
- **SC-002**: A network capture of the whole flow shows requests only to the site, SEC EDGAR and the provider the person chose (automated browser test with a mock provider).
- **SC-003**: The Robinhood connector cannot call a write tool (test against a mock MCP server that offers them).
- **SC-004**: Browser verdicts match the Python reference on 100% of the shared fixture cases.
- **SC-005**: "Delete everything" leaves no site data in the browser (test).
- **SC-006**: No personal data, key or pulled market data ever appears in a public repository (leak gate, and the public build reads no browser data).

## Research for the plan phase (must be answered before code)

- **R1, browser access per provider:** does each provider's API allow browser requests from another origin (CORS), and do its terms allow calling it from a browser with the user's own key? Tiingo, Massive and SEC EDGAR each need checking (SEC requires a User-Agent header, which browsers don't let pages set; SEC data may need to come from the site's own published files instead).
- **R2, Robinhood MCP from a web page:** can a browser-based MCP client connect to Robinhood's MCP server (sign-in flow, client registration, CORS), and do Robinhood's terms allow a third-party web app to do so? If not, the Robinhood paths are CSV import and the person's own AI assistant with the local helper.
- **R3, analysis engine in the browser:** Pyodide running `src/` unchanged (one source of truth, ~10 MB first load) versus a JavaScript port (smaller, two implementations to keep in step).
- **R4, storage:** realistic sizes for 70 and 500 sessions of whole-market small-cap bars in IndexedDB, and persistent-storage behaviour in Chrome, Safari and Firefox.

## Assumptions

- People create their own accounts with the providers; Red Flag Club has no accounts of its own.
- This replaces the earlier local-server-first draft of this spec; the local server stays available as an optional helper (FR-014).
- Constitution note: the public deployment stores no positions or personal data. This feature stores them only in the visitor's own browser, which the plan must state explicitly.
- Out of scope for v1: password-based or screen-scraping connectors (they break brokerage terms and would mean handling passwords), aggregator services such as Plaid or SnapTrade (third party in the path), and syncing data between a person's devices.
