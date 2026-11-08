# Feature Specification: Red Flag Club organisation, public repos and private split

**Feature Branch**: `feature/community-org`

**Created**: 2026-11-08

**Status**: In progress. Owner decisions D1 (revised 2026-11-08), D2-D4 recorded

**Input**: Owner, 2026-11-08: "Create a GitHub org named red-flag-club and the
public repo to publish the GitHub Pages site, necessary tools, data and pages
based on my private repo, for the community. Move my private repo to that org
only. The objective is that this is for the community and by the community.
Detail all features supported and pending in the README. Do a detailed plan
first. Make sure public and private repo requirements are clear. Take decisions
appropriately. Ask questions if there is ambiguity."

## Goal

Anyone can read, use, check and improve the defence tools and the site. Nobody
can learn anything private about the owner, a story's author or anyone's
brokerage account from anything public. The laptop pipeline (data, scan,
stories decryption) keeps working throughout.

## What GitHub allows (constraints, verified against how GitHub works today)

| Step | Who can do it | Why |
|---|---|---|
| Create the `red-flag-club` organisation | **Owner, in the GitHub web UI** (Free plan) | GitHub has no API to create an organisation on github.com; Claude cannot do it |
| Transfer the owner's personal `pd-defence` repo into the org | **Owner** (Settings → Danger zone → Transfer; needs owner on both sides) | Not exposed to Claude's tools. Old URLs redirect; local clones keep working |
| Install the Claude GitHub App on the org | **Owner** | Needed before Claude can touch any org repo |
| Create the public repos, push their first commit, open PRs | Claude, once the app is installed on the org | |
| Repo secrets, deploy keys, Pages settings, runner registration | **Owner** (values never pass through Claude) | |
| GitHub Pages on a private repo | Not on the Free plan | Why the site repo must be public |
| Self-hosted runner on a public repo | **Never** | A fork's pull request could run code on the owner's laptop. GitHub's own guidance |

## Decisions

| # | Question | Decision | Why |
|---|---|---|---|
| 1 | How many repos | **Three public + two private** in the org (table below) | Code, built site and community content have different owners, churn and risks |
| 2 | Is the code open source | **Yes**: the defence path, server, site source, story tooling, Worker, specs and tests go public | "By the community" means people can read how a verdict is made, report a wrong one and fix it. A closed checker asks for trust; this project exists because misplaced trust cost money |
| 3 | Source of truth after the move | **The public code repo**. The private repo keeps only the owner's own material and the deployment, and builds the container from a pinned tag of the public repo | One copy of the code. Community pull requests land in one place and are never ported by hand |
| 4 | Git history | Public repos start from a **fresh first commit**. The private history is never pushed | The private history contains the owner's position, raw brokerage payloads and draft story commits; deleting files later does not remove them from history |
| 5 | Brokerage data | **Never public**: `raw/`, `data/events`, `data/l13`, `data/l14`, `data/universe`, `research/universe.json`, `results/`, and test fixtures cut from brokerage payloads | Brokerage data is licensed to the account holder, not for redistribution. It also carries the owner's activity |
| 6 | Price data on the site | **Off** (`PD_SITE_PRICES=off`), as today | Tiingo's free tier does not allow redistribution. Verdicts, flags and percentages only |
| 7 | Public test suite | Runs on **synthetic fixtures** only, on GitHub-hosted runners | Contributors need green tests without the owner's data |
| 8 | Ride Strategy research (`research/` riding code) | **Private**. Its findings go public as a summary ("riding a detected pump lost money: N=61,129, −2.9%/trade, every year negative") | A pump-riding backtester under an anti-scam brand is a buy-signal tool in the wrong hands. The finding protects people; the code doesn't |
| 9 | `research/check_ticker.py` | Moves into the public defence path (`src/check_ticker.py`) | The server's `check_ticker` tool needs it; it's defence code that happens to live in `research/` |
| 10 | Story pipeline | The Worker and checker are public. The **inbox stays private**, the **decryption key stays on the owner's machine**, and approval stays with the owner | Anyone can audit how stories are protected. Nobody but the owner can read a raw story |
| 11 | Licences | Code **MIT**. Docs, methodology and site text **CC BY 4.0**. Stories **CC BY-NC-ND 4.0** (shareable with credit, not editable or sold) | Stories are people's lives; they must not be rewritten or monetised by others |
| 12 | Community contributions | Issues, Discussions, pull requests to the public code repo. Story submissions only through the site. Templates for: wrong verdict, suspicious group or promoter (no personal data), bug, feature, translation | |
| 13 | Safety rules carried into public | Hard rules 1-5, "never a buy signal", "never call a stock a fraud", "no personal data", the story checker. They're restated in `CONTRIBUTING.md` and enforced by CI and review | |
| 14 | Org security | 2FA required. Base member permission: read. Members private by default. Fork PR workflows need approval. Actions on public repos limited to GitHub-hosted runners and pinned actions. Secret scanning and push protection on. Dependabot on | |
| 15 | Site URL | `https://red-flag-club.github.io/`, served from the repo `red-flag-club.github.io` | The organisation's root Pages address. A custom domain can be added later without breaking it |
| 16 | Repo names | The private repo is **`red-flag-club/pd-defender`** (owner renamed it on transfer, 2026-11-08). Internal names stay `pd-defence`: runner label, container and image, compose project, story-key path, MCP server name | Renaming those would break the laptop runner, the deployment and the stored key. None of them is public |

