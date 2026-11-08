# Site data contract (public JSON, for community bots)

All files under `data/`. Dates ISO. Percentages are fractions (0.5 = +50%).
`prices` is false unless the owner enabled them; then `close` fields appear.

## meta.json
`{version, built_at, data_session, prices, counts{symbols, risk_list, scan_hits},
retention, gate, base_rates{bracket{n, win, breakeven, per_trade}, collapse{n_runs, n_collapsed}},
disclaimer}`

## movers.json
`{session, penny_max, min_value, lists: {day|week|month: [row…≤100]}}`
row = `{s, band, chg, runup, rv, verdict, flags[], why, scan_days, spark[]}`
(`spark`: closes normalised to 100 at the window start, 2 decimals)

## symbols.json
`{session, fields:[...], rows:[[...], ...]}` — every symbol with close ≤ $30:
`s, band, r1, r5, r21, rv, verdict|null, flags, why, scan_days, first_seen` (+ `close` if prices)

## scan.json
`{sessions:[{session, hits:[{s, reason, verdict, r5, r21, flags}]}]}` — last 20 scanned sessions

## outcomes.json
`{forward{…}, backfilled{…}, episodes:[{s, first_logged, label, runup, drawdown, peak_date}]}`

## CSV
`data/movers_day.csv`, `movers_week.csv`, `movers_month.csv`, `symbols.csv` — same columns.
