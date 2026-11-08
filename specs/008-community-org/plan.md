# Implementation Plan: Red Flag Club organisation (spec 008)

**Spec**: `specs/008-community-org/spec.md` · **Branch**: `feature/community-org`

## Constitution check

| Rule | How this plan keeps it |
|---|---|
| 1 No order-placing tools | Nothing here touches the brokerage. The public code has no brokerage client at all (server data comes from Tiingo, Massive and SEC) |
| 2 No lookahead | Public tests keep the `as_of` tests and run them on synthetic fixtures |
| 3 No live values in historical tests | RYDE's public fixture uses the 3.0M float as of September 2024, written as a dated fact |
| 4 Bias to false positives | No threshold changes. Public contributors are told precision may never be bought with recall without saying so (CONTRIBUTING) |
| 5 `interpolated` | Synthetic fixtures include gap-fill bars so the filter stays tested |
| Defence path never trades | Ride Strategy code stays private (spec D8) |
| Stories | Approval stays with the owner; inbox and key never public |

## File classification (the allowlist)

Every tracked file falls in exactly one row. The export script holds this
table as data; a file in no row fails the gate.

| Path | Public code repo | Private | Notes |
|---|---|---|---|
| `src/*.py` | ✅ | | + `src/check_ticker.py` moved from `research/` |
| `server/*` | ✅ | | Drop the `research/` and `scripts/` sys.path hacks once `check_ticker` moves |
| `web/*` | ✅ | | Source of the site |
| `worker/stories/*` | ✅ | | `wrangler.toml` stays git-ignored |
| `scripts/stories.py`, `scripts/monitor.py`, `scripts/score_checks.py` | ✅ | | Tools. `monitor.py` reads positions you pass in and stores nothing |
| `scripts/l13.py`, `scripts/l14.py` | ✅ | | Harness code without the data. Docs say "bring your own bars" |
| `tests/*` | ✅ rewritten | original | Fixtures replaced with synthetic ones (task T12) |
| `specs/001-008`, `.specify/` | ✅ scrubbed | original | Methodology is the most useful thing to reviewers |
| `docs/mcp_server.md`, `docs/site.md`, `docs/stories.md` | ✅ scrubbed | | Owner-specific hostnames and usernames become placeholders |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `run.sh`, `conftest.py` | ✅ | | |
| `.claude/skills/story-anonymise`, `speckit-*` | ✅ | | Lets contributors use Claude Code with the same rules |
| `CLAUDE.md` | ✅ public version | ✅ private version | Public drops the owner's loss and position (per D1) and the brokerage data notes |
| `PLAN.md` | `METHODOLOGY.md` (scrubbed extract) | ✅ | The private copy keeps the position table |
| `research/FINDINGS.md` | ✅ summary only | ✅ full | |
| `research/*.py` (riding, bracket, candles, paper agent) | | ✅ | Spec D8 |
| `raw/`, `data/`, `results/`, `research/universe.json` | | ✅ | Spec D5 |
| `reports/`, `research_notes/`, `RECONCILE_AND_BUILD_PROMPT.md`, `PROGRESS.md`, `docs/daily_monitor_routine.md`, `.mcp.json` | | ✅ | Personal research and routines |
| `community/stories/approved/*` | ✅ via export (D3 decides which repo) | ✅ | Only what `approve` produced |
| `community/stories/*.draft.json`, `community/inbox/` | | ✅ | Drafts are never public, even anonymised ones |
| `.github/workflows/ci.yml` | ✅ rewritten | ✅ | Public CI: tests, leak gate, Node tests; GitHub-hosted only; no secrets |
| `.github/workflows/deploy.yml`, `site.yml` | | ✅ | Self-hosted runner. The owner guard changes from the owner's personal account to `red-flag-club` |
| `LICENSE` | ✅ MIT + `LICENSE-content` (CC BY 4.0) + `LICENSE-stories` (CC BY-NC-ND 4.0), copyright "Red Flag Club contributors" | ✅ | D1 |

## Phases and owners