## Repositories

| Repo | Visibility | Holds | Written by |
|---|---|---|---|
| `red-flag-club/red-flag-club` | **Public** | Code: `src/`, `server/`, `web/`, `worker/`, `scripts/stories.py`, `scripts/monitor.py`, tests with synthetic fixtures, `specs/`, `docs/`, `.specify/`, public `CLAUDE.md`, the README with features and roadmap, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, licences, CI | Community via pull requests; maintainers merge |
| `red-flag-club/red-flag-club.github.io` | **Public** | Built site only: `index.html`, JS and CSS, `data/*.json` (no prices), approved `stories.json` | The private repo's `site.yml` bot only, via a deploy key. No human edits |
| `red-flag-club/stories` | **Public** | Approved, anonymised stories as JSON/Markdown, with their licence | Owner (`stories.py approve` → export) |
| `red-flag-club/.github` | **Public** | Org-wide defaults every repo inherits: issue forms (each asks what / why / how), PR template with the hard-rules checklist, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, SUPPORT, the org profile, the reusable `spec-gate` workflow and the `project-sync` board job | Maintainers via PRs |
| `red-flag-club/pd-defender` | **Private** (transferred and renamed) | Owner-only material: `PLAN.md` with the position, `PROGRESS.md`, `raw/`, `data/`, `results/`, `reports/`, `research_notes/`, Ride Strategy code, `docs/daily_monitor_routine.md`, `.mcp.json`, approval records. Plus the **deployment**: `deploy.yml`, `site.yml` on the self-hosted runner, building from a pinned public tag | Owner and Claude |
| `red-flag-club/stories-inbox` | **Private** | Encrypted story submissions only (ciphertext) | The Worker's fine-grained token |

## Requirements

- **FR-001** (narrowed by D1 revised) No public repo contains the owner's trading records: exact loss, position, cost basis, buy dates, orders. Originally: nothing in any public repo identifies the owner beyond what the owner chooses in D1. This covers the loss amount, position size, cost basis, account numbers, monitor output, chat details, commit author emails and names in LICENSE.
- **FR-002** A **leak gate** (`scripts/public_export.py check`) fails on: any file outside the allowlist; brokerage payload shapes (`"begins_at"`, `"interpolated"`, `account_number` values); email addresses other than `noreply`; files over 1 MB; plus owner-specific patterns (name, username, exact loss, position, cost basis) read from `scripts/leak_patterns.private`. That file is private and never exported, because publishing the patterns would publish what they protect. It runs in the private repo's CI before every export, and in the public repo's CI on every pull request.
- **FR-003** The public test suite passes on a clean checkout on `ubuntu-latest` with no secrets and no network.
- **FR-004** RYDE and DJT stay regression tests in public, rebuilt from **public facts** (SEC filing dates, the 3.0M float as of September 2024, a synthetic price path with the same shape). The owner's actual position is not used.
- **FR-005** No self-hosted runner, deploy key with write access, or production secret is attached to a public repo. Public repos hold no secrets.
- **FR-006** The private deployment builds from a **tagged** public release, so an unreviewed public commit never reaches the laptop.
- **FR-007** The site keeps working throughout the move: the old `PD_SITE_REPO` keeps publishing until the new site repo is live.
- **FR-008** The README lists every supported feature with its validation status and sample size, and every pending item, honestly. Layer 1 says "gate not met; use it as a checklist" (recall 0.783, FP 0.782, N=295/400).
- **FR-009** Story content in public is only what `stories.py approve` produced. The public repos never contain inbox files, drafts or the decryption key.
- **FR-010** Every public page and the README carry: not financial advice; never a buy signal; we do not call any stock a fraud; how to report to the SEC and IC3; how to ask for a correction or takedown.

