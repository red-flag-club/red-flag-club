# Data Model: Layer 2 Scan Log

New DuckDB tables beside the spec 003 ones. No personal data.

## market_daily
| column | type | notes |
|---|---|---|
| date | DATE | session |
| symbol | VARCHAR | |
| o, h, l, c, v | DOUBLE | as published that session |
| source | VARCHAR | `massive-grouped`, `brokerage-payload`, `fixture` |

PK (date, symbol). Written once per session; a re-fetch of the same session
replaces that session's rows only (no log row depends on them until logged).

## sessions
| column | type | notes |
|---|---|---|
| date | DATE PK | |
| status | VARCHAR | `loaded`, `empty` (retry), `no_session` (holiday) |
| n_symbols | INTEGER | |
| dropped | INTEGER | non-positive rows dropped |
| tries | INTEGER | |

## splits
| column | type |
|---|---|
| symbol | VARCHAR |
| date | DATE |
| ratio | DOUBLE (split_to / split_from) |

## scan_log  (append-only)
| column | type | notes |
|---|---|---|
| session | DATE | |
| symbol | VARCHAR | PK (session, symbol) |
| logged_at | TIMESTAMP | |
| close | DOUBLE | |
| ret_1, ret_5, ret_21 | DOUBLE | run-ups per R2 |
| rel_vol_30 | DOUBLE | NULL if < 30 sessions |
| reason | VARCHAR | `5-session run-up`, `21-session run-up` |
| flags | VARCHAR | comma list: `split`, `possible_split`, `bad_print`, `short_history` |
| backfilled | BOOLEAN | logged by a catch-up of > 5 sessions old |
| verdict | VARCHAR | VETO / CAUTION / NO FLAGS / INSUFFICIENT DATA |
| reasons | VARCHAR | vetoes then cautions, `; `-joined |

Insert uses `INSERT OR IGNORE`; there is no UPDATE or DELETE on this table
anywhere in the code (tested by grep).

## outcomes
| column | type | notes |
|---|---|---|
| symbol | VARCHAR | |
| first_logged | DATE | PK (symbol, first_logged) |
| label | VARCHAR | `pending`, `collapsed`, `no_collapse` |
| peak_date, peak | DATE, DOUBLE | |
| drawdown | DOUBLE | |
| decided_on | DATE | session when decided |

An episode starts at a symbol's first log row after ≥ 20 sessions without one.
`pending` rows are re-evaluated each refresh; decided rows are final.

## scan_runs
| column | type |
|---|---|
| ts | TIMESTAMP |
| sessions_scanned | INTEGER |
| hits | INTEGER |
| status | VARCHAR (`ok`, `partial: <reason>`) |
