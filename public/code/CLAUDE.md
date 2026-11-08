# Red Flag Club

Open-source defence against pump-and-dump scams in small-cap stocks, and the
community site at https://red-flag-club.github.io. Read `README.md` for what
exists and what's pending, and `docs/workflow.md` for how work moves.

## Before writing code

Work is spec-driven (GitHub Spec Kit). A change needs an issue in the
*Implement* phase on the board and a spec under `specs/NNN-name/`. If there
isn't one, write or update the spec (`/speckit.specify`, `/speckit.plan`,
`/speckit.tasks`) instead of code. Never move board items, approve or merge;
those are human steps. `.specify/memory/constitution.md` restates the rules
below; this file wins if they disagree.

## Hard rules

1. **No brokerage writes, ever.** This code has no brokerage connection and
   must not gain one. Never call an order-placing tool.
2. **No lookahead.** Every backtest or check takes `as_of` and touches only
   data dated `<= as_of`. A new data loader needs a test proving it.
3. **No live value in a historical test.** Point-in-time fields change; RYDE's
   float was 3.0M in September 2024 and far larger later.
4. **Bias every threshold toward false positives.** Never improve precision by
   weakening recall without saying so explicitly, with sample sizes.
5. **Filter `interpolated` bars** before any calculation and assert the
   survivor count.
6. **Never a buy signal.** Layers 1-3 decide *not* to trade.
7. **Never call a stock or person a fraud.** Red flags and evidence only.
8. **No personal data in any public file.** Run
   `python3 scripts/public_export.py check --tree .` before every commit.
9. **Stories:** never publish one without the maintainer's `approve`; never
   commit `community/inbox/` or drafts; never weaken the checker to let a
   draft through.

## Reference cases (regression tests)

- **RYDE, Sep 2024**: true positive. ~3.0M float, foreign issuer filing only
  6-Ks, 82 days without an SEC filing while tripling. Must block on
  2024-09-06; the pump trigger fires 2024-09-04.
- **DJT, Oct 2024**: control, **not** a positive. ~130M float, $9B cap,
  domestic filer with ten 8-Ks in seven weeks. Must warn, not block.

## Layout and conventions

- Python 3.11+, stdlib and pandas only unless there's a reason. Pure functions
  in `src/`; nothing stateful in the scoring path.
- `src/`: Layer 1 (`layer1.py`), harness, event labelling, Layer 3,
  `check_ticker.py`. `server/`: MCP server, scan, outcomes, retention, site
  builder; it imports `src/` and `scripts/monitor.py`; nothing imports `server/`.
- `web/` is dependency-free HTML/JS/CSS; Node tests in `web/*.test.mjs`.
- Tests import `src` as a package (`from src.x import ...`). Fixtures are
  synthetic (`scripts/make_synthetic.py`, `tests/fixture_data.py`).
- `python3 -m pytest -q` runs everything; server tests skip without
  `mcp`/`duckdb` (`pip install -r server/requirements.txt`).
- Every metric is reported with the sample size that produced it.