## Spec-driven, issue-tracked, human-gated (owner, 2026-11-08)

Input: "Ensure spec-kit based spec driven development using GitHub issues and
projects are added to all repos of the new org. Human agent (me as admin)
will review and move the task from one phase to another where human review is
a must. As the public community will access the public repo, ensure the value
add in what, why and how is clearly mentioned."

- **FR-011** Every repo in the org (public and private) uses the same issue
  forms, PR template and labels, inherited from `red-flag-club/.github`. Each
  issue form asks **what**, **why** and **how**.
- **FR-012** One organisation project, "Red Flag Club: spec pipeline", with a
  **Phase** field: Inbox → Specify → Plan → Tasks → Implement → Review → Done
  (+ Won't do, Blocked). Items from every repo are auto-added.
- **FR-013** Only maintainers (admins) can move items between phases. Every
  forward move except Implement → Review is a **human review gate**
  (`docs/workflow.md` lists what each gate checks).
- **FR-014** `spec-gate` (reusable workflow) blocks a PR unless it links an
  issue in an allowed phase (docs and specs: Specify, Plan or Tasks; code:
  Implement or Review) and every hard-rule box is ticked. Phases reach
  issues as `phase:*` labels written by `project-sync` from the board, because
  fork PRs can't read the board and labels need triage access to set.
- **FR-015** `tasks.md` items become sub-issues of the spec issue
  (`scripts/spec_issues.py`) when the Tasks gate is passed.
- **FR-016** Every public README (org profile, code, stories, site) states
  what the project or repo does, why it matters and how it works; the code
  README lists every built feature and every pending one with what / why /
  how (tested in `tests/test_governance.py`).
- **FR-017** (superseded by D1 revised) The owner's personal account is the
  maintainer. Label syncing and site/stories publishing still run as a bot.

## Owner decisions (2026-11-08)

| # | Decision | Consequences |
|---|---|---|
| D1 (superseded) | **Anonymous organisation** | Copyright "Red Flag Club contributors". Org membership private. Public commits authored `Red Flag Club <noreply>`. The loss amount, position, cost basis and the owner's name are scrubbed from every public file (FR-001 and the leak gate). **The owner's own GitHub account must not author public commits, issues, PRs or Discussions posts.** Its username would link the founder to the org. Use a separate maintainer account (e.g. `red-flag-club-maintainer`), or have Claude and the bot push |
| D1 (revised 2026-11-08) | **Public founder.** The owner's personal account (`ashutosrath`) is the org owner and the maintainer: it creates the public repos, owns CODEOWNERS and moves board items. Asked in a choice that spelled out the consequence (permanent public link to the org and, effectively, to the owner's story); the owner chose "my personal account, go public" | The name and username may appear publicly. Still private: the exact loss, position size, cost basis, buy dates and orders, the brokerage payloads and the chat records (leak gate unchanged for those). Copyright stays "Red Flag Club contributors". FR-001 and FR-017 are narrowed accordingly |
| D2 | **Owner is the only approver** for now | One decryption key, as today. Moderators go on the roadmap |
| D3 | **Separate public `red-flag-club/stories` repo** | `site.yml` pushes approved stories there too. Issue templates for corrections and takedowns |
| D4 | **Event labels stay private** | Public gets summary metrics with sample sizes only |
