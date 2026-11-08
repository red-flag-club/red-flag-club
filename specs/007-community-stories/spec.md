# Feature Specification: Community Stories and "Pump & Dump Defender" brand

**Feature Branch**: `feature/community-site` (stacked on spec 006, not yet merged)

**Created**: 2026-10-16

**Status**: Draft

**Input**: Owner, 2026-10-16: "Add the option to share your story along with
mine. No need to put my name or personal information; names and personal data
will be anonymised. A page with stock name, number of victims and timestamp.
Objective is to protect the community by sharing true stories. Record voice to
transcript so there is no need to type. A shared story first comes to my
private repo; we run Claude to anonymise it and generate tags without changing
the storyline. Users can read other stories by browsing tags or stocks.
Engage users at least 5-10 minutes. Rename the page to something catchy for
marketing on Facebook, YouTube etc."

## Decisions

| Question | Decision | Why |
|---|---|---|
| Name | **Red Flag Club** — "pump-and-dump checks & real stories"; tagline "The investment club that tells you when to walk away."; #RedFlagClub (replaced the first choice, *Pump & Dump Defender*, on 2026-10-16) | Turns the scammers' own hook — the free "investment club" — against them, and is about the community, not the tool. "Red flag" is everyday language on social media and ties together the risk lists, the stories and the quiz. Names with "pump" in them sit next to pump-*signal* apps in app stores and search (PumpAlert, Pump Detector), the opposite of what this is. No existing product by this name was found in a web search; trademark and domain checks are still the owner's to do |
| How a story reaches the private repo | Browser → a tiny **Cloudflare Worker** (free tier) → **encrypted** file in a separate private *inbox* repo | A static site can't accept posts; the laptop may be off; the Worker is always on and free. Encryption with the owner's public key means the inbox repo only ever holds ciphertext, so a leaked token or repo reveals nothing |
| Voice | Browser speech-to-text (Web Speech API), editable transcript; typing always available | No audio is stored or sent to us. In Chrome the browser's speech service (Google) does the recognition — the page says so. Not available in Firefox; the button hides itself |
| Anonymisation | Owner runs Claude Code with the `story-anonymise` skill on decrypted stories, then a deterministic **checker** and a **human approval** before anything is published | "Run Claude" as asked, without auto-publishing anything a model wrote |
| What is kept | The storyline, the stock(s), the month, the channel and tactics, a loss *range* | What helps others recognise the pattern |
| What is removed | Names (replaced by roles: "the 'professor'"), phone numbers, emails, handles, account and order numbers, exact addresses, employer, exact dates (month kept), exact amounts (range kept) | Personal data and anything that identifies a person |
| "Number of victims" | **People who shared a story** per stock, with first/last month | Self-reported, unverified — the page says exactly that |

## User Scenarios & Testing

### US1 - Share a story by voice or text (P1)
**Acceptance**: a visitor can speak or type, edit the transcript, pick the
stock(s), channel and rough loss range, tick consent, and submit; the page
confirms with a reference id; nothing is published until approved. Without a
configured endpoint the form explains how to share later and submits nothing.

### US2 - Private, encrypted intake (P1)
**Acceptance**: the Worker rejects oversize or consent-less posts, bot
honeypot hits and (when enabled) failed Turnstile checks; it writes one
encrypted JSON file per story to the inbox repo; the plaintext never touches
disk outside the owner's machine; decrypt works with the owner's private key
(tested across Node WebCrypto and Python).

### US3 - Anonymise without changing the story (P1)
**Acceptance**: the checker fails a draft that contains an email, phone,
handle, URL (other than regulators), long digit run, or a name from a
"names to remove" list, that drops a stock ticker from the original, that is
less than 60% of the original length, or whose tags are outside the
vocabulary. Approved stories are the only ones exported.

### US4 - Read and browse (P1)
**Acceptance**: a Stories page with cards (title, stocks, month, channel,
tags, read time), filters by tag / stock / channel and text search; a story
page with full text and "read next" (same stock or tactic); a Stocks page
listing each stock with number of people who shared, first and last month,
and today's risk check link.

### US5 - Engagement (P2)
**Acceptance**: a "Spot the red flag" quiz (10 scenarios, instant
explanations, score), tactic counts chart, and read-next chains — enough
material for a 5-10 minute visit, all static.

### US6 - Brand and sharing (P2)
**Acceptance**: new name everywhere on the site, social preview card
(Open Graph / Twitter tags + image), share buttons that copy a link (no
third-party scripts).

### Edge cases
- Story names a real company that was impersonated → replaced by
  "[a well-known brokerage]"; the checker can't detect it, so the human
  approval step lists all capitalised words for the owner to scan.
- Story contains a threat of self-harm → the skill flags it for the owner and
  the page shows a support line note; not published as-is.
- Duplicate submissions → same ticker + near-identical text are flagged.

## Requirements
- **FR-001** No submission is stored unencrypted outside the owner's machine.
- **FR-002** Nothing is published without `stories approve <id>` by the owner.
- **FR-003** Exported stories contain only anonymised fields (schema in contracts).
- **FR-004** The site works without the Worker (read-only); the share form
  degrades to instructions.
- **FR-005** External requests only from the share page, only to the configured
  Worker and (optionally) Cloudflare Turnstile.
- **FR-006** Voice transcription is opt-in per use and explained.
- **FR-007** Stock pages say "people who shared a story", never "victims
  confirmed".

## Success Criteria
- **SC-001** Encrypt in Node (Worker code) → decrypt in Python round-trips (test).
- **SC-002** Checker catches each PII class in its test corpus (test).
- **SC-003** Stories, quiz and stocks pages render offline from fixtures.
- **SC-004** Cost stays $0 (Workers free tier: 100,000 requests/day).
