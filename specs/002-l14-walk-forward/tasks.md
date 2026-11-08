# Tasks: L1.4 / L1.5

- [x] T001 Spec, plan, research (`specs/002-l14-walk-forward/`)
- [x] T002 `layer1_verdict(cfg, block_threshold)`; defaults unchanged, RYDE still BLOCK
- [x] T003 `src/harness.py`: `point_in_time`, `issuers` (lo/hi), `replay`, `metrics`
- [x] T004 Tests: truncation (bars), filings and results after the peak, first bar after T, index holes, report lag, listing age, RYDE replay, metrics, tuning rule
- [x] T005 `scripts/l14.py select`: all positives + 400 controls (seed 42)
- [x] T006 Live: filing index and annual financials for 503 symbols (read-only, subagents)
- [x] T007 `scripts/l14.py extract` from session transcripts → `data/l14/`
- [x] T008 Baseline run with N → `data/l14/runs/baseline.json`
- [x] T009 L1.5 one-knob sweep → `data/l14/tuning.json`; gate not met, defaults kept
- [x] T010 PLAN.md, PROGRESS.md, CLAUDE.md status
- [ ] T011 Phase D — gated on T009; needs the owner's decision
