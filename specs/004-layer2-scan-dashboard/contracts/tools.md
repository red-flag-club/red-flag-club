# Contract additions (spec 004)

## MCP tool: is_pumping (PLAN L2.3)

| arg | type | notes |
|---|---|---|
| symbol | str | |

Returns `{symbol, last_session, on_scan_today, days_on_scan (last 20 sessions),
first_seen, last_seen, recent: [{session, reason, verdict}], check: <check_ticker
as of last session>, note}`.

## MCP tool: scan_latest

| arg | type | default |
|---|---|---|
| session | str? | latest scanned session |
| limit | int | 25 (max 200) |

Returns `{session, n_hits, n_veto, rows: [{symbol, close, ret_5, ret_21,
rel_vol_30, verdict, reason, flags}], forward: {n_labelled, n_collapsed,
recall, fp_rate, note}, note}`. VETO first, then by `ret_5` descending.

## HTTP: GET /dashboard/

Behind the token gate: `/t/<token>/dashboard/` (or Bearer header).
`200 text/html` — the last built page; `503` with a one-line message if no
page has been built yet. `Cache-Control: no-store`.

## HTTP: POST /jobs/refresh

Behind the token gate. Runs the refresh now and returns its summary JSON
(`409` if `PD_SCAN_SOURCE=off`). Exists because DuckDB allows one writer
process: while the server runs, `./run.sh scan` calls this instead of opening
the database.

## CLI

```
./run.sh scan [--backfill N] [--check-source] [--fixture]
./run.sh dashboard            # rebuild the page from the DB
```
