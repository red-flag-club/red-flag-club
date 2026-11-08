# 🚩 Red Flag Club

**The investment club that tells you when to walk away.**

Free, open-source tools and a community website against **pump-and-dump scams
in small-cap stocks**, especially the ones run through "free" WhatsApp,
Telegram and Facebook investing groups.

**Site:** https://red-flag-club.github.io · **Stories:** [red-flag-club/stories](https://github.com/red-flag-club/stories) · **How we work:** [docs/workflow.md](docs/workflow.md) · **Board:** [spec pipeline](https://github.com/orgs/red-flag-club/projects)

> Independent and community-run: not affiliated with, endorsed by or sponsored
> by any brokerage (including Robinhood), data provider or company named here.
> Names are used only to describe compatibility.
>
> Not financial advice. Nothing here ever says "buy". We never call a company
> or person a fraud; we show red flags and the evidence behind them.

---

## If it already happened to you

1. **Stop sending money**, including any "fee", "tax" or "compensation trade"
   to win back what you lost. That is the second scam.
2. **Save everything:** chat exports, screenshots, broker confirmations.
3. **Report it.** It's free and still useful years later: FBI
   [ic3.gov](https://www.ic3.gov), SEC [sec.gov/tcr](https://www.sec.gov/tcr),
   your broker's fraud team.
4. **You were targeted, not foolish.** These scripts are written by
   professionals. If you want to, [share your story](https://red-flag-club.github.io/#/share),
   anonymously, so the next person recognises it.

---

## What, why, how

**What.** A website and a set of checks that answer one question before
someone buys a small stock they were "tipped" in a group: *does this look like
a pump-and-dump?* Around that question: daily risk lists of stocks that are
running up, true stories from people who lost money, a quiz that teaches the
script, and step-by-step help for victims.

**Why.** The playbook is the same every time. A Facebook ad or a "wrong
number" message, a free group with a friendly "professor", months of sensible
tips to build trust, then one tiny stock that "we all buy together", exact
buy orders with screenshots for "approval", a crash, and finally a
"compensation plan" that asks for more money. Research on investment-scam
warnings (e.g. a 2025 Ontario Securities Commission study, N=1,465) found that
a warning shown **before** the pitch cut the share of people who bought the
promoted asset from 38.1% to 21.3%, while generic risk warnings did almost
nothing. Victims also tend to stay silent out of shame, so the same
script works on the next group. Red Flag Club is built to be the warning
that arrives in time, and the place where stories stop being secret.

**How.**
- **Checks from public data:** daily prices and SEC filing history, never a
  brokerage connection. Every check uses only data that existed on the day
  being judged (no hindsight), and is tested for that.
- **A scan of the whole market every trading day,** logged permanently, so
  the track record can't be rewritten.
- **Stories submitted through an encrypted form,** anonymised, checked by a
  script for personal data, and published only after a human reviews them.
- **Every change is specified, reviewed and tested before it ships.** Issues
  move through Spec Kit phases on a public board, and a maintainer approves
  each step ([docs/workflow.md](docs/workflow.md)).

---

## Features built

Everything below is built and tested. The public site goes live at launch
(see the board).

| Feature | What it does | Why it matters | How it works | Status |
|---|---|---|---|---|
| **Look up a ticker** (`#/t/XYZ`) | Verdict (VETO / CAUTION / NO FLAGS), the red flags behind it, recent run-up, filing history, past outcomes; a link you can paste back into the group | The moment of risk is when someone pitches you a stock. This is the check to do first | Layer 1 on daily bars and the SEC filing index as of the last session | Built. The verdict is a **checklist**, not a guarantee; see Layer 1 below |
| **Top 100 run-ups** (day / week / month) | Penny stocks (under $5, at least $25k traded a day) with the biggest moves, each with its verdict and flags | Groups push stocks that are already moving; seeing the list helps you recognise the stock you're being pitched | Daily end-of-day data; risk-framed with the backtest base rate | Built (prices hidden for licence reasons; percentages and shapes shown) |
| **Risk scan** | $1-$30 stocks up 50% or more over 5 or 21 sessions, with the Layer 1 verdict on each day | A market-wide early warning that doesn't depend on anyone reporting the stock | Layer 2: append-only scan log, outcome labels 30 sessions later | Built; forward validation needs 6 months of data (about May 2027) |
| **Track record** | How the logged stocks ended (collapsed or not), recall and false alarms with sample sizes | Trust has to be earned in public, including the misses | Outcomes computed only from data after each log entry; backfilled rows shown separately | Built |
| **Stories** | Real, anonymised first-person accounts; browse by tactic, stock, channel; "people who shared a story" per stock | People recognise a scam from someone else's story faster than from a warning | `stories.json` exported after review; see Story pipeline | Built |
| **Share your story** | Speak or type; it arrives encrypted | Silence is what the scheme relies on | Browser speech-to-text (nothing recorded by us), a Cloudflare Worker that encrypts with the reviewer's public key, a private inbox | Built; needs the Worker deployed |
| **Quiz** | 10 "spot the red flag" situations with explanations | Prebunking: learning the script before you meet it is the warning that works | Static questions in `web/quiz.js` | Built |
| **Assistant** | Answers "is XYZ a pump?", "I lost money, what now?", "what are the red flags?" from the site's data | Some people would rather ask than read | Runs entirely in the browser (`web/assistant.js`), no API key, no data sent anywhere; never recommends buying (tested) | Built |
| **Got pumped?** | What to do now, where to report, "recovery" scam warning, taxes | The hours after the crash are when the second scam lands | Static help page | Built |
| **Analytics** | Filter every small cap by band, change, volume, verdict, scan days; CSV download | For moderators, journalists and researchers | Same daily data | Built |
| **MCP server** | `check_ticker`, `was_i_pumped`, `pump_scan`, `monitor_digest`, `is_pumping`, `scan_latest`, `data_status` for AI assistants | Lets an assistant (Claude or another) run the same checks when someone asks it about a stock | Read-only HTTP service, token-gated, Docker, free data tiers (Tiingo + SEC EDGAR), cached in DuckDB | Works; self-hosted ([docs/mcp_server.md](docs/mcp_server.md)) |
| **Position rules** (Layer 3) | Time stop, sell-only ladder, "abandoned position" alert | If you're already in, the risk is holding through the overnight gap | Pure functions in `src/layer3.py` | Built and tested; not connected to any account |

### The checks, honestly

| Layer | What | Evidence so far | What that means |
|---|---|---|---|
| **1: pre-trade check** (`src/layer1.py`) | A structural fingerprint from FINRA's pump-and-dump guidance (tiny float, foreign-issuer filings, long silence at the SEC while the price runs) plus a 2-sigma price/volume anomaly that latches once it fires | Walk-forward on 295 collapsed run-ups and 400 controls: catches 78.3% of pumps before the peak, but also flags 78.2% of controls (unknown float counted as a red flag). The release gate is **not met** | Treat a VETO as "this has the shape of a pump", not as proof. Treat NO FLAGS as "nothing found", not as safe |
| **2: market scan** (`server/scan.py`) | Every $1-$30 stock up 50% or more over 5 or 21 sessions, every day, with Layer 1's verdict as it was that day | The forward log starts when the daily scan goes live; outcomes are labelled after 30 sessions | Forward recall and false-alarm rates will be published with sample sizes |
| **3: position rules** (`src/layer3.py`) | Rules for someone already holding | Unit-tested on synthetic replays of a real 2024 collapse | Never connected to a brokerage |

**Research finding (why we never say "ride the pump"):** buying after a
detected run-up with a +20% take-profit and −10% stop lost money in every year
tested: 61,129 trades, 30.1% winners against a 40% break-even, −2.9% per trade.

**Reference cases** (regression tests): RYDE in September 2024 must be
blocked before its peak. DJT in October 2024 is a large, heavily filing
company that must only get a warning, never a block.

---

## Not yet built: help wanted

| Item | What | Why | How you can help |
|---|---|---|---|
| **Layer 1 precision** | Cut false alarms without missing more pumps | 78% false alarms makes the VETO easy to ignore | New point-in-time features (float from SEC filings, promotion signals), walk-forward experiments. Specs only; never trade recall for precision silently |
| **Float and market cap for small caps** | A point-in-time source | The strongest red flag (tiny float) is "unknown" today | Parse float from SEC filings (10-K, 20-F, F-1, 424B) as of each date |
| **Paste-a-message red-flag checker** | Paste a group message and get the tactics it uses | Meets people where the scam happens, in the chat | Rules from the story tags and the quiz; runs in the browser; nothing sent anywhere |
| **"Recovery" scam detector** | Flags fee-to-recover and "compensation trade" pitches | The second scam targets people who already lost money | Same approach as the message checker |
| **Report helper** | Turns your notes into an SEC TCR / FBI IC3 report with a checklist of evidence | People don't report because it feels pointless or hard | Static form, generated in the browser, nothing stored |
| **Prebunking alerts** | A short, shareable "what happens next" card for groups that are still in the trust-building phase | Warnings before the pitch are the ones that work | Content and design; sharing to WhatsApp and Facebook |
| **Translations** | Site, quiz, assistant and help in other languages | These groups target communities in their own languages | Use the translation issue form |
| **More story reviewers** | More than one person who can decrypt and approve stories | One reviewer is a bottleneck | Spec for per-reviewer keys and an approval log |
| **Forward validation (L2.4)** | Publish Layer 1's live recall and false alarms | The backtest is not the proof; live results are | Needs 6 months of the forward log (about May 2027) |
| **Live position monitor (L3.3)** | Alerts for people who choose to connect their own data locally | Holding through the gap is where most losses happen | Local-only design; never a hosted brokerage connection |
| **Prices on the site** | Show exact prices | Easier to read | Needs a data source whose licence allows republishing |
| **Browser extension** | Red flags next to a ticker on social media pages | Context at the moment of the pitch | Spec first |

Every item starts as an issue, then a spec, before any code: [open one](https://github.com/red-flag-club/red-flag-club/issues/new/choose).

---

## How it fits together

```
 Free data (Tiingo EOD, SEC EDGAR)
        │
        ▼
 maintainer-run container ── Layer 1/2 checks ── scan log (append-only) ──► site data (JSON, no prices)
        │                                                                          │
        │                                                                          ▼
        └─ MCP server (read-only tools)                       red-flag-club.github.io (GitHub Pages)
                                                                                   ▲
 Share form ─► Cloudflare Worker (encrypts) ─► private inbox ─► review ─► stories repo + site
```

| Repo | What's in it |
|---|---|
| [`red-flag-club`](https://github.com/red-flag-club/red-flag-club) (this one) | All the code, specs and docs |
| [`red-flag-club.github.io`](https://github.com/red-flag-club/red-flag-club.github.io) | The built site (a bot publishes it; don't edit) |
| [`stories`](https://github.com/red-flag-club/stories) | Published, anonymised stories (CC BY-NC-ND 4.0) |
| [`.github`](https://github.com/red-flag-club/.github) | Org-wide issue forms, PR template, `spec-gate`, board sync |
| private repos | Story inbox (ciphertext only), deployment, licensed data. Nothing personal is ever public |

## Repository layout

| Path | What |
|---|---|
| `src/` | The defence path: Layer 1 (`layer1.py`), point-in-time harness, event labelling, Layer 3, `check_ticker.py` |
| `server/` | MCP server, scan, outcomes, retention, site builder |
| `web/` | The site: plain HTML/JS/CSS, no trackers, no external scripts |
| `worker/stories/` | Cloudflare Worker that encrypts story submissions |
| `scripts/` | Story tooling (`stories.py`), synthetic fixtures, public export and leak gate, org set-up |
| `specs/NNN-name/` | Spec Kit specs, plans and tasks for every feature (001-008 so far) |
| `tests/` | Python tests, on synthetic data. Node tests are in `web/` and `worker/` |
| `docs/` | Workflow, methodology, server, site and story runbooks |

## Run it yourself

```bash
python3 -m pip install -r server/requirements.txt pytest
python3 -m pytest -q                     # Python tests, synthetic data, no network
node --test web/*.test.mjs worker/stories/*.test.mjs
python3 scripts/public_export.py check --tree .   # the leak gate CI runs
PD_PROVIDER=fixture python3 -m server.app          # the server on synthetic data
```

Some offline tools (`scripts/l13.py`, `scripts/l14.py`, the `payload` data
source) read payloads saved from a **brokerage that offers a read-only MCP
server**, such as Robinhood. The project never connects to a brokerage itself
and never places orders; a person's own AI assistant fetches the data with
read-only tools.

**Expected file format.** The parser (`parse_brokerage_payload` in
`server/providers.py`, and `clean_bars` in `src/event_sets.py`) reads the JSON
that Robinhood's MCP `get_equity_historicals` tool returns:
`{"data": {"results": [{"symbol": ..., "interval": "day", "bars": [{"begins_at", "open_price",
"high_price", "low_price", "close_price", "volume", "interpolated"?}]}]}}`,
prices as strings, `interpolated: true` on gap-fill bars (dropped before any
calculation). `tests/fixtures/synthetic/historicals.json` is a complete
example. Another brokerage's data works once it's converted to this shape;
an adapter per brokerage would be a welcome contribution.

The test fixtures are **synthetic** (`scripts/make_synthetic.py`): shaped like
the real episodes, anchored to publicly reported prices, and not market data.
Brokerage data isn't redistributable, so it never enters this repo.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). In short: open an issue (each form
asks what, why and how), a maintainer moves it through **Specify → Plan →
Tasks → Implement → Review** on the board, and your PR links the issue and
ticks the hard-rules checklist. We will not merge: buy signals, anything that
calls a company or person a fraud, personal data, hindsight in a backtest, or
a recall cut hidden behind a precision gain.

## Licences

Code: [MIT](LICENSE). Docs and site text: [CC BY 4.0](LICENSE-content).
Stories: CC BY-NC-ND 4.0 (in the stories repo). © Red Flag Club contributors.
