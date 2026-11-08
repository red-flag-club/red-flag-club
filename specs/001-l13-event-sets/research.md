# Research: L1.3 Event Sets

Findings from live probes on 2026-10-08, before design.

## R1. Universe without a scanner write

- **Decision**: `preview_scan` with `FILTER_TYPE_INSTRUMENT_TYPE = STOCK` and
  `FILTER_TYPE_MARKET_CAP BETWEEN [lo, hi]`, split adaptively until every band returns
  `total_items <= 200`.
- **Rationale**: `preview_scan` evaluates the same filters as a saved scan but persists nothing,
  so it is read-only. Probe: $40–50M → 86 rows; $0–10M → 384 rows (saturated, needs splitting).
- **Alternatives rejected**: reusing scan `f34e7102-…` via `create_scan` (a write; the
  authorization was withdrawn); iterating an external ticker list (none available offline).

## R2. Getting payloads from the agent into Python

- **Decision**: rely on the harness spilling large MCP results to
  `~/.claude/projects/.../tool-results/*.txt` and pass those paths to `scripts/l13.py`.
  Scan previews add extra columns (Float, Shares outstanding, Average volume, Sector, RSI) so the
  response is large enough to spill, which also captures useful context.
- **Rationale**: no hand transcription. Probe: a 4-symbol daily payload (831 kB) and a
  200-row scan (91 kB) both spilled.
- **Alternatives rejected**: copying tickers from inline output (error-prone at 2,000+ names).

## R3. Bar hygiene beyond `interpolated`

- **Decision**: drop bars that are `interpolated` **or** have any OHLC ≤ 0.
- **Rationale**: RYDE returns real-flagged (`interpolated` absent) all-zero bars on
  2024-02-29..03-04, before its first trade. A zero close crashes `find_runs` (ZeroDivisionError)
  and would otherwise make any later price an infinite run-up.

## R4. Censored runs

- **Decision**: a run is *pending* when fewer than 20 sessions follow the peak in the data and the
  drawdown so far is < 70%. Pending runs are stored but excluded from positives and controls.
- **Rationale**: `find_runs` labels such runs `collapsed=False`. Probe: XRPN's run peaking
  2026-10-01 had 3 sessions of follow-through and was labelled a control. Counting it would put an
  unresolved, possibly collapsing event into the control set, against hard rule 4.
- **Alternative rejected**: changing `find_runs` (L1.2 is shipped and tested; the censoring rule
  belongs to the set builder, which knows `as_of`).

## R5. What to store per event

- **Decision**: OHLCV from 60 real sessions before ramp start through peak + 20 sessions, plus the
  label fields. Bars as compact arrays `[date, o, h, l, c, v]`.
- **Rationale**: L1.4 replays Layer 1 session by session; `pump_state` needs a 5-session baseline
  and the structural gate needs no bars. 60 sessions gives margin for L1.5 window experiments
  without re-fetching. Full histories (~1 MB per 10 symbols) are not committed.

## R6. Sampling order

- **Decision**: process the snapshot in one fixed shuffled order (seed 42), seeds (RYDE, RETO)
  in a separate tagged batch.
- **Rationale**: if the sweep stops early, the processed prefix is a random sample, so the
  positive rate it reports is unbiased for the survivor universe.

## R7. Reference results from the probe (N=4 symbols)

| Symbol | Run (peak) | Drawdown | find_runs label |
|---|---|---|---|
| RYDE | 2024-09-06 | 96% | collapsed |
| RETO | 2023-08-18 | 91% | collapsed |
| RETO | 2026-09-15 | 97% | collapsed |
| XRPN | 2026-10-01 | 18% (3 sessions) | control → should be *pending* |
| DJT | 2024-01-22, 2024-04-30 | 30%, 12% | control |

FINDINGS.md's XRPN −64% is not ≥ 70%, and the run is unresolved anyway.

## R8. Live float check (US4) — 0/5

CARL (424B4 2025-07-24, 10-K 2026-02-25), JAGX (424B5), KOSS (10-K x8), TPST
(10-K, 424B5 x2) and GIBO (no filings listed): `get_sec_filing` returned 404
for every filing tried, and `get_sec_filing_facts` / `_catalog` returned no
facts for the 10-Ks. Control: AAPL's 10-K returns a table of contents. For
small caps this source provides the filing index only. A record/replay harness
(T016) would have nothing to replay and was not built.

## R9. Bad prints vs real one-day spikes

An isolated one-bar spike (close >= 3x both neighbours) is not enough to call
a print bad: JAGX (27.9M shares), MI (167M) and AZTR (11M) are real one-day
pump-and-dumps. The bad ones trade at or below their own recent median volume
(REED 196 shares, SSM 184, VCIG 0). `suspect_bad_print` = isolated spike AND
(zero volume OR volume below the prior-20-session median). It is flagged and
reported, never dropped.

## R10. Ghost quotes (full-sweep audit)

The full sweep put ELOX (14 positives) and DCX (15) at the top of the per-symbol
positive count. ELOX after 2024 is a stale quote: it flips between $0.0011 and
$0.000011 on bars where open = high = low = close, and each flip reads as a
99x run that collapses. DCX, COPR and MSLE show the same thing. The share of
flat bars from ramp start onward separates them. Of 349 positives, 302 have a
flat share below 0.1, 12 fall between 0.1 and 0.5, and 35 sit at or above 0.5,
all from those four symbols. `stale_quote` is flat share ≥ 0.5. Absolute price
filters were rejected because prices are split-adjusted (DCX shows $57M). The
flag is reported and never drops or relabels an event. It was backfilled from
the stored windows, which hold every bar from ramp start through the window
end, so no re-fetch was needed.