### Phase 0: Decisions (done 2026-11-08)
D1 anonymous org, D2 owner-only approval, D3 separate stories repo, D4 event labels private.
Because of D1: create a separate GitHub account for public maintainer work, or let Claude and the bot do every public write.

### Phase 1: Organisation (owner, about 15 minutes, web UI)
1. github.com → + → New organization → **Free** → name `red-flag-club`. If the name is taken: `redflagclub`, then `red-flag-club-org`. Tell Claude which one.
2. Settings → Authentication security → **Require 2FA**.
3. Member privileges: base permission **Read**. Turn off repository creation by members for now.
4. Actions → General: **Require approval for all outside collaborators'** fork workflows. Allow GitHub's and verified actions only.
5. Code security: secret scanning + push protection, Dependabot alerts, on for new repos.
6. Install the **Claude GitHub App** on the org: all repositories, or the five listed in the spec.
7. Optional: profile README, avatar (`web/icon.svg`), and a "Red Flag Club" display name.

### Phase 2: Move the private repo (owner, about 10 minutes)
1. the owner's personal `pd-defence` repo → Settings → Transfer → `red-flag-club`. Keep it **private**.
2. Check after the transfer: Actions secrets and variables, deploy keys, the self-hosted runner (repo → Settings → Actions → Runners). Re-register the runner if it's missing. `git remote set-url origin git@github.com:red-flag-club/pd-defence.git` on the laptop.
3. Transfer `pd-defence-stories-inbox` the same way, or create `red-flag-club/stories-inbox` new. Reissue the Worker's fine-grained token with **resource owner = red-flag-club** (tokens don't follow a transfer), then `npx wrangler secret put GITHUB_TOKEN` and update `INBOX_REPO`.
4. Start a new Claude Code session on `red-flag-club/pd-defender` (renamed on transfer). This session's GitHub scope is the old name.

### Phase 3: Make the code publishable (Claude, in the private repo, one PR)
- **T1** Move `research/check_ticker.py` to `src/check_ticker.py`; keep a re-export shim in `research/` so the private research code still runs; simplify `server/__init__.py`.
- **T2** `scripts/public_export.py`: allowlist (table above), scrub rules for `CLAUDE.md`, docs and specs, and `check` (leak gate FR-002), `build --out DIR` (writes the public tree) and `diff` (what changed since the last export).
- **T3** Leak-gate tests: a fixture containing each forbidden pattern must fail; the real export must pass.
- **T4** Synthetic fixtures: RYDE-shaped and DJT-shaped price paths with real public SEC filing dates and gap-fill bars; port every test that reads `data/`, `raw/` or `tests/fixtures/l13`. The full suite must pass with those paths deleted.
- **T5** Public `CLAUDE.md`, `METHODOLOGY.md` and `FINDINGS-summary.md`.
- **T6** README (outline below), CONTRIBUTING, CODE_OF_CONDUCT (Contributor Covenant 2.1), SECURITY (private vulnerability reporting), SUPPORT (victim resources), licences.
- **T7** `.github/` for public: `ci.yml` (Python 3.11/3.12, Node 20, leak gate), issue templates (wrong verdict, suspicious group, bug, feature, translation, story correction or takedown), PR template with the hard-rule checklist, `CODEOWNERS`, `dependabot.yml`.
- **T8** Workflow guards from the owner's personal account to `red-flag-club`; `PD_SITE_REPO` → `red-flag-club/red-flag-club.github.io`.

### Phase 4: Create the public repos (Claude creates them, owner sets keys)
1. Claude creates `red-flag-club/red-flag-club` (public), builds the tree with `public_export.py build`, runs the gate and the tests on it, and pushes **one fresh commit** authored as `Red Flag Club <noreply>`. Tag `v0.1.0`.
2. Claude creates `red-flag-club/red-flag-club.github.io` (public) with a placeholder `index.html` and a README saying "built by a bot, do not edit; source in red-flag-club/red-flag-club".
3. Owner: Pages for the site repo (deploy from `main`, root). New deploy key with write access on the site repo; private key → `SITE_DEPLOY_KEY` in `pd-defence`; set `PD_SITE_REPO`; set `PD_SITE_URL=https://red-flag-club.github.io` and `PD_SITE_DISCUSSIONS`.
4. Owner: run `site.yml` once (workflow_dispatch) and open the site. Then retire the old site repo (archive it, with a README pointing to the new URL).
5. Owner: turn on Discussions in the code repo (categories: Q&A, "Is this a red flag?", Ideas, Show and tell), and branch protection on `main` (PR + 1 review + CI green; maintainers only).
6. D3: Claude creates `red-flag-club/stories`; `site.yml` also pushes approved stories there.

