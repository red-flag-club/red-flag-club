# Research: L1.4 / L1.5

## R1. The filing index has coverage holes

`get_sec_filing_index` returns nothing for JAGX between 2021 and 2026-09-18,
although JAGX filed every 10-Q and 10-K in that span. ACON's coverage starts
2022-06. A missing filing therefore cannot be read as a missing disclosure.

- **Decision**: `stale_disclosure` is unknown when no filing is on record by T,
  or when the last one is more than 365 days old.
- **Decision**: `foreign` is unknown when no filing is on record by T.

## R2. Inputs with no point-in-time source

- **Float**: small-cap filing content 404s (L1.3 R8).
- **Market cap**: needs a historical share count, which comes from the same
  unavailable filing facts. Today's market cap is forbidden by hard rule 3.

Both are always unknown. Under `hi` they are red flags, so `hi` needs only 2
of the other 4 inputs to reach 4/6.

## R3. Listing age from price history

The first non-interpolated daily bar is a usable listing proxy:
- ACON IPO April 2022: first bar 2022-04-22.
- RYDE IPO 2024-03-06: first bar 2024-03-05 (placeholder bars dropped).

1,545 of 2,431 symbols start at the data start (2022-01). For those, the age
is a lower bound, and it is unknown until 18 months after 2022-01-03.

## R4. Annual results

`get_financials` (annual) gives net income by fiscal period end. A result
counts as public 120 days after period end (20-F deadline; 10-K is 90 days).
A late filer can leak by its delay. That leak only matters if the sign of net
income changed, which is rare for these issuers.

## R5. Evaluation window

Over the full stored window (60 sessions before the ramp through the peak),
the latch fires somewhere on 97.7% of controls (N=2,492), mostly from noise
long before the run. The metrics use sessions from ramp start through the
peak, which is when a buyer is exposed. Lead time counts back from the peak:
0 means BLOCK first appeared on the peak session.

## R6. Pump detector alone (default config, before tuning)

Latched on or before the peak:

| Set | N | Latched |
|---|---|---|
| Unflagged positives | 295 | 0.868 |
| All positives | 338 | 0.778 |
| Controls | 2,485 | 0.924 |

Because BLOCK needs the latch, these are upper bounds on BLOCK recall. The
structural gate is what has to separate collapses from controls.

## R7. Sampling

All 349 positives, plus 400 controls drawn with seed 42 from 2,492. Latch
precision weights control sessions by 2,492 / 400.

## R8. Tuning result

17 full runs, one knob at a time, in PLAN order. No value of any knob meets
the gate (`data/l14/tuning.json`). Recall and FP move together at every step,
which is what a gate with no discriminating input looks like. Threshold 6/6
reaches FP 0.193 only by cutting recall to 0.234. That trade is rejected under
hard rule 4.
