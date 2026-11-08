# pd-defence MCP server — runbook

Spec: `specs/003-mcp-server/`. The server is **read-only**: it has no brokerage
connection, cannot place orders, and stores no account numbers, positions or
orders. Your own holdings still come from a brokerage MCP server; you (or the chat
agent) pass them to `monitor_digest` when you want the daily rules run.

```
chat agent ──HTTPS──> Cloudflare ──tunnel──> cloudflared (laptop) ──> 127.0.0.1:8765
                                                                       pd-defence-mcp container
                                                                       ├─ Tiingo (daily bars, free tier)
                                                                       ├─ SEC EDGAR (filing index)
                                                                       └─ /data/pd.duckdb (volume)
```

## Tools

| Tool | Ask it | Returns |
|---|---|---|
| `check_ticker` | "check XYZ before I buy" | VETO / CAUTION / NO FLAGS, reasons, run-up, structural score with unknowns, dollars at risk |
| `was_i_pumped` | "I bought XYZ on 2025-03-03 — was it a pump?" | the verdict using only data known that day, then labelled hindsight (5/20/60-session returns, worst drawdown) |
| `pump_scan` | "scan these 30 tickers" | table, VETO first, by 10-session run-up |
| `monitor_digest` | "run my daily rules" (agent passes positions + orders) | EXIT RULE, TIME STOP, EARNINGS, ABANDONED, LOSS, VETO alerts |
| `is_pumping` | "is XYZ on the pump scan?" | on the scan today, days on scan in the last 20 sessions, first/last seen, plus the check |
| `scan_latest` | "what's pumping today?" | the latest scan's hits, VETO first, and the forward check of Layer 1 |
| `data_status` | "how much quota is left?" | provider, calls this hour, unique symbols this month, cache size |

None of them is a buy signal. Layer 1's walk-forward gate is not met (recall
0.783, FP 0.782, N=295/400), so every verdict is a checklist aid.

**Why it saves tokens.** Today a check pulls ~14 months of bars through the
brokerage MCP into the chat (tens of thousands of characters, often spilled to
a file and re-parsed). The server keeps the bars and answers in under 2,500
characters (tested), and repeat questions are served from its cache.

## 1. One-time setup

1. **Tiingo key** — create a free account at tiingo.com, copy the API token.
   Free tier is about 50 requests/hour and 500 unique symbols/month (check
   their pricing page; the server caches so one symbol costs one request a day).
2. **SEC contact** — any e-mail you read. SEC requires it in the User-Agent.
3. **Server token** — `openssl rand -hex 32`. Keep it in a password manager.
4. `cp .env.example .env` and fill in `PD_MCP_TOKEN`, `TIINGO_API_KEY`,
   `PD_SEC_CONTACT`, `PD_ALLOWED_HOSTS`. `.env` is git-ignored.

Offline demo with no keys: `./run.sh serve --fixture` (RYDE and RETO from
the repo's event data, on 127.0.0.1 only).

## 2. Run it on the laptop

```bash
docker compose up -d --build        # or ./run.sh docker-up
curl -s localhost:8765/healthz      # {"status":"ok","version":"0.1.0"}
docker compose logs -f              # tool name, symbol count, outcome, ms — nothing else
```

The port is bound to `127.0.0.1` only; cloudflared on the same machine is the
way in. The DuckDB cache lives in the `pd-defence_pd-data` volume and survives
restarts and redeploys. The container runs as a non-root user on a read-only
filesystem.

## 3. Route a hostname through your existing tunnel

Locally-managed tunnel (`~/.cloudflared/config.yml`): add an ingress rule
**above** the catch-all, then route DNS and restart cloudflared.

```yaml
ingress:
  - hostname: pd.example.com
    service: http://localhost:8765
  # ...your existing rules...
  - service: http_status:404
```

```bash
cloudflared tunnel route dns <your-tunnel-name> pd.example.com
sudo systemctl restart cloudflared     # macOS: sudo launchctl kickstart -k system/com.cloudflare.cloudflared
```

Dashboard-managed tunnel: Zero Trust → Networks → Tunnels → your tunnel →
Public Hostname → add `pd.example.com` → `HTTP` → `localhost:8765`.

Set `PD_ALLOWED_HOSTS=pd.example.com` — the server rejects other `Host`
headers (DNS-rebinding protection).

## 4. Connect your agents

**Claude Code** (sends headers):

```bash
claude mcp add --transport http pd-defence https://pd.example.com/mcp \
  --header "Authorization: Bearer $PD_MCP_TOKEN"
```

**claude.ai** (custom connector takes a URL): Settings → Connectors → Add
custom connector → `https://pd.example.com/t/<PD_MCP_TOKEN>/mcp`, no OAuth.
The secret is in the URL, so it can appear in Cloudflare request logs and in
the connector settings; rotate it if either is exposed. claude.ai reaches the
server from Anthropic's cloud, so the tunnel hostname must be public (it is).

**Optional extra layer for Claude Code only:** a Cloudflare Access application
on `pd.example.com` with a service token, and two more `--header` flags
(`CF-Access-Client-Id`, `CF-Access-Client-Secret`). claude.ai connectors can't
send those headers, so don't enable Access if you use claude.ai.

## 5. Deploy on merge (self-hosted runner)

1. GitHub → repo → Settings → Actions → Runners → **New self-hosted runner**;
   pick your laptop's OS and run the commands it shows. When asked for labels,
   add `pd-defence`. Install it as a service (`./svc.sh install && ./svc.sh start`
   on macOS/Linux) so it survives reboots.
2. The runner's user must be able to run `docker` (Linux: in the `docker`
   group; macOS: Docker Desktop running).
