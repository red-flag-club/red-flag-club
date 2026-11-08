# Research: Layer 2 Scan Log and Private Dashboard

## R1. Whole-market daily data on a free tier

**Decision**: Massive (ex-Polygon) grouped daily,
`/v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=true`, one call per
session for every US stock. Splits from `/v3/reference/splits?execution_date=`.

**Unverified**: third-party pricing guides confirm the free plan (5
calls/minute, end of day, ~2 years) but none confirm the grouped endpoint is on
it. The owner's first `./run.sh scan --check-source` call settles it: a 403
means the endpoint is not on the free plan.

**Fallback if not free**: `PD_SCAN_SOURCE=payload` builds sessions from
brokerage historicals payloads the owner's Claude routine saves (the 2,431-
symbol universe, read-only tools, 10 symbols/call). Slower to collect, but no
cost. A per-symbol free API (Tiingo, 500 symbols/month) cannot cover the
market and is not used for the scan.

**Why not Tiingo**: one request per symbol; 10k symbols a day is far beyond
its free limits.

## R2. The screen with free inputs

PLAN.md L2.1 filters: instrument STOCK, market cap < $100M, float < 20M,
relative volume > 5 (1d/30), 1-week change > 50%, close $1–$30. After the close
PLAN says to use the 1-month change instead of relative volume.

Free EOD data has close, volume and history, not market cap or float. So:

| L2.1 filter | Here |
|---|---|
| close $1–$30 | applied |
| 1w change > 50% | `ret_5 >= 0.50` (OR) |
| 1mo change > 50% (after-close variant) | `ret_21 >= 0.50` (OR) |
| relative volume > 5 | computed from own 30-session average, recorded, not required |
| market cap < $100M, float < 20M | not applied (unknown) — widens the screen |
| instrument STOCK | grouped daily is stocks; ETFs/warrants not excluded (noted) |

Run-ups are `close / min(close over the last N+1 sessions) - 1`, the same
measure `check()` uses for its pump rule.

## R3. Splits without lookahead

Grouped daily with `adjusted=true` adjusts only within that day's response, so
stored history mixes pre- and post-split prices. Back-adjusting with a split
announced later would be fine for returns but is easy to get wrong. Decision:
when a split executes on session S, every computation for a session ≥ S uses
only bars from S onward. A 1-for-10 reverse split therefore never reads as a
+900% run, and nothing after S's knowledge is used before S. Split dates come
from the splits endpoint when available; when it is unavailable, a one-session
close ratio ≥ 3 or ≤ 1/3 that persists for 3 sessions is flagged
`possible_split` (kept, not truncated — recall).

## R4. Outcomes and forward metrics

Label = L1.2 collapse definition via `find_runs` on closes from 10 sessions
before first logged to 30 after. Decided only when 30 sessions exist after
first logged; else `pending`. Forward metrics (non-backfilled rows only):
recall = collapsed episodes with a VETO logged on a session up to the peak;
FP rate = non-collapsing episodes with any VETO logged; both with N. (First-day
verdict alone would miss RYDE, logged CAUTION on 2024-09-05 and VETO on 09-06.) Shown as "too few to judge" below N=30.

## R5. Scheduling

Free EOD data appears after the close (exact time unverified for the free
tier), so the 17:30 ET run picks up the day; 10:00/12:30/15:00 runs catch up
any missed session, refresh SEC filings for the last 5 sessions' hits, re-label
outcomes and rebuild the page. Runs are idempotent; a lock prevents overlap.
Holidays: a session with no snapshot is skipped and retried next run (a
holiday stays empty; after 3 days it is marked `no_session`).

## R6. Dashboard

One static HTML file, inline CSS and SVG, light/dark via
`prefers-color-scheme`, no external requests. Served by the server at
`/dashboard/`, which the existing token gate protects; the bookmark is
`https://<host>/t/<token>/dashboard/`. The page carries no positions or
account data. Charts: hits per session (bars, last 60 sessions), per-hit
60-session close sparkline with the hit session marked, and a validation table
(not a chart: four numbers with N read better as a table).
