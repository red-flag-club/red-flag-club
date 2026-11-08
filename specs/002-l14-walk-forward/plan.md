# Implementation Plan: L1.4 Walk-Forward Harness and L1.5 Tuning

**Branch**: `phase-c/l14-harness` | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

## Summary

Replay `layer1_verdict` over each sampled L1.3 event from ramp start to peak.
At each session the pump detector sees only bars dated `<= T`; the structural
gate sees an Issuer rebuilt from filings and annual results public by T. Inputs
that this data cannot establish point-in-time are scored both ways, giving a
`lo` / `hi` bracket on every metric.

## Technical Context

**Language**: Python 3.11+, stdlib only. **Tests**: pytest, offline.
**Inputs**:
- `data/events/*.jsonl` (L1.3).
- `data/l13/progress.json` (`first_bar`).
- `data/l14/filings.json` (`get_sec_filing_index`, 2021-01-01..2026-10-08).
- `data/l14/financials.json` (`get_financials`, annual, 8 periods).
**Constraints**: no brokerage writes; MCP calls are made by the agent and its
subagents; small responses never spill to disk, so `scripts/l14.py extract`
reads them from the session transcripts.

## Constitution Check

| Principle | Compliance | Status |
|---|---|---|
| I. Read-only | `get_sec_filing_index`, `get_financials` only | PASS |
| II. No lookahead | bars sliced to `<= T` and asserted; `point_in_time` filters `<= T`; first bar after T raises `LookaheadError`; truncation tests | PASS |
| III. Point-in-time | no live float / market cap used; both are unknown | PASS |
| IV. Recall over precision | unknown inputs scored as red flags on the primary (`hi`) bound | PASS |
| V. Hygiene / N | every metric printed with N+ and N-; coverage holes stated | PASS |

## Structure

```text
src/layer1.py          # layer1_verdict gains cfg and block_threshold (defaults unchanged)
src/harness.py         # point_in_time, issuers, replay, metrics (pure)
scripts/l14.py         # select, extract, run
tests/test_harness.py
data/l14/              # sample.json, filings.json, financials.json, runs/*.json
```
