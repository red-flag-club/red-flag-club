# How work moves: spec-driven, issue-tracked, human-gated

Every change to Red Flag Club, in every repository of the organisation, follows
the same path: **an issue, a spec, a plan, tasks, code, review**. We use
[GitHub Spec Kit](https://github.com/github/spec-kit) for the documents, GitHub
Issues for the conversation, and one organisation-wide GitHub Project for the
board. A maintainer (a human) moves each item through the review gates. No bot,
model or contributor can skip one.

## Why we work this way

- **What:** the documents state what a change does and how we'll know it
  works, before anyone writes code.
- **Why:** this project tells people *not* to trade. One careless change, such
  as a weaker threshold, a leaked personal detail, or a page that reads like a
  buy signal, can cost someone their savings or expose a victim. Writing the
  spec first catches those mistakes while they're cheap to fix.
- **How:** the gates below, the board and a CI check (`spec-gate`) that blocks
  code pull requests whose issue hasn't been approved for implementation.

## The board: "Red Flag Club: spec pipeline"

One project for the whole organisation, with items from every repo. Its
**Phase** field is the pipeline:

| Phase | What happens | Produced | Who moves it on | Gate (human review required) |
|---|---|---|---|---|
| **Inbox** | Someone opens an issue (idea, bug, wrong verdict, red-flag report, translation, story correction) | The issue | Maintainer | **Triage**: in scope, not a duplicate, no personal data in the issue → *Specify*, or close with a reason |
| **Specify** | Write `specs/NNN-name/spec.md` with `/speckit.specify` (or by hand from `.specify/templates/spec-template.md`): user stories, requirements, success criteria | Spec PR | Maintainer | **Spec review**: solves a real problem for victims or at-risk investors; no buy signal; no accusation; measurable success criteria; open questions answered (`/speckit.clarify`) → *Plan* |
| **Plan** | `/speckit.plan`: design, data, contracts, **constitution check** against the hard rules | `plan.md` (+ research, data model, contracts) | Maintainer | **Plan review**: every hard rule addressed; no lookahead; no new personal data; free-tier cost → *Tasks* |
| **Tasks** | `/speckit.tasks` then `/speckit.analyze`; tasks become sub-issues (`scripts/spec_issues.py`) | `tasks.md`, sub-issues | Maintainer | **Task review**: small, testable, ordered; tests named for every rule → *Implement* |
| **Implement** | `/speckit.implement` or by hand. A PR per task or small group. The PR says `Closes #N` | Code PRs | Automatic when a PR opens | `spec-gate` CI refuses a code PR whose issue isn't in *Implement* |
| **Review** | CI green; a maintainer reads the diff against the spec | Approved PR | Maintainer | **Code review**: tests prove the requirement; leak gate clean; reference cases (RYDE blocks, DJT warns) unchanged → *Done* (merge) |
| **Done** | Merged and released | | Automatic on close | |
| **Won't do** / **Blocked** | With a comment saying why | | Maintainer | |

Small fixes (a typo, a broken link, a failing test with an obvious cause) can
skip *Specify* to *Tasks*. A maintainer adds the label `size:trivial` and
moves the item straight to *Implement*. Anything that changes a verdict, a
threshold, what's stored or what's published is never trivial.

### How the gates are enforced

1. **Only maintainers can move items.** The project is public to read; write
   access is the maintainers team only.
2. **The board writes the labels.** A sync job (`project-sync` in
   `red-flag-club/.github`, every 15 minutes) copies each item's Phase onto its
   issue as a `phase:*` label and removes the old one. Labels on issues can
   only be set by people with triage access, so a contributor can't fake one.
3. **`spec-gate` checks every pull request** in every repo (a reusable
   workflow in `red-flag-club/.github`):
   - the PR body links an issue (`Closes #12`, `Refs red-flag-club/stories#3`);
   - a PR that changes only `specs/` or `docs/` needs that issue in
     *Specify*, *Plan* or *Tasks*;
   - any other PR needs it in *Implement* or *Review*;
   - every box in the PR template's "Hard rules" checklist is ticked.
4. **Branch protection** on `main`: one maintainer approval, CI green
   (`tests`, `leak-gate`, `spec-gate`), no force-pushes.

## Labels (the same in every repo)

| Label | Meaning |
|---|---|
| `phase:inbox`, `phase:specify`, `phase:plan`, `phase:tasks`, `phase:implement`, `phase:review` | Set by the board sync; never by hand |
| `type:feature`, `type:bug`, `type:wrong-verdict`, `type:red-flag-report`, `type:translation`, `type:story-correction`, `type:docs` | Set by the issue form |
| `size:trivial` | Maintainer-only fast path (above) |
| `area:layer1`, `area:layer2`, `area:layer3`, `area:server`, `area:site`, `area:stories`, `area:assistant` | Where the change lands |
| `good first issue`, `help wanted` | For newcomers |
| `needs:personal-data-removed` | A maintainer has hidden a comment; the author is asked to repost without it |
| `hard-rule` | Touches a hard rule; needs two maintainer approvals |

## Using Claude Code (or any assistant) here

The Spec Kit commands (`/speckit.specify`, `/speckit.plan`, `/speckit.tasks`,
`/speckit.implement`) and the rules in `CLAUDE.md` are in the code repo. An
assistant may draft any document or PR. It never moves a board item, merges,
approves, or publishes a story. Those are human steps.

## Repositories and what goes where

| Repo | Visibility | Issues for |
|---|---|---|
| `red-flag-club/red-flag-club` | public | Code, the site's source, specs, docs: most work |
| `red-flag-club/stories` | public | Story corrections and takedowns only |
| `red-flag-club/red-flag-club.github.io` | public | None (built by a bot); issues are off |
| `red-flag-club/.github` | public | Org-wide templates, the board sync, `spec-gate` |
| private repos | private | Maintainer operations (data, deployment, story inbox) under the same pipeline |
