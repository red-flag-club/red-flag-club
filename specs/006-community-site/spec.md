# Feature Specification: Community Site (GitHub Pages)

**Feature Branch**: `feature/community-site`

**Created**: 2026-10-16

**Status**: Draft

**Input**: Owner, 2026-10-16: "Create the GitHub page with a menu based
dashboard and analytic page for user to query various options this tool
provide. Think well and analyse what could be good for community who are
already impacted by pump and dump or already part of some community group. It
should show top 100s penny stocks of this day, week, month. Can there be a
chatbot assistant as well?"

**PLAN.md items**: Layer 2 delivery (L2.3 for everyone, not only the owner);
builds on specs 003-005.

## Who this is for (analysis)

| Person | Situation | What they need from the page |
|---|---|---|
| **Already pumped** | Holding or sold a collapsed small cap | "Was it a pump?" timeline for their ticker; what to do now (report: SEC, FINRA, FBI IC3; tax loss); a loud warning about *recovery scams*, which target exactly them; a safe place to tell the story |
| **Being pitched in a group** | In a WhatsApp/Telegram/Discord "investment club" — the FBI saw ramp-and-dump complaints up 300%+ in 2025 | A phone-fast ticker lookup with a shareable link; today's risk list to cross-check the "teacher's" pick; the red-flag checklist for group tactics |
| **Group moderator** | Runs a community, wants to protect members | Shareable per-ticker links, downloadable JSON/CSV the group's bot can read, a weekly summary |
| **Researcher / journalist** | Wants evidence | Method, track record with N, downloads |

### The design risk this page must not create

A public "top 100 penny-stock gainers" list is exactly the attention a pump
needs. So every list is a **risk list**, never a pick list:

- Sorted and labelled as "biggest run-ups — highest risk", each row with its
  red flags and Layer 1 verdict.
- A fixed banner with what history says about buying after such runs (the
  project's own research: the +20%/−10% rule on 61,129 trades won 30.1% of the
  time against a 40% breakeven, −2.9% per trade, negative every year; 349 of
  2,841 ≥100% runs collapsed ≥70% within 20 sessions).
- Published after the close, not live.
- Wording describes **patterns and risk**, never fraud: "matches the
  pump-and-dump risk profile", not "is a scam". No accusation of any company
  or person.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ticker lookup with a shareable link (P1)

Someone pitched `XYZ` opens `…/#/t/XYZ` on a phone and sees: on the risk list
today or not, run-up over day/week/month, volume vs its normal, Layer 1
verdict and why, SEC red flags, days on the scan, and any past episode and how
it ended.

**Acceptance**: a symbol in the data shows those fields; a symbol not in the
small-cap set says so and suggests what to check by hand; the URL can be pasted
into a chat and opens the same view.

### User Story 2 - Top 100 penny stocks: day, week, month (P1)

**Acceptance**: three tabs, each at most 100 rows, penny = close under $5 (the
SEC's penny-stock threshold) with a minimum trading-value floor; sorted by
run-up; every row shows verdict and flags; the risk banner is always visible;
the data date and N are shown.

### User Story 3 - "I got pumped — what now?" help (P1)

**Acceptance**: one page with reporting links (SEC tips, FINRA, FBI IC3),
recovery-scam warning, tax-loss pointer, red-flag checklist for group tactics,
and how to share a story safely (never account numbers or screenshots with
personal details).

### User Story 4 - Analytics / query page (P2)

**Acceptance**: filter the small-cap set by price band, run-up over
day/week/month, volume ratio, verdict, flags and days on scan; sort; see N;
download the result as CSV.

### User Story 5 - Assistant (P2)

A chat box answers: "is ABC a pump?", "what's pumping this week?", "I lost
money on ABC", "how do I report", "what are the red flags", "what is a ramp and
dump". Answers come from the site's own data and help text.

**Acceptance**: works with no server, no API key and no cost; every ticker
answer links to the lookup view; unknown questions get suggestions, never an
invented answer; no answer recommends buying.

### User Story 6 - Track record and community (P2)

**Acceptance**: outcomes of past risk-list episodes with forward/backfilled N;
a "Stories" section linking to the site repository's GitHub Discussions with
posting guidance (no personal or account data).

### User Story 7 - Publishes itself (P1)

**Acceptance**: after each scan refresh the site is rebuilt; a scheduled
workflow on the owner's runner publishes it four times a market day to a
public site repository; the code repository stays private.

### Edge Cases

- No scan data yet: pages say so; nothing crashes.
- A split inside a window: the change is not ranked and the row is flagged.
- Prices: provider terms usually forbid redistributing raw prices on a free
  tier, so absolute prices are **off by default** — the page shows percentages,
  price bands (under $1, $1–5, $5–30) and shapes normalised to 100. The owner
  can turn prices on after checking the provider licence.

## Requirements *(mandatory)*

- **FR-001**: The site is static (HTML, CSS, JS, JSON), menu-based, works on a
  phone, light and dark, with no external requests by default.
- **FR-002**: Menu: Today · Top 100 (day / week / month) · Risk scan · Look up
  · Analytics · Track record · Assistant · Got pumped? · About.
- **FR-003**: Every view carries "not investment advice / not a buy signal"
  and the data date; risk lists carry the history banner.
- **FR-004**: Exported data contains no account, position or personal data and,
  unless enabled, no absolute prices (tested).
- **FR-005**: Downloadable JSON and CSV with a documented schema, for
  community bots.
- **FR-006**: The assistant is deterministic and offline; an LLM-backed
  assistant is a later, opt-in phase with a spend cap.
- **FR-007**: Language describes risk patterns, never accuses.
- **FR-008**: Build is part of the scan refresh; publishing is a separate,
  opt-in workflow on the self-hosted runner.

## Success Criteria *(mandatory)*

- **SC-001**: Fixture build produces all pages and data; RYDE shows as VETO on
  its 2024-09-06 risk list in a replay build.
- **SC-002**: Site payload (HTML+JS+CSS+JSON) under 2 MB for a 10k-symbol day.
- **SC-003**: Ticker lookup answers from a shared link in under 1 s on a phone
  after the page loads.
- **SC-004**: Zero absolute prices in exported data with prices off (tested).
- **SC-005**: Running cost stays $0.

## Assumptions

- The owner creates a public repository for the built site (e.g.
  `pd-defence-site`) and enables Pages on it; the code repo stays private.
  (GitHub Pages is free only for public repos, and a Pages site is public
  either way.)
- Stories live in GitHub Discussions on the public site repo (free, moderated
  by the owner). Embedded comments (Giscus) are optional and off by default
  because they load a third-party script.
- The owner's own loss is not published on the site unless they choose to.
