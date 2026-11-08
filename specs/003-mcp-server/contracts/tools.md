# MCP Tool Contract

Transport: MCP streamable HTTP at `/mcp` (stateless, JSON responses).
Auth: `Authorization: Bearer $PD_MCP_TOKEN`, or the URL `/t/$PD_MCP_TOKEN/mcp`.
`GET /healthz` → `200 {"status":"ok","version":"..."}`, no auth.

Every tool returns text (a compact report) plus structured content. Every
response includes `"note": "Not a buy signal. No order is placed."`. Dates are
ISO `YYYY-MM-DD`; omitted `as_of` means the last completed session.

All tools are annotated `readOnlyHint: true`, `destructiveHint: false`.

## check_ticker

| arg | type | default | notes |
|---|---|---|---|
| symbol | str | — | `^[A-Z][A-Z0-9.\-]{0,9}$` |
| as_of | str? | last session | future dates refused |
| position_usd | float | 250 | size being considered, for dollars-at-risk |
| account_usd | float | 1000 | for the suggested ceiling |
| fundamentals | object? | — | `{float, market_cap, pe_ratio, high_52_weeks, low_52_weeks}`; used only if `as_of` is today |
| earnings | list? | — | brokerage `get_earnings_results` rows |
| detail | bool | false | include the full `facts` block |

Returns `{symbol, as_of, verdict: VETO|CAUTION|NO FLAGS|INSUFFICIENT DATA|NO DATA,
vetoes[], cautions[], summary{last_close, ret_1m, vs_sma200, vol_annual,
structural_score, structural_unknown[], last_sec_filing}, data{bars, dropped,
source, adjusted, splits[], suspect_bad_prints[]}, note}`.

## was_i_pumped

| arg | type | notes |
|---|---|---|
| symbol | str | |
| buy_date | str | the verdict uses data `<= buy_date` only |

Returns `{symbol, buy_date, at_the_time: <check_ticker result as of buy_date>,
hindsight: {peak_after, peak_date, max_drawdown_from_buy, ret_5, ret_20, ret_60,
last_close, last_date}, note}`. Horizons not yet elapsed are `"not yet"`.
`hindsight` is labelled as such in the text and never feeds the verdict.

## pump_scan

| arg | type | notes |
|---|---|---|
| symbols | list[str] | 1–50 |
| as_of | str? | |

Returns rows `{symbol, verdict, run_up_5, run_up_10, volume_ratio_20, last_close,
reason}` sorted VETO first, then by `run_up_10` descending. Symbols with no data
are listed with `verdict: NO DATA`.

## monitor_digest

| arg | type | notes |
|---|---|---|
| positions | list | `{symbol, quantity, average_cost}`; any other field (account numbers included) is discarded |
| orders | list? | Brokerage order rows (as `get_equity_orders` returns) for time stop / abandoned |
| as_of | str? | |

Returns `{as_of, holdings: [{symbol, quantity, average_cost, last_close, value,
unrealized_pnl, unrealized_pct, verdict, alerts[]}], alert_count, note}`.
Nothing in the request is written to disk or logged.

## data_status

No args. Returns `{provider, sec_contact_set, symbols_cached, bars_cached,
calls_last_hour, unique_symbols_this_month, limits, db_path}`.

## Errors

Refusals are returned as tool results with `isError: true` and a one-line
reason: invalid symbol, future date, more than 50 symbols, rate limit reached
with no cache coverage ("data unavailable, try later"), provider not
configured.
