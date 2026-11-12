# Feature Specification: Personal connectors: a browser extension (and a local helper) for your own accounts and data

**Feature Branch**: `spec/010-personal-connectors`

**Created**: 2026-11-08 · **Revised**: 2026-11-12 (browser-only; extension first; no hosted proxy)

**Status**: Draft (phase: Specify)

**Issue**: red-flag-club/red-flag-club#19

**Input**: Maintainer, 2026-11-08: "Provide connectors for the community to
connect their personal account if they want a detailed analysis." Revised
2026-11-12: "Let community members connect their own Tiingo, Massive or
Robinhood account with their API key or MCP interface; pull the data and store
it locally; nothing in the public repo; everything runs on the user's
machine." And: "The local helper and extension options are required for both
technical and non-technical people. A Docker image for technical people, but
the priority is a Chrome extension anybody can run. The extension stores the
local data set and pulls from the remote provider, and the site talks to the
extension to fetch and show different data sets. Everything runs in the
browser; nothing runs on a backend."

## What, why, how

- **What:** the **Red Flag Club extension** for Chrome. A person installs it
  from the Chrome Web Store, connects **their own** sources inside it (a Tiingo
  or Massive API key, their Robinhood account, files from any brokerage), and
  the extension pulls and stores the data on their computer. When they open
  red-flag-club.github.io, the site asks the extension for results and shows
  them: the Top 100 and risk scan with prices, full look-ups with history, red
  flags on their holdings, "was I pumped?", the position rules, and their own
  queries. People who prefer it can run the same thing as a **Docker image**
  on their machine instead.
- **Why:** free data plans and brokerage data are licensed to the account
  holder for personal use, so the public site can't republish them (spec 009),
  but the holder can analyse them on their own computer. An extension makes
  that possible for anyone (one click, no install of Python or Docker), and it
  can reach providers that an ordinary web page can't call. Nothing is
  uploaded, so the project never holds anyone's keys or data.
- **How:** everything runs in the person's browser. The extension holds an
  encrypted key vault, the connectors, a local database (IndexedDB) and the
  analysis engine. The public site stays static and only displays what the
  extension returns, over Chrome's extension messaging, which is restricted to
  red-flag-club.github.io. The Docker helper offers the same interface on
  `localhost`.

## Decisions

| # | Question | Decision | Why |
|---|---|---|---|
| D1 | Hosted proxy that forwards users' keys or tokens to providers | **Rejected.** No Red Flag Club server ever receives a key, token, account number or personal data | A proxy must decrypt traffic to forward it, so it sees every credential; "we don't store it" can't be proven; one breach exposes every account; a Robinhood token can also place orders; many keys from one server looks like key pooling under the providers' terms; and it is an always-on service for volunteers to secure |
| D2 | Primary way to connect | **Chrome extension (P1)** | One click for non-technical people; extensions may call provider APIs directly (host permissions), keep their own storage, and run without a backend |
| D3 | Technical users | **Docker local helper (P3)**, same message interface on `127.0.0.1` | Reuses `server/`; for people who prefer a desktop setup or another browser |
| D4 | Without either | The site works as today (spec 009 public flags), plus CSV import in the page, and browser-direct calls only to providers that allow them | No one is blocked from the free public check |
| D5 | Robinhood | **Only through the extension's read-only allowlist** (if Robinhood allows it, R2), the person's own AI assistant, or CSV. **Never through any server** | Its tools include order placing (hard rule 1) |
| D6 | Other browsers | Edge and Brave can install Chrome extensions; Firefox later (the same code, WebExtensions) | Chrome first by reach |

## Architecture (for orientation; the plan decides details)

```
 red-flag-club.github.io (static page)          Red Flag Club extension (on the user's computer)
 ─────────────────────────────────────          ──────────────────────────────────────────────
 shows results, asks for data      ──message──►  vault (keys, encrypted with the person's passphrase)
 (only from this site's address)   ◄──results──  connectors: Tiingo · Massive · Robinhood (read-only) · CSV
                                                 local database (IndexedDB): bars, holdings, trades, results
                                                 analysis engine (same checks as src/)
                                                        │
                                                        └── HTTPS ──► only the provider the person connected
```

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install the extension and connect a market-data key (Priority: P1)

Someone who has never used a terminal installs the extension from the Chrome
Web Store, opens it, creates a passphrase, pastes a free Tiingo or Massive key,
and chooses what to pull (their watchlist, or the whole market for the last N
sessions). The extension pulls in the background, respecting the free-tier
limits, and survives the browser closing. When they open the site, the Top 100,
risk scan and look-ups show full price-based results, marked "from your data,
on this device".

**Why this priority**: it is the whole feature for most people, and it needs no
technical skill.

**Independent Test**: load the unpacked extension in an automated Chrome with a
mock provider; connect a fake key; pull synthetic data; open the site; check
that (a) the extension's requests go only to the mock provider's host, (b) the
site shows the RYDE-shaped symbol as VETO on 2024-09-06, (c) the page itself
made no request to any provider.

