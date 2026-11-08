# Methodology: how a verdict is made, and how well it works

This is the public summary. The full designs are in `specs/001`-`specs/005`,
and the code is in `src/` and `server/`. Every number below comes with the
sample that produced it.

## The question

*Before someone buys a small stock they were tipped, does it look like a
pump-and-dump?* The checks only ever answer "don't" or "no flags found". They
never say "buy".

## Layer 1: the pre-trade check (`src/layer1.py`)

Two independent gates combine into one verdict.

**A. Structural: is this the kind of stock these schemes use?** Six red
flags, from FINRA Regulatory Notice 22-25 on small-cap IPO ramp-and-dumps:

| # | Red flag | Why |
|---|---|---|
| 1 | Public float under 20 million shares | Few shares make the price easy to move. FINRA's threshold |
| 2 | Market cap under $100 million | Same reason |
| 3 | Files as a foreign private issuer only (6-K/20-F, no 10-K/8-K) | Lighter, slower disclosure |
| 4 | Listed less than 18 months ago | Most ramp-and-dumps follow recent small IPOs |
| 5 | Unprofitable | Nothing fundamental behind a run |
| 6 | No SEC filing for over 30 days | Silence while the price runs |

Four or more of six → **VETO**. An input we can't know (today: float and
market cap for most small caps) is scored **as a red flag** in the main
result, because a missed pump costs far more than a false alarm.

**B. Pump state: is it happening now?** The price-and-volume test from Nam &
Skillicorn (arXiv:2301.11403): a session fires when its average price
((O+H+L+C)/4) **and** its volume are both more than 2 standard deviations
above the previous 5 sessions. The paper's 5-day baseline is contaminated by
the pump itself, so once fired the flag **latches** for 10 sessions, or until
the price falls back near where it started.

**Verdict.** The core module (`layer1_verdict`) says BLOCK when both gates
fire, WARN when one does, PASS otherwise. The check people see
(`src/check_ticker.py`) turns that into:

- **VETO**: four or more structural red flags, or the pump profile (up 100%
  or more within 10 sessions), or a ghost quote (no real trading);
- **CAUTION**: no veto, but listed risks apply (high volatility, earnings
  soon, a position large for the account);
- **NO FLAGS**: none of the checks fired. That means "nothing found", not
  "safe".

**No hindsight:** every check takes an `as_of` date and reads only bars and
filings dated on or before it. Tests remove all later data and assert the
verdict doesn't change.

### How well it works (walk-forward, `specs/002`)

| Sample | Result |
|---|---|
| Event set: 2,431 US small caps swept, 349 run-ups that collapsed at least 70% within 20 sessions (positives), 2,492 that didn't (controls) | |
| Test: 295 clean positives, 400 random controls; Layer 1 replayed session by session from ramp start to peak, with filings as known at each date | Recall **0.783** (caught before the peak), but only 0.437 with two or more sessions' warning; false alarms **0.782** |
| One knob at a time, 17 runs | No setting meets the release gate; recall and false alarms move together |

**What that means:** Layer 1 recognises the *shape* of these stocks well, but
most small caps that run up have the same shape, whether or not they
collapse. That's why the site presents verdicts as a **checklist of red flags**
with the evidence, not as a prediction. The fix most likely to help is a
point-in-time float source (see the README's roadmap).

## Layer 2: the market scan (`server/scan.py`, `specs/004`)

Every trading day: every US stock closing between $1 and $30 that is up 50%
or more over 5 or 21 sessions is logged with its Layer 1 verdict **as of that
day**. The log is append-only (tested: rows are never updated or deleted).
Thirty sessions later each logged run is labelled *collapsed* (70% or more
drawdown from its peak) or not. Rows added by backfill are marked and kept
out of the forward metrics. Forward recall and false-alarm rates will be
published once six months of live rows exist.

## Layer 3: rules for someone already holding (`src/layer3.py`)

- **Time stop:** exit after two sessions; overnight gaps are what wipe people out.
- **Sell-only ladder:** a third at +25%, a third at +50%, the rest at the time stop.
- **Abandoned position:** a holding with no live exit order for 30 days.

Unit-tested; never connected to any account.

## Why we never say "ride the pump" (research)

Buying after a detected run-up with a +20% take-profit and −10% stop, on the
full universe: 61,129 trades, 30.1% winners against a 40% break-even, −2.9%
per trade, negative in every year tested. The research code that tested this
is not part of the public project.

## Limits

- Prices are end-of-day only; intraday pumps inside one session are invisible.
- Float and market cap are unknown for most small caps (counted as red flags).
- SEC filing indexes have gaps for some issuers.
- Survivorship: delisted symbols are under-represented in the event set.
- The site shows no exact prices, for data-licence reasons.

## Data

Daily prices from free tiers (Tiingo end-of-day; split-adjusted), SEC EDGAR
filing indexes (public records). Offline research tools can also read
payloads saved from a brokerage's read-only MCP server (such as Robinhood);
none of that data is published. No personal data. Test
fixtures are synthetic (`scripts/make_synthetic.py`).
