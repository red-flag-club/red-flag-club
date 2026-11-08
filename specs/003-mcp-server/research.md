# Research: pd-defence MCP Server

Each decision: what was chosen, why, what else was considered.

## R1. Free-tier daily bars

**Decision**: Tiingo free ("Starter") as the default; Massive (ex-Polygon) free
"Basic" as a configurable alternative; a `PayloadProvider` that imports saved
Brokerage `get_equity_historicals` payloads for offline seeding.

**Rationale**:
- `was_i_pumped` must reach back to 2024 (RYDE, Sep 2024, is already past two
  years). Tiingo's end-of-day history goes back decades; Massive's free tier
  stops at two years.
- Tiingo returns both raw and split-adjusted OHLCV plus `splitFactor`, so a
  reverse split inside a window can be detected and flagged.
- Published limits (third-party sources, verify on the pricing pages):
  Tiingo ≈ 50 requests/hour and 500 unique symbols/month on the free plan;
  Massive 5 requests/minute, 2 years, end-of-day, HTTP 429 when exceeded.
  One request returns a whole range, so a cached store keeps both comfortable
  for one user.

**Alternatives considered**: Alpha Vantage free (25 requests/day — too few);
Financial Modeling Prep free (250/day, short history); Stooq CSV (no key, but
unofficial and frequently blocked); Yahoo (unofficial, ToS risk).

**Adjusted vs raw prices**: verdicts use split-adjusted OHLCV so a 1-for-10
reverse split is not read as a +900% day. Back-adjustment scales a whole
series by the same factor, so returns (what the pump rule uses) are unchanged;
absolute price levels before a later split are not what traders saw. Every
response states `adjusted: true` and lists any split inside the window.

## R2. Synthesized and placeholder bars

Tiingo and Massive do not mark gap-fill bars the way the brokerage payload's `interpolated`
flag does. `clean_bars()` therefore drops only what provably carries no
information: bars with `interpolated == true` (brokerage payloads), bars with
any non-positive price (pre-listing placeholders such as RYDE 2024-02-29), and
duplicate dates (kept once, latest fetch wins). The survivor count is returned
(hard rule 5).

Flat zero-volume bars are **kept**: a flat last bar is the ghost-quote veto in
`check()`, and dropping such bars would silently remove a veto (hard rule 4).
One-bar spikes are flagged using the existing REED rule from
`src/event_sets.py` (`ISOLATED_SPIKE_RATIO` + below-median volume), never
dropped.

## R3. SEC filing index

**Decision**: `https://www.sec.gov/files/company_tickers.json` for ticker→CIK,
`https://data.sec.gov/submissions/CIK##########.json` for `form` and
`filingDate` (plus its `filings.files` pages for older history). User-Agent
`pd-defence <contact>` from `PD_SEC_CONTACT`; limit 5 requests/second (SEC
allows 10).

**Point-in-time caveat**: the ticker map is today's. A renamed or delisted
symbol may map to nothing or to a different issuer; then filing inputs are
unknown (scored worst-case), never a pass.

**Later**: SEC `companyfacts` carries `dei:EntityCommonStockSharesOutstanding`
with filing dates, a possible point-in-time shares source for L1.1. Out of
scope here; noted for a later spec.

## R4. Fundamentals and earnings

Free tiers give neither historically. The server accepts optional
`fundamentals` and `earnings` from the caller (the chat agent can read them
from a brokerage MCP server) and uses fundamentals **only when `as_of` is today**.
Otherwise float and market cap are unknown, and `check()` already scores
unknowns worst-case and raises the "could reach the veto" caution.

## R5. MCP transport and SDK

**Decision**: official Python SDK 2.x, `MCPServer` + `streamable_http_app()`,
`stateless_http=True`, `json_response=True` (no long-lived sessions to lose on a
redeploy; simplest behind a tunnel). The SDK's DNS-rebinding protection checks
the `Host` header; the public tunnel hostname goes in `PD_ALLOWED_HOSTS`.

## R6. Authentication behind cloudflared

**Decision**: one shared secret `PD_MCP_TOKEN` (≥ 32 random bytes), accepted as
`Authorization: Bearer <token>` (Claude Code, MCP Inspector, scripts) **or** as
a secret path prefix `/t/<token>/mcp` for clients that only take a URL. Compared
with `hmac.compare_digest`. `/healthz` is open and returns only `ok` + version.
The server refuses to start without a token unless bound to `127.0.0.1`.

**Trade-off of the path form**: the secret sits in the URL, so it can appear in
Cloudflare request logs and client config. Acceptable for a private,
single-owner, read-only service; rotate by changing the env var and redeploying.

**Alternatives**: OAuth 2.1 per the MCP auth spec — correct for a public
service, too much for one owner today (revisit when going public). Cloudflare
Access service tokens — good extra layer for Claude Code (custom headers), but
claude.ai connectors cannot send them; documented as optional.

## R7. Deployment

**Decision**: `docker compose` with one service, port published on
`127.0.0.1:8765` only (the tunnel runs on the same host), named volume
`pd-data`, `restart: unless-stopped`, health check on `/healthz`.

GitHub Actions:
- `ci.yml` — every push and PR, GitHub-hosted `ubuntu-latest`, `pytest -q`.
  Pull requests never touch the self-hosted runner.
- `deploy.yml` — `push` to `main` (and manual dispatch): test job on
  GitHub-hosted, then `deploy` on `runs-on: [self-hosted, pd-defence]`: tag the
  running image as `previous`, `docker compose up -d --build`, poll `/healthz`;
  on failure, restore `previous` and fail the job. Secrets come from repository
  secrets as environment variables; nothing is written into the checkout.

**Security note**: a self-hosted runner on a **public** repo can be made to run
untrusted code from fork PRs. The deploy job is restricted to `push` on `main`
and the repository owner; before the repo goes public, re-read this (GitHub's
guidance is to not attach self-hosted runners to public repos).
