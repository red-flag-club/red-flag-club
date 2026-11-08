# Tasks: Community Site

- [X] T001 `server/site.py`: movers SQL (31-session pivot), penny filter (< $5, value floor), split guard, verdicts via `check()` for list + scan symbols, symbols index, scan, outcomes, meta with base rates, CSV, price stripping, copy `web/`
- [X] T002 [P] `web/index.html`, `web/app.css`: shell, menu (desktop bar / phone drawer), light/dark tokens, risk banner, disclaimer footer
- [X] T003 [P] `web/app.js`: hash router; views Today, Top 100 (day/week/month), Risk scan, Look up (#/t/SYM), Analytics (filters, sort, N, CSV), Track record, Got pumped?, About
- [X] T004 [P] `web/assistant.js`: intents (ticker check, movers, scan, lost money, report, red flags, recovery scam, what is), answers from data; `web/assistant.test.mjs`
- [X] T005 `server/jobs.py` `site`; refresh builds the site; `run.sh site`; Dockerfile copies `web/`
- [X] T006 `.github/workflows/site.yml` (self-hosted, 4× market days + dispatch, deploy key, only if `PD_SITE_REPO` set)
- [X] T007 Tests `tests/test_site.py` (files, schema, ≤100 rows, penny rule, no prices, no personal data, no external URLs, wording) and `tests/test_site_js.py` (runs node tests)
- [X] T008 Render check (headless Chromium, light/dark/phone); docs `docs/site.md`, README, CLAUDE.md, PROGRESS.md
