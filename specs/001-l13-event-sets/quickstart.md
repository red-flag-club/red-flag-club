# Quickstart: L1.3 Event Sets

The agent fetches; the CLI ingests. Every step is resumable.

## 1. Universe (read-only)

For each band, call `preview_scan` with:

```text
filters: INSTRUMENT_TYPE = STOCK; MARKET_CAP BETWEEN [lo, hi]
columns: Market cap, Float, Shares outstanding, Average volume, Sector, RSI
```

Then record the spilled payload:

```bash
python3 scripts/l13.py universe-add <payload.txt>
python3 scripts/l13.py universe-build --date 2026-10-08   # lists gaps / saturated bands
```

Split any saturated band and repeat until `complete: true`.

## 2. Seeds

```bash
# agent: get_equity_historicals(["RYDE","RETO"], start 2022-01-01, interval day)
python3 scripts/l13.py ingest --batch seed --origin seed --as-of 2026-10-08 \
    --expect RYDE,RETO <payload.txt>
```

## 3. Sweep

```bash
python3 scripts/l13.py next-batch --size 50     # prints groups of 10 symbols + a batch id
# agent: one get_equity_historicals call per group
python3 scripts/l13.py ingest --batch b001 --as-of 2026-10-08 <payload1.txt> <payload2.txt> ...
python3 scripts/l13.py report
git add data/ && git commit
```

## 4. Float check

Not scripted: small-cap filing content 404s (research R8). The manual 0/5
result is recorded in `data/l13/float_check_2026-10-08.json`.

## Validate

```bash
python3 -m pytest -q
```
