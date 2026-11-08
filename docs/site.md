# Red Flag Club (community site) — setup and guide

Spec: `specs/006-community-site/`. A static, menu-based site built from the
laptop server's data after every scan refresh and published to GitHub Pages
from a **separate public repository**. This code repository stays private.

## What's on it

| Menu | For | What it shows |
|---|---|---|
| Today | everyone | counts, this week's 10 biggest run-ups, entry points |
| Top 100 | everyone | penny stocks (close < $5, ≥ $25k traded/day) with the biggest run-ups today, this week (5 sessions), this month (21) — each with its Layer 1 verdict, red flags and a shape line |
| Risk scan | everyone | the Layer 2 log: $1–$30 stocks up ≥ 50% over 5 or 21 sessions, last 20 sessions |
| Look up (`#/t/XYZ`) | someone being pitched | one stock: verdict, red flags, changes, history, past outcomes, a link to paste into the group |
| Analytics | moderators, researchers | filter every small cap by band, change, volume, verdict, scan days; CSV download |
| Track record | everyone | how logged stocks ended (collapse or not), recall and false alarms with N |
| Assistant | everyone | a chat box answering from the site's data and help text (offline, no API key) |
| Got pumped? | victims | don't pay "recovery" firms; report free (SEC, FINRA, FBI IC3); taxes; share safely; red flags |
| Stories | everyone | real, anonymised stories; filter by tactic, stock, channel; "read next" |
| Share yours | victims | speak or type a story; see `docs/stories.md` |
| Quiz | everyone | 10 "spot the red flag" situations with explanations |
| About | everyone | method, limits, data format for bots, privacy |

### Guard rails built in

- Every list is a **risk list**: a fixed banner shows what buying after such
  runs did in this project's backtest (61,129 trades, 30.1% wins vs 40%
  breakeven, −2.9%/trade).
- Wording is about **risk patterns**: no page says a company is a fraud.
- Exact prices are **off** (data licences); percentages, price bands and shapes
  indexed to 100 are shown. Turn on with `PD_SITE_PRICES=on` only after checking
  your provider's terms allow republishing.
- No cookies, trackers, external scripts or fonts. The assistant runs in the
  browser.

## Owner setup (once)

1. **Create the public site repo**, e.g. `pd-defence-site` (public, with a
   README). Settings → Pages → Deploy from branch → `main` / root.
2. **Deploy key**: `ssh-keygen -t ed25519 -N "" -f site_key`. In the *site* repo:
   Settings → Deploy keys → add `site_key.pub` with **write access**. In *this*
   repo: Settings → Secrets → Actions → `SITE_DEPLOY_KEY` = contents of
   `site_key`. Delete both files afterwards.
3. In *this* repo: Settings → Variables → Actions → `PD_SITE_REPO` =
   `<you>/pd-defence-site`. Optional: `PD_SITE_DISCUSSIONS` =
   `https://github.com/<you>/pd-defence-site/discussions` (enable Discussions
   on the site repo, add a "Stories" category, pin the posting guidance below).
4. Make sure the server runs the scan (`PD_SCAN_SOURCE`, `PD_SCHEDULE=on`, see
   `docs/mcp_server.md` §6). Every refresh rebuilds `/data/site`.
5. Actions → **site** → Run workflow once. The site appears at
   `https://<you>.github.io/pd-defence-site/` and then updates four times a
   market day (laptop on).

Preview locally: `./run.sh site --fixture && ./run.sh site-preview`, then open
http://127.0.0.1:8000/.

### Posting guidance for the Stories category (pin it)

> Share what happened so others can spot it sooner: how you were contacted,
> the group's name and tactics, the ticker and dates. **Never post account
> numbers, order screenshots with personal details, phone numbers of real
> people, or anyone's private information.** Describe patterns; don't accuse
> named individuals. If someone replies offering to recover your money, it is
> almost certainly a second scam — report it.

## For community bots

Static JSON and CSV under `data/` (schema: `specs/006-community-site/contracts/site-data.md`):
`meta.json`, `movers.json` (+ `movers_{day,week,month}.csv`), `symbols.json`
(+ `symbols.csv`), `scan.json`, `outcomes.json`. Percentages are fractions.

## A smarter assistant later

The built-in assistant is deterministic: free, private and unable to invent a
verdict. An LLM-backed assistant (answering free-form questions by calling
this project's tools) is possible later through the laptop server, but a
public endpoint has unbounded cost and abuse risk; it needs a per-visitor
rate limit and a hard daily spend cap first. Until then, the owner's own
Claude can already use every tool through the MCP connector
(`docs/mcp_server.md` §4).
