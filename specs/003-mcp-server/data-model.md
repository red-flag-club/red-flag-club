# Data Model: pd-defence MCP Server

One DuckDB file, `$PD_DATA_DIR/pd.duckdb`. No personal data is stored: no
account numbers, positions or orders.

## bars

| column | type | notes |
|---|---|---|
| symbol | VARCHAR | upper case |
| date | DATE | session date |
| o, h, l, c | DOUBLE | split-adjusted |
| v | DOUBLE | split-adjusted volume |
| raw_c | DOUBLE | unadjusted close (NULL if the source gives only one) |
| split_factor | DOUBLE | 1.0 unless a split took effect that day |
| source | VARCHAR | `tiingo`, `massive`, `brokerage-payload`, `fixture` |
| fetched_at | TIMESTAMP | |

Primary key `(symbol, date)`; a later fetch replaces the row (providers revise
adjustments after splits). Only cleaned bars are stored (research R2).

## coverage

What range has been fetched for a symbol, so repeat requests are cache hits.

| column | type | notes |
|---|---|---|
| symbol | VARCHAR | PK |
| first_date, last_date | DATE | requested range (not first/last bar) |
| fetched_at | TIMESTAMP | |
| source | VARCHAR | |
| status | VARCHAR | `ok` or `no_data` (memoised for 24 h) |
| dropped | INTEGER | bars dropped by `clean_bars` on the last fetch |

A request `[start, as_of]` is a hit when `first_date <= start` and
`last_date >= min(as_of, last completed session)`, and, if `as_of` is today,
`fetched_at` is younger than `PD_TODAY_TTL_MIN` (default 240).

## filings

| column | type | notes |
|---|---|---|
| symbol | VARCHAR | |
| cik | VARCHAR | 10-digit |
| form | VARCHAR | e.g. `6-K`, `10-Q` |
| filed | DATE | |

Plus `filings_coverage(symbol, cik, fetched_at, status)` with a 24 h TTL.
Reads always filter `filed <= as_of`.

## checks

Scorecard log; no personal data.

| column | type |
|---|---|
| ts | TIMESTAMP |
| tool | VARCHAR |
| symbol | VARCHAR |
| as_of | DATE |
| verdict | VARCHAR |

## provider_calls

| column | type | notes |
|---|---|---|
| ts | TIMESTAMP | |
| provider | VARCHAR | |
| symbol | VARCHAR | |
| status | VARCHAR | ok, no_data, RateLimited, ProviderError |

Used to report free-tier usage in `data_status` (calls this hour, unique
symbols this month).

## Validation rules

- `date <= as_of` on every read used for a verdict (II).
- `fundamentals` input ignored unless `as_of == today` (III).
- Symbols match `^[A-Z][A-Z0-9.\-]{0,9}$`; anything else is refused before any
  provider call.