3. Settings → Secrets and variables → Actions → add secrets `PD_MCP_TOKEN`,
   `TIINGO_API_KEY`, `PD_SEC_CONTACT`, `PD_ALLOWED_HOSTS` (and
   `MASSIVE_API_KEY` if you switch provider). Optional variable `PD_PROVIDER`.

Then every push to `main`:

- `ci.yml` (GitHub-hosted): full test suite + image build + fixture smoke test.
  Runs on every push and PR; PRs never touch your laptop.
- `deploy.yml`: tests again on GitHub-hosted, then on your laptop tags the
  running image `previous`, `docker compose up -d --build`, waits for healthy
  (90 s), and rolls back to `previous` if it doesn't come up.

Manual redeploy: Actions → deploy → Run workflow.

**Before the repo goes public:** a self-hosted runner attached to a public repo
can be made to run code from a fork. `deploy.yml` only runs on `push` to
`main` by the owner, but GitHub's advice is still not to attach self-hosted
runners to public repos. Revisit this (e.g. move deploy to a pull-based
watcher on the laptop) as part of the going-public spec.

## 6. Layer 2 scan and the private dashboard (spec 004)

Every market day the server screens the **whole US market** for small caps
up ≥ 50% over 5 or 21 sessions (close $1–$30), logs each hit with that day's
Layer 1 verdict in an append-only table, and — 30 sessions later — labels
whether it collapsed (≥ 100% up then ≥ 70% down, PLAN.md L1.2). That log is
the forward test Layer 1 has never had.

1. **Get a free Massive key** (massive.com, formerly polygon.io) and check
   that the whole-market endpoint is on the free plan:

   ```bash
   MASSIVE_API_KEY=... PD_SCAN_SOURCE=massive ./run.sh scan --check-source
   ```

   `ok: 11,000 symbols for <date>` → continue. `not usable … 403` → the
   endpoint is not on the free plan; use `PD_SCAN_SOURCE=payload` with the
   brokerage payload files your Claude routine saves (slower to collect).
2. In `.env` (or repo variables for the deploy workflow): `MASSIVE_API_KEY`,
   `PD_SCAN_SOURCE=massive`, `PD_SCHEDULE=on`. Redeploy.
3. The first refresh backfills 60 sessions: 60 calls at 5/minute, about
   **12 minutes**. It is resumable. Rows logged during backfill are marked and
   kept out of the forward metrics.
4. Refreshes run weekdays at 10:00, 12:30, 15:00 and 17:30 ET
   (`PD_SCAN_TIMES`). Free data is end-of-day, so prices change once (the
   17:30 run); the others catch up missed sessions, pick up new SEC filings
   for recent hits and rebuild the page.
5. Bookmark `https://pd.example.com/t/<PD_MCP_TOKEN>/dashboard/`. The page is
   self-contained (no scripts, no external requests), light/dark, and holds
   no account data. Without the token it returns 401.

By hand: `./run.sh scan`, `./run.sh dashboard`. Offline demo:
`./run.sh scan --fixture` then `./run.sh serve --fixture` and open
`http://127.0.0.1:8765/dashboard/`.

**What is kept on disk (spec 005).** Only what today's questions need, plus
the record that cannot be rebuilt:

| Data | Kept |
|---|---|
| Whole-market daily bars | the last 70 sessions (rolling) |
| Bars for symbols you ask about | ~16 months, dropped after 30 days without a lookup |
| Older history (e.g. "was I pumped on RYDE in 2024?") | fetched for the answer, held in memory only, never written |
| Scan log, outcomes, check log, SEC filing index | permanently (small) |

The database is compacted weekly. A simulated year of 10,000 symbols leaves a
~28 MB file. `data_status` and the dashboard footer show the current size.

**What the screen cannot do on free data:** float and market cap are unknown,
so the PLAN.md L2.1 filters for them are not applied — the list is wider than
the plan's (more false positives, never fewer true ones). Back up
`/data/pd.duckdb` occasionally (`docker cp pd-defence-mcp:/data/pd.duckdb .`):
the scan log cannot be rebuilt for days that were never logged.

## 7. Rotate the token

Generate a new one, update the repo secret and `.env`, run the deploy workflow
(or `docker compose up -d`), then update the Claude Code header and the
claude.ai connector URL.

## 8. Limits and caveats

- **Free data.** Daily bars only, split-adjusted (a reverse split is not read
  as a pump; levels before a later split are scaled). Tiingo's limits are on
  its pricing page; `data_status` shows your usage. When the limit is hit, a
  cached symbol is still answered; an uncached one gets "data unavailable, try
  later", never a verdict on partial data.
- **Float and market cap are unknown** for any past date (no free
  point-in-time source). They are scored as red flags in the worst case.
  For today's date you can pass `fundamentals` from a brokerage MCP server.
- **SEC ticker map is today's.** Renamed or delisted symbols may not resolve;
  then filing inputs are unknown (worst case), never a pass.
- **Laptop off = service off.**
