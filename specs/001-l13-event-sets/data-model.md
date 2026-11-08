# Data Model: L1.3 Event Sets

All files are UTF-8 JSON or JSONL, committed under `data/`.

## Band — `data/universe/bands.jsonl` (one line per preview)

```json
{"lo": 0, "hi": 10000000, "total_items": 384, "rows": 200, "saturated": true,
 "fetched": "2026-10-08",
 "tickers": [{"symbol": "CVR", "market_cap": 9516400.0, "float": 861044.0, "name": "..."}]}
```

A later line for the same `[lo, hi]` replaces the earlier one.

## Snapshot — `data/universe/snapshot_<date>.json`

```json
{"date": "2026-10-08", "complete": true, "bands": [{"lo":..,"hi":..,"total_items":..,"rows":..}],
 "gaps": [], "saturated": [], "n_symbols": 2873, "symbols": ["AAPL", ...]}
```

`complete` is true only when the bands tile $0–500M with no gaps and none is saturated.

## Event record — `data/events/events_<batch>.jsonl`

```json
{"symbol": "RYDE", "origin": "seed", "batch": "seed", "as_of": "2026-10-08",
 "label": "positive", "ramp_start_date": "2024-08-22", "ramp_start_price": 8.65,
 "peak_date": "2024-09-06", "peak_price": 17.33, "run_up_pct": 1.003,
 "trough_date": "2024-10-01", "trough_price": 0.69, "drawdown_pct": 0.96,
 "sessions_after_peak": 20,
 "isolated_spike_peak": false, "suspect_bad_print": false, "zero_volume_bars": 0,
 "flat_bar_share": 0.0, "stale_quote": false,
 "bars": [["2024-05-28", 4.1, 4.2, 4.0, 4.1, 12345], ...]}
```

`label` ∈ {`positive`, `control`, `pending`}. The flags are informational
and never change `label`:

- `suspect_bad_print`: isolated spike peak on zero or below-median volume
  (research R9).
- `stale_quote`: `flat_bar_share` ≥ 0.5 from ramp start onward (research R10).

## Progress — `data/l13/progress.json`

```json
{"snapshot": "data/universe/snapshot_2026-10-08.json", "seed": 42,
 "order": ["SYM1", "SYM2", ...],
 "done": {"SYM1": {"batch": "b001", "bars_total": 1195, "bars_kept": 1190,
                    "dropped_interpolated": 5, "dropped_nonpositive": 0, "status": "ok"}},
 "batches": [{"id": "b001", "symbols": [...], "ingested": "2026-10-08"}]}
```

`status` ∈ {`ok`, `no_data`}. Symbols requested but missing from a payload are recorded as
`no_data` so they are not retried forever.