**Acceptance Scenarios**:

1. **Given** the extension is not installed, **When** someone opens "My data" on the site, **Then** it explains what the extension does and links to the store listing, and everything public still works.
2. **Given** a valid Massive key, **When** a 70-session whole-market pull starts, **Then** it runs at 5 calls a minute, shows time remaining, and resumes after Chrome restarts.
3. **Given** pulled data, **When** the person looks up a ticker on the site, **Then** the result comes from the extension and the page shows its source and date.
4. **Given** a wrong passphrase, **When** the vault is opened, **Then** nothing is decrypted, and after repeated failures it waits before allowing another try.

---

### User Story 2 - Manage and delete (Priority: P1)

The extension's settings list each connected source, what was pulled, how much
space it uses and when; with refresh, disconnect, forget key, export my data
(to a local file) and **delete everything**. Uninstalling the extension also
deletes everything.

**Acceptance Scenarios**:

1. **Given** stored data, **When** "delete everything" is confirmed, **Then** the vault, database and settings are gone and the site shows the not-connected state.

---

### User Story 3 - Robinhood, read-only, through the extension (Priority: P2)

A Robinhood customer clicks "Connect Robinhood" in the extension, signs in on
Robinhood's own page, and the extension reads positions, orders and price
history through Robinhood's MCP server using only read-only tools. The site
then shows red flags on each holding, a concentration warning, "was I
pumped?" for past buys and the sell-only position rules.

**Why this priority**: it is where the founding loss happened; it depends on R2.

**Acceptance Scenarios**:

1. **Given** a connected account, **When** data is pulled, **Then** only allowlisted read tools are called, and account numbers are reduced to their last 4 digits before storage.
2. **Given** the server offers order, alert or watchlist tools, **When** the extension starts, **Then** it never shows or calls them (tested against a mock server that offers them).
3. **Given** Robinhood doesn't allow third-party sign-in (R2), **Then** the extension offers CSV import and the "use your own AI assistant" guide instead.

---

### User Story 4 - Import files from any brokerage (Priority: P2)

A Vanguard, Fidelity, Schwab or Robinhood customer drops their CSV exports
into the extension (or onto the site, which hands them to the extension). The
files are read locally; nothing is uploaded.

**Acceptance Scenarios**:

1. **Given** a supported CSV, **When** it is imported, **Then** holdings and trades are stored locally and no network request is made during the import (tested).
2. **Given** an unknown layout, **When** it is imported, **Then** the extension shows which columns were found and imports nothing partially.

---

### User Story 5 - Query your own history (Priority: P3)

