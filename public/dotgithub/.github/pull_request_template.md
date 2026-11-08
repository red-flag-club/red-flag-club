## What

<!-- What this PR changes, in plain words. -->

## Why

<!-- Who it protects or what it fixes. Link the issue (it must be approved for this phase): -->
Closes #

## How

<!-- How it works and how you tested it. Name the tests that prove the spec's requirements. -->

Spec: `specs/NNN-name/` <!-- or "size:trivial" -->

## Hard rules

<!-- spec-gate refuses the PR until every box is ticked. If one doesn't apply, tick it: it means "I checked". -->
- [ ] No order placing, no brokerage write calls, and nothing here recommends buying or sizing up.
- [ ] No lookahead: anything that reads dated data takes an `as_of` and has a test proving later data can't change the result.
- [ ] No live API value (float, market cap, shares) hardcoded into a historical test.
- [ ] Thresholds still bias toward false alarms; if recall drops, this PR says so with numbers and sample sizes.
- [ ] Interpolated (gap-fill) bars are filtered before any calculation.
- [ ] No personal data, account numbers, brokerage payloads or real chat content; `scripts/public_export.py check` is clean.
- [ ] No stock or person is called a fraud; allegations are labelled as allegations.
- [ ] Reference cases unchanged: RYDE (Sep 2024) still blocks, DJT (Oct 2024) still only warns.
