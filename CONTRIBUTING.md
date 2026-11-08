# Contributing

Thank you for helping. Before anything else: **never post personal data**
(yours or anyone's) in an issue, PR, discussion or commit. That means no names,
phone numbers, account numbers, chat screenshots or group links. Stories go
only through the site's encrypted form.

## How a change moves (summary of [docs/workflow.md](docs/workflow.md))

| Step | You do | A maintainer reviews and moves it to |
|---|---|---|
| 1. Issue | Pick a form. Each asks **what**, **why** (who it protects) and **how** | *Specify*, or closes with a reason |
| 2. Spec | `specs/NNN-name/spec.md`: `/speckit.specify` in Claude Code, or copy `.specify/templates/spec-template.md`. User stories, requirements, success criteria. Open a PR with `Refs #N` | *Plan* |
| 3. Plan | `/speckit.plan`: design and a **constitution check** against the hard rules below | *Tasks* |
| 4. Tasks | `/speckit.tasks` + `/speckit.analyze`; tasks become sub-issues | *Implement* |
| 5. Code | A small PR per task: `Closes #N`, tests first, hard-rules box ticked | *Review* happens automatically |
| 6. Review | Respond to review; CI green (`tests`, `node`, `leak-gate`, `spec-gate`) | *Done* (merged) |

`spec-gate` blocks a code PR whose issue isn't in *Implement*. That isn't red
tape: this project's whole job is to stop people acting on a pitch they
haven't checked, so we hold our own changes to the same standard.

Trivial fixes (typos, broken links, an obviously broken test) can be fast-tracked:
a maintainer labels the issue `size:trivial` and moves it straight to
*Implement*.

## Hard rules (a PR that breaks one is not merged)

1. **Never a buy signal.** Nothing in `src/`, `server/` or `web/` recommends
   entering, adding to or sizing a position. The checks decide *not* to trade.
2. **No order placing, no brokerage connection.** The project is read-only and
   uses public data.
3. **No lookahead.** Every function that reads dated data takes an `as_of`
   and touches only data dated on or before it. New data loaders need a test
   proving later data can't change the result.
4. **No live value in a historical test.** Float, market cap and shares
   outstanding change over time; use point-in-time values with their date.
5. **Bias toward false alarms.** A false alarm costs one skipped trade; a
   missed pump can cost someone's savings. If a change lowers recall, the PR
   says so with numbers and sample sizes.
6. **Drop gap-fill bars.** Bars flagged `interpolated` carry no information;
   filter them and assert how many are left.
7. **No accusations.** Show red flags and evidence; never state that a
   company or person is a fraud. Label allegations as allegations.
8. **No personal data anywhere public.** `python3 scripts/public_export.py
   check --tree .` must stay clean.
9. **Reference cases hold.** RYDE (September 2024) is blocked before its peak;
   DJT (October 2024) only gets a warning. If a change makes DJT block, the
   change is wrong.
10. **Every metric with its sample size.**

## Set-up

```bash
python3 -m pip install -r server/requirements.txt pytest
python3 -m pytest -q
node --test web/*.test.mjs worker/stories/*.test.mjs
python3 scripts/public_export.py check --tree .
```

Tests use synthetic fixtures (`scripts/make_synthetic.py`). If you change the
generator, commit the regenerated files; CI checks they match.

## Good first issues

Translations, quiz questions, assistant intents, accessibility fixes, docs,
and new synthetic test cases. Look for the
[`good first issue`](https://github.com/red-flag-club/red-flag-club/labels/good%20first%20issue) label.

## Using an AI assistant

Welcome. Claude Code picks up `CLAUDE.md` and the Spec Kit commands in this
repo. The assistant drafts; a human opens the PR, answers review, and is
responsible for it. Assistants never move board items, approve, merge, or
handle stories.

## Conduct

[Code of Conduct](https://github.com/red-flag-club/.github/blob/main/CODE_OF_CONDUCT.md).
Be kind to people who lost money; nobody here is "greedy" or "stupid".
