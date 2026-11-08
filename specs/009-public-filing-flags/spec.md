# Feature Specification: Public red flags from SEC filings, with links to live prices

**Feature Branch**: `spec/009-public-filing-flags`

**Created**: 2026-11-08

**Status**: Draft (phase: Specify)

**Issue**: red-flag-club/red-flag-club#18

**Input**: Maintainer, 2026-11-08: free market-data plans (Tiingo, Massive, Yahoo via
yfinance, a brokerage's own data) are licensed for personal use and don't allow
republishing prices or numbers calculated from them on a public site. Launch the
public look-up with red flags that come only from public-domain SEC filings, and
link out to free sites for live prices.

## What, why, how

- **What:** anyone can type a ticker on the public site and see the red flags
  that SEC filings show for it, each with a link to the filing, plus links to
  see the live price elsewhere.
- **Why:** the moment of risk is when someone is pitched a stock. The
  structural fingerprint from FINRA Regulatory Notice 22-25 (tiny float,
  foreign-issuer-only filings, long silence at the SEC, newly listed,
  unprofitable) is one of the strongest signals this project has: RYDE scored 6
  of 6 before its collapse. All of it can be read from SEC filings, which are
  public records. So the most useful check can be public, free and lawful,
  without any price data licence.
- **How:** SEC EDGAR's free JSON APIs (company tickers, submissions, XBRL
  company facts), point-in-time as of each filing date, built into static files
  for GitHub Pages. No price, and nothing calculated from a price, is
  published.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Check a ticker someone is pushing (Priority: P1)

Someone in a WhatsApp group is told to buy ABCD. They open the site, type ABCD,
and see: which of the filing red flags apply, what each one means in plain
words, the filing behind each (with a link to sec.gov), and buttons to see the
live price on Google Finance, Yahoo Finance or Nasdaq.com.

**Why this priority**: it is the whole point of the site, and it can launch
without any data licence.

**Independent Test**: build the site from the synthetic SEC fixtures; look up
the RYDE-shaped and DJT-shaped tickers; check the flags, the filing links and
the outbound links.

**Acceptance Scenarios**:

1. **Given** a ticker that files only 6-K forms, listed 6 months ago, last filed 82 days ago, with a reported float of 3.0M shares and a net loss, **When** it is looked up, **Then** it shows those five filing flags, with the filing for each, and "market cap: needs price data (not shown)".
2. **Given** a large domestic filer with recent 8-Ks, **When** it is looked up, **Then** it shows at most the flags that apply and no "high risk" summary.
3. **Given** a ticker the SEC doesn't list, **When** it is looked up, **Then** the page says it isn't an SEC-registered US listing (it may be OTC, foreign or mistyped), shows the general red flags, and still offers the live-price links.
4. **Given** any ticker page, **When** its data file is inspected, **Then** it contains no price, volume, percentage change or anything else calculated from market data.

---

### User Story 2 - "Going quiet" list (Priority: P2)

A public daily list of small issuers whose filings show several red flags and
that have recently stopped filing or just listed: the pattern that preceded
the ramp in this project's event sets.

**Why this priority**: it gives group moderators something to watch without a
price feed, and it is calculated from filings alone.

**Independent Test**: from fixtures, the list contains the RYDE-shaped issuer
on 2024-09-06 and not the DJT-shaped one.

**Acceptance Scenarios**:

1. **Given** the latest EDGAR snapshot, **When** the site is built, **Then** the list ranks issuers by the number of filing flags, then by days since their last filing, and shows no market data.

---

### User Story 3 - Same check for bots and assistants (Priority: P3)

The per-ticker filing flags are also available as static JSON, so group bots
and AI assistants can check a ticker without scraping the page.

**Acceptance Scenarios**:

1. **Given** `data/filings/ABCD.json`, **When** a bot reads it, **Then** it gets the flags, the evidence filings and the as-of date, under CC BY 4.0, with the "not a fraud finding" note.

### Edge Cases

- A company files late or amends a filing: flags use what was filed on or before the as-of date (no lookahead).
- Ticker changes and reused tickers: map through the CIK, show the company name, and say when the ticker changed.
- Float not reported in XBRL (common for foreign issuers): "float: not reported", never treated as a pass.
- SEC rate limit or outage: keep yesterday's files and show their date.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Public outputs MUST contain only data from SEC EDGAR (public domain) and this project's own text. Their schema has no price, volume or market-data-derived fields, and the leak gate rejects any file that has one.
- **FR-002**: Every flag MUST name its evidence: form type, filing date and a sec.gov link.
- **FR-003**: Every flag MUST be computed from filings dated on or before the as-of date, with a test proving later filings can't change it.
- **FR-004**: Unknown inputs (float or net income not reported) MUST be shown as unknown and, in any summary, counted as red flags (hard rule 4).
- **FR-005**: The market-cap flag MUST be shown as "needs price data (not shown)" until a data licence allows it.
- **FR-006**: Every ticker page MUST link to the live price on Google Finance, Yahoo Finance and Nasdaq.com. These are plain links; no data from those sites is fetched.
- **FR-007**: The EDGAR client MUST follow SEC fair-access rules: a User-Agent with a contact, at most 10 requests a second, and caching.
- **FR-008**: Wording MUST describe red flags and never call a company or person a fraud. Pages carry the not-advice and independence notes.
- **FR-009**: Reference cases: RYDE as of 2024-09-06 shows the foreign-issuer, listing-age, silence and unprofitable flags, and the float flag if its 3.0M float can be read from its filings (otherwise "float: not reported", counted as a red flag); DJT as of October 2024 shows no foreign-issuer or silence flag.

### Key Entities

- **Issuer filing profile**: CIK, ticker(s), name, form types on file, first filing date, last filing date, reported float (shares) with its source filing, latest annual net income with its source, as-of date.
- **Filing flag**: id, plain-language text, evidence filing, as-of date.

## Success Criteria *(mandatory)*

- **SC-001**: A look-up shows filing flags for any SEC-registered US-listed ticker in under 2 seconds on a phone.
- **SC-002**: Zero price or market-data-derived fields in any public file (leak gate and schema test).
- **SC-003**: Both reference cases pass as tests.
- **SC-004**: The public site launches without any paid data licence.

## Assumptions

- SEC EDGAR data is a US government public record, free to republish.
- Float from XBRL (`dei:EntityPublicFloat` is in dollars and only in annual reports; shares outstanding from cover pages) needs care; the plan phase decides the exact sources and their limits.
- Price-based checks (the pump profile, Top 100, risk scan) stay off the public site until a provider gives written permission or a licence is bought (see the maintainers' data-licensing notes).

## Open questions (for /speckit.clarify)

- Should the public summary show a score ("5 of 6 red flags") or only the list of flags? A score reads like a verdict.
- Should OTC tickers (not SEC-registered) get a page that only shows general red flags, or no page?