### Phase 5: Cut over the source of truth (Claude, private repo PR)
- `deploy.yml` checks out `red-flag-club/red-flag-club` at the tag in `PUBLIC_REF` (a file in the private repo) and builds the image from it; private-only files stay out of the image.
- Delete the now-public code from the private repo (in a normal commit; it's still in private history, which is fine).
- From here: code changes → public PRs → tag → bump `PUBLIC_REF` in private → deploy. Story approvals and data stay private.

### Phase 6: Open to the community (owner + Claude)
- Seed "good first issue"s from the pending list in the README (translations, quiz questions, assistant intents, accessibility).
- Pin a Discussions post: how to report a group without posting anyone's personal data.
- Launch post for Facebook and YouTube with the site URL.

## README outline (public code repo)

1. **Red Flag Club**: one paragraph: what it is, for whom, the tagline. Site link. "Not financial advice. We never say buy. We never call a stock a fraud."
2. **If you've just lost money**: SEC tips (sec.gov/tcr), FBI IC3 (ic3.gov), FINRA helpline, "recovery" scams warning, share your story.
3. **Features supported** (each with status and sample size):
   - Site: Today, Top 100 run-ups (day/week/month) with verdicts and flags, Risk scan, Look up `#/t/SYM`, Analytics, Track record (forward vs backfill), Stories (browse by tag and stock, victims per stock), Share yours (voice or text, encrypted), Quiz, offline Assistant, Got pumped?, About.
   - Defence path: Layer 1 pre-trade check (structural FINRA fingerprint + 2-sigma anomaly with latch; **gate not met**, recall 0.783 / FP 0.782, N=295/400, so it's a checklist); Layer 2 market scan with an append-only log and 30-session outcome labels; Layer 3 rules (time stop, sell-only ladder, abandoned check).
   - MCP server: the 7 tools, read-only, token-gated, Docker, free data tiers, retention policy.
   - Stories: encryption, checker, approval, licence.
   - Research findings: riding pumps loses (N=61,129).
4. **Pending / roadmap**, with how to help: L1.4/L1.5 gate (precision without losing recall), L1.6, L2.4 (needs six months of forward rows, about May 2027), L3.3, float data for small caps, prices on the site (licence), Massive grouped-daily check, "hero" features (prebunking alert before a group's "rocket plan", red-flag checker for a pasted group message, recovery-scam detector, report-letter helper for SEC and IC3, multilingual site and stories, browser extension), moderation for more than one approver, custom domain, trademark.
5. **How it works**: architecture diagram (laptop container → site repo → Pages; Worker → inbox → owner → approved stories).
6. **Run it yourself**: tests, site locally, the server with Tiingo's free key.
7. **Contributing**: rules, what we won't merge (buy signals, accusations, personal data, weakened recall).
8. **Licences and credits**.

## Risks

| Risk | Mitigation |
|---|---|
| Private data leaks into a public repo | Fresh history; allowlist, not a denylist; leak gate in both CIs; secret scanning and push protection; a human reads the first export |
| A malicious PR to the public repo reaches the laptop | No self-hosted runner on public repos; deploy only from tags the owner cuts |
| A story's author is identified | Owner-only approval; checker; D1 handled before the RYDE story is linked to any name |
| A company disputes a verdict | Correction/takedown template; the "allegation", "never fraud" wording rules; verdicts explained with their inputs |
| The org name is taken | Fallback names in Phase 1 |
| The transfer breaks the runner or secrets | Phase 2 checklist; the site keeps its old repo until the new one is live |
