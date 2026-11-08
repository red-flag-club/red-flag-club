# Implementation Plan: Community Site

**Branch**: `feature/community-site` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

## Summary

`server/site.py` turns the DuckDB store into JSON files under
`$PD_DATA_DIR/site/data/` and copies a static single-page app from `web/`
(vanilla JS, hash routes, no build step, no dependencies). It runs at the end
of every scan refresh and by hand (`./run.sh site`). `.github/workflows/site.yml`
runs on the owner's self-hosted runner four times a market day (and on
demand): it copies `/data/site` out of the container and pushes it to the
public site repository with a deploy key.

## Technical Context

- **Python**: unchanged stack. Movers are one SQL query over the 70-session
  `market_daily` window; verdicts reuse `check_ticker.check()` with the
  scan's 60-session window and SEC filings.
- **Frontend**: plain ES2020 modules, no framework, no CDN; inline SVG
  sparklines; CSS tokens from the dashboard (light/dark).
- **Assistant**: `web/assistant.js`, pure functions (intent → answer from the
  loaded JSON); unit-tested with Node (`node --test`), skipped if Node is
  missing.
- **Size budget**: symbols index ~8k small caps × ~70 bytes ≈ 0.6 MB; lists
  3 × 100 rows; total < 2 MB.

## Constitution Check

| Principle | How | Gate |
|---|---|---|
| I Read-only | No brokerage calls; the site only reads the store | PASS |
| II No lookahead | Every exported verdict is the one computed for that session with data ≤ session (scan log) or as of the data date | PASS |
| III Point-in-time | Float/market cap still unknown; shown as unknown | PASS |
| IV Recall | Lists are wider than the scan (all penny run-ups), never narrower | PASS |
| V N everywhere | Every list and metric shows N and the data date | PASS |
| Defence path never a buy signal | Lists framed as risk, banner with base rates, tested wording | PASS |

## Structure

```text
web/index.html, web/app.js, web/app.css, web/assistant.js, web/help.js
server/site.py           build_site(store, ds, out_dir, now, prices=False)
server/jobs.py           + `site`
server/app.py            refresh builds the site; POST /jobs/refresh unchanged
.github/workflows/site.yml
docs/site.md             owner setup + JSON schema for community bots
tests/test_site.py, tests/test_site_js.py (+ web/assistant.test.mjs)
```

## Decisions

| Decision | Why | Rejected |
|---|---|---|
| Separate public site repo | Pages is free only for public repos; code stays private | Make code repo public (not yet); GitHub Pro ($4/mo, site still public) |
| Deterministic assistant | $0, no key in the browser, no abuse surface, never hallucinates a verdict | LLM in the browser (exposes key); LLM via the laptop (unbounded public cost) — later phase with a cap |
| Prices off by default | Free-tier data licences restrict redistribution | Show raw prices (licence risk) |
| No DuckDB-WASM | Several MB from a CDN for filters JS does in a few lines | |