On the site, with the extension connected, the person filters and sorts their
data ("small caps up 50% in 5 sessions in March", "my buys that matched the
pump profile"), sees charts and downloads results as a local CSV.

---

### User Story 6 - Docker helper for technical users (Priority: P3)

A technical user runs `docker run -p 127.0.0.1:8765:8765 ghcr.io/red-flag-club/helper`
(or the existing compose file), opens the site, and chooses "use local helper".
The helper offers the same requests as the extension, on `localhost` only, with
the same rules.

**Acceptance Scenarios**:

1. **Given** the helper is running, **When** the site connects, **Then** it accepts requests only from `https://red-flag-club.github.io` and only on 127.0.0.1, and answers the browser's private-network check.

### Edge Cases

- **Chrome stops the extension's background worker** (Manifest V3 does this after about 30 seconds idle): pulls are scheduled with alarms and resume where they stopped.
- **Storage:** the extension estimates the size before a pull and asks for unlimited storage at install; whole-market history can be hundreds of MB.
- **The site is opened in another browser, or the extension is disabled:** the site falls back to the public view (D4).
- **Another website tries to talk to the extension:** refused; only red-flag-club.github.io is allowed (and `localhost` only in a development build).
- **Extension update:** the stored data keeps working (versioned schema with migrations).

## Requirements *(mandatory)*

### Functional Requirements

**Where things run**
- **FR-001**: No Red Flag Club server MAY receive a key, token, account number, holding, trade or pulled data (D1). The public site stays static.
- **FR-002**: The extension MUST hold the connectors, the key vault, the local database and the analysis engine. The site only sends requests to the extension and displays its answers.
- **FR-003**: The extension MUST accept messages only from `https://red-flag-club.github.io/*` (Chrome `externally_connectable`), check the sender's origin on every message, and answer only the documented read requests. It never returns a key to the page.
- **FR-004**: The Docker helper MUST implement the same request interface on `127.0.0.1` only, accept only the site's origin, and follow every other rule here (D3).

**Sources**
- **FR-005**: Connectors for Tiingo (API key), Massive (API key), Robinhood (MCP sign-in, R2) and CSV files from Vanguard, Fidelity, Schwab and Robinhood [NEEDS CLARIFICATION: confirm the first CSV formats]. All share one interface: describe, connect, pull(window), status, disconnect.
- **FR-006**: Connectors MUST call only their provider's documented endpoints with the person's own credentials, respect the published free-tier limits, and label every result with its source.
- **FR-007**: The extension's host permissions MUST be limited to the supported providers' API hosts and SEC EDGAR; adding a provider is a reviewed change.

**Read-only, enforced (hard rule 1)**
- **FR-008**: The Robinhood connector MUST call only an explicit allowlist of read-only tools (positions, orders, historicals, fundamentals, SEC filing index, quotes). Tools that place, cancel, review or change orders, alerts, watchlists, transfers or options exercises MUST be unreachable, with a test against a mock server that exposes them.
- **FR-009**: The connector interface MUST have no write method (tested).

**Keys and personal data**
- **FR-010**: Keys MUST be stored only in the extension's vault, encrypted with a key derived from the person's passphrase (WebCrypto AES-GCM, with PBKDF2 or Argon2). The passphrase is never stored. The vault locks after a period of inactivity the person chooses.
- **FR-011**: Full account numbers MUST never be stored; at most the last 4 digits as a label.
- **FR-012**: "Delete everything" and uninstalling MUST remove the vault, database and settings (tested).
- **FR-013**: No telemetry, analytics or crash reporting. No network requests except to the providers the person connected and SEC EDGAR.

**Code integrity and store policy**
- **FR-014**: No remotely hosted code (Manifest V3 rule): the analysis engine, including any WebAssembly, ships inside the extension package. Extension pages use a strict Content Security Policy.
- **FR-015**: The extension's source MUST live in the public code repo (`extension/`), and each store release MUST be reproducible from a tagged commit, with its hashes listed on the site's About page.
- **FR-016**: The store listing MUST include a privacy policy stating FR-001, FR-010 to FR-013, and Chrome Web Store "limited use" compliance.

**Same analysis everywhere**
- **FR-017**: Verdicts from the extension and the helper MUST match the reference Python implementation (`src/`) on the shared synthetic fixtures, including RYDE (blocks 2024-09-06, pump trigger 2024-09-04) and DJT (warns only). [Decided in plan: Pyodide running `src/` inside the extension, or a JavaScript port with conformance tests.]
- **FR-018**: Results follow the defence-path rules: never a buy signal, never "add to this position", position rules sell-only, no claim that any company is a fraud.

### Key Entities

- **Source**: provider, kind (api-key, mcp, file), status, last pull, data window, size.
- **Bar**: symbol, date, OHLCV, provider, interpolated flag (filtered before any calculation, hard rule 5).
- **Account / Holding / Trade**: account labels limited to the last 4 digits.
- **Result**: check, symbol, as-of date, verdict, flags, computed-at.
- **Message**: request type (status, lookup, list, query, holdings report), parameters; response with source and as-of.

## Success Criteria *(mandatory)*

- **SC-001**: A person with no technical background installs the extension, connects a free key and sees a full price-based look-up on the site in under 10 minutes.
- **SC-002**: An automated network capture of the whole flow shows requests only to the site (static files), SEC EDGAR and the provider the person chose.
- **SC-003**: The Robinhood connector cannot call a write tool (mock-server test).
- **SC-004**: Extension and helper verdicts match the Python reference on 100% of the shared fixture cases.
- **SC-005**: "Delete everything" and uninstall leave no stored data (test).
- **SC-006**: Another origin's messages to the extension are refused (test).
- **SC-007**: The extension passes Chrome Web Store review.

## Research for the plan phase (must be answered before code)

- **R1, providers from an extension:** confirm each provider's terms allow API calls from a browser extension with the user's own key (Tiingo, Massive), and SEC EDGAR fair-access rules (User-Agent) from an extension.
- **R2, Robinhood MCP from an extension:** can an extension sign in to Robinhood's MCP server (`chrome.identity` web auth flow, client registration), and do Robinhood's terms allow a third-party client? If not, D5's other paths apply.
- **R3, analysis engine:** Pyodide inside the extension (one implementation, ~10 MB package, needs `wasm-unsafe-eval` in the extension's CSP, allowed in Manifest V3) versus a JavaScript port (smaller, two implementations).
- **R4, Manifest V3 limits:** background worker lifetime, alarms for long pulls, an offscreen document for long computations, storage quotas with `unlimitedStorage`.
- **R5, local helper and Chrome's private-network rules:** what the helper must answer for a public site to call `127.0.0.1`.

## Assumptions

- People create their own provider accounts; Red Flag Club has no accounts.
- The extension is published by the `red-flag-club` organisation's Chrome Web Store developer account (one-time USD 5 fee).
- Constitution note: the public deployment stores no positions or personal data; this feature stores them only on the person's own computer, in the extension or the helper, which the plan must state explicitly.
- Out of scope for v1: password-based or screen-scraping connectors, aggregator services (Plaid, SnapTrade), syncing between devices, Firefox and Safari builds.
