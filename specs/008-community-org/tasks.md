# Tasks: Red Flag Club organisation (spec 008)

`[H]` = a human step only the owner/maintainer can do (GitHub has no API for
it, or it is a review gate). `[x]` done, `[ ]` open. Branch `feature/community-org`.

## Phase 1: Organisation and move (owner, web UI)

- [x] T001 [H] Create the org `red-flag-club` (Free); 2FA required; base permission Read; members can't create repos
- [x] T002 [H] ~~Separate maintainer account~~: not needed after D1 was revised (the founder's account is the maintainer)
- [ ] T003 [H] Optional later: a `maintainers` team when there are more maintainers (CODEOWNERS uses @ashutosrath until then)
- [x] T004 [H] Install the Claude GitHub App on the org
- [x] T005 [H] Transfer `pd-defence` into the org (private), renamed `pd-defender` (2026-11-08); still to check: check secrets, variables, deploy keys and the self-hosted runner; update the laptop's git remote
- [ ] T006 [H] Move or recreate the story inbox as `red-flag-club/stories-inbox` (private); reissue the Worker's fine-grained token owned by the org; `wrangler secret put GITHUB_TOKEN`; update `INBOX_REPO`

## Phase 2: Make the code publishable (Claude, private repo)

- [x] T010 Move `research/check_ticker.py` → `src/check_ticker.py`; shim in `research/`; server, monitor, run.sh, Docker updated
- [x] T011 Synthetic fixtures (`scripts/make_synthetic.py` → `tests/fixtures/synthetic/`): RYDE/RETO/XRPN in the brokerage payload shape, gap-fill bars, pre-listing zeros; seed events labelled by the real pipeline; SEC filing subset; scanner page with made-up tickers
- [x] T012 `tests/fixture_data.py`: real fixtures in private, synthetic elsewhere (`PD_FIXTURES=synthetic` forces it); server fixture loaders fall back the same way
- [x] T013 Real-position Layer 3 tests → `tests/private/test_layer3_realdata.py`; public `tests/test_layer3.py` on synthetic data and made-up orders
- [x] T014 `src/layer1.py` self-test uses synthetic bars; owner's buy dates and loss removed (still BLOCK on 2024-09-06, trigger 2024-09-04)
- [x] T015 Owner's loss, position and username scrubbed from shared files (constitution, specs 003/008, stories checker example, docs)
- [x] T016 `scripts/public_export.py`: allowlist, overlays for four repos, leak gate (payload shapes, emails, account numbers, private paths, real-data volume fingerprints) + private-only owner patterns in `scripts/leak_patterns.private`
- [x] T017 Public overlays: code (README with what/why/how + built/pending features, CONTRIBUTING, CLAUDE.md, licences, CI, CODEOWNERS, Dependabot), stories (README, CC BY-NC-ND), site (README, .nojekyll), `.github` (profile, issue forms, PR template, CoC, SECURITY, SUPPORT, labels)
- [x] T018 `docs/workflow.md` (phases, gates, labels, enforcement) and `docs/methodology.md`
- [x] T019 `spec-gate` (reusable) + `project-sync` (board → labels) + `scripts/spec_issues.py` (tasks → sub-issues) + `scripts/org_setup.sh` (labels, settings, protection, board)
- [x] T020 Private CI job `public-export`: gate all four repos, synthetic fixtures reproducible, public tree passes its own tests; `site.yml` gates the built site and publishes stories; workflow guards accept the org
- [x] T021 `tests/test_governance.py`
- [ ] T022 [H] **Review gate:** owner reads `public/` and a `public_export.py build` of each repo before anything is created

## Phase 3: Create the public repos (maintainer account, one command)

D1 was revised to "public founder", so the owner's account creates and pushes
the public repos: either by running `scripts/publish_public.sh`, or by
creating four empty repos in the web UI and letting a Claude session (which
acts as the same account) push the built contents.

- [x] T029 `scripts/publish_public.sh`: identity check, build + gate all four repos, code repo tests, create + push one fresh commit each, tag `v0.1.0`, run `org_setup.sh`, `--seed-issues` from `public/seed_issues.json`; dry run tested
- [ ] T030 [H] `scripts/publish_public.sh --dry-run` then `scripts/publish_public.sh --seed-issues`, signed in as the maintainer account (covers creating `.github`, `red-flag-club`, `stories`, `red-flag-club.github.io` and T033)
- [ ] T033 [H] (run by T030) labels, settings, branch protection, board with the Phase field
- [ ] T034 [H] Board access (members read, maintainers write), auto-add workflows, views; `PROJECT_NUMBER` + bot App (or `PROJECT_TOKEN`) in `red-flag-club/.github`
- [ ] T035 [H] Pages on the site repo; deploy keys for site and stories repos; `SITE_DEPLOY_KEY`, `STORIES_DEPLOY_KEY`, `PD_SITE_REPO`, `PD_STORIES_REPO`, `PD_SITE_URL` in `pd-defender`; run `site.yml` once
- [ ] T036 [H] Discussions categories; pin the "how to report a pattern without personal data" post

## Phase 4: One source of truth (Claude, private repo PR)

- [x] T040a `deploy.yml` builds from `red-flag-club/red-flag-club@$(cat PUBLIC_REF)` when `PUBLIC_REF` exists (approved stories copied in from here); `docker-compose.yml` takes `BUILD_CONTEXT`
- [ ] T040b [H] After T030: `echo v0.1.0 > PUBLIC_REF` here; first deploy from the public tag
- [ ] T040c Remove the now-public code from this repo (keeps data, research, `tests/private/`, deployment, overlays)
- [x] T041a `public/seed_issues.json`: 10 starter issues from the README's pending list (what / why / how, labels)
- [ ] T041b [H] Created by `publish_public.sh --seed-issues` (T030)

## Phase 5: Launch (owner)

- [ ] T050 [H] Retire the old site repo (archive, README pointing to the new URL)
- [ ] T051 [H] Launch post (Facebook, YouTube) with the site link
