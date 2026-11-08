"""Private Layer 2 dashboard (spec 004, research R6).

One self-contained HTML page: inline CSS and SVG, no scripts, fonts or other
external requests, light and dark via prefers-color-scheme. Served behind the
token gate at /dashboard/. Carries no positions or account data.
"""

from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

from server.outcomes import forward_metrics
from server.store import Store, _now
from server.tools import GATE, NOTE

SPARK_SESSIONS = 60
BAR_SESSIONS = 60
MAX_ROWS = 100
PAGE_NAME = "dashboard.html"

CSS = """
:root { color-scheme: light;
  --surface-0:#f6f5f2; --surface-1:#fcfcfb; --border:#e3e2dd;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#75746f;
  --series-1:#2a78d6; --grid:#e8e7e2;
  --critical:#d03b3b; --warning:#fab219; --good:#0ca30c; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --surface-0:#121211; --surface-1:#1a1a19; --border:#2e2e2b;
  --text-primary:#f0efec; --text-secondary:#c3c2b7; --text-muted:#9a998f;
  --series-1:#3987e5; --grid:#2a2a27; } }
:root[data-theme="dark"] { color-scheme: dark;
  --surface-0:#121211; --surface-1:#1a1a19; --border:#2e2e2b;
  --text-primary:#f0efec; --text-secondary:#c3c2b7; --text-muted:#9a998f;
  --series-1:#3987e5; --grid:#2a2a27; }
* { box-sizing: border-box; }
body { margin:0; background:var(--surface-0); color:var(--text-primary);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; } h2 { font-size: 16px; margin: 0 0 12px; }
.sub { color: var(--text-secondary); margin: 0 0 20px; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
  padding: 16px; margin-bottom: 16px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.tile .n { font-size: 26px; font-weight: 600; } .tile .l { color: var(--text-secondary); font-size: 12px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { color: var(--text-secondary); font-weight: 500; font-size: 12px; }
td.num, th.num { text-align: right; }
.badge { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; font-size: 12px; }
.badge::before { content: ""; width: 8px; height: 8px; border-radius: 2px; background: var(--dot); }
.VETO { --dot: var(--critical); } .CAUTION { --dot: var(--warning); } .NOFLAGS { --dot: var(--good); }
.muted { color: var(--text-muted); } .small { font-size: 12px; }
.note { color: var(--text-secondary); font-size: 12px; }
svg text { fill: var(--text-secondary); font-size: 11px; }
"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _pct(x) -> str:
    return "n/a" if x is None else f"{x:+.0%}"


def sparkline(closes: list[float], mark: int | None, w: int = 120, h: int = 28) -> str:
    """2px line, single series; the logged session marked with a dot."""
    if len(closes) < 2:
        return '<span class="muted small">n/a</span>'
    lo, hi = min(closes), max(closes)
    span = (hi - lo) or 1.0
    xs = [2 + i * (w - 4) / (len(closes) - 1) for i in range(len(closes))]
    ys = [h - 3 - (c - lo) / span * (h - 6) for c in closes]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    dot = ""
    if mark is not None and 0 <= mark < len(closes):
        dot = (f'<circle cx="{xs[mark]:.1f}" cy="{ys[mark]:.1f}" r="4" fill="var(--series-1)" '
               f'stroke="var(--surface-1)" stroke-width="2"/>')
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="last {len(closes)} closes, {closes[0]:g} to {closes[-1]:g}">'
            f'<title>{len(closes)} sessions: low {lo:g}, high {hi:g}, last {closes[-1]:g}</title>'
            f'<polyline points="{pts}" fill="none" stroke="var(--series-1)" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>{dot}</svg>')


def hits_chart(counts: list[tuple[str, int]], w: int = 1000, h: int = 160) -> str:
    """Hits per scanned session: one series, bars with a 2px gap, rounded
    data-end, recessive grid, native tooltips per bar."""
    if not counts:
        return '<p class="muted">No sessions scanned yet.</p>'
    top = max(1, max(n for _, n in counts))
    left, bottom, plot_h = 32, 20, h - 30
    bw = (w - left) / len(counts)
    ticks = sorted({0, top} | ({top // 2} if top >= 4 else set()))
    grid = "".join(
        f'<line x1="{left}" x2="{w}" y1="{10 + plot_h - plot_h * t / top:.1f}" y2="{10 + plot_h - plot_h * t / top:.1f}" '
        f'stroke="var(--grid)" stroke-width="1"/><text x="{left - 6}" y="{14 + plot_h - plot_h * t / top:.1f}" '
        f'text-anchor="end">{t}</text>' for t in ticks)
    bars = []
    for i, (d, n) in enumerate(counts):
        bh = plot_h * n / top
        x = left + i * bw + 1
        y = 10 + plot_h - bh
        bars.append(f'<g><title>{d}: {n} hit{"s" if n != 1 else ""}</title>'
                    f'<rect x="{x:.1f}" y="10" width="{max(bw - 2, 1):.1f}" height="{plot_h}" fill="transparent"/>'
                    + (f'<path d="M{x:.1f},{10 + plot_h} V{y + min(4, bh):.1f} q0,-{min(4, bh):.1f} {min(4, bh):.1f},-{min(4, bh):.1f} '
                       f'H{x + max(bw - 2, 1) - min(4, bh):.1f} q{min(4, bh):.1f},0 {min(4, bh):.1f},{min(4, bh):.1f} V{10 + plot_h} Z" '
                       f'fill="var(--series-1)"/>' if n else "") + "</g>")
    first, last = counts[0][0], counts[-1][0]
    axis = (f'<text x="{left}" y="{h - 4}">{first}</text>'
            f'<text x="{w}" y="{h - 4}" text-anchor="end">{last}</text>')
    total = sum(n for _, n in counts)
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
            f'aria-label="hits per session, {len(counts)} sessions, {total} hits">{grid}{"".join(bars)}{axis}</svg>')


def build_page(store: Store, now: dt.datetime | None = None) -> str:
    built = (now or _now()).strftime("%Y-%m-%d %H:%M UTC")
    scanned = sorted(store.scanned_sessions())
    last = scanned[-1] if scanned else None
    rows = store.scan_rows(session=last) if last else []
    order = {"VETO": 0, "CAUTION": 1, "INSUFFICIENT DATA": 2, "NO FLAGS": 3}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), -(r["ret_5"] or 0)))
    window = scanned[-BAR_SESSIONS:]
    all_recent = store.scan_rows(since=window[0]) if window else []
    per = {d: 0 for d in window}
    for r in all_recent:
        if r["session"] in per:
            per[r["session"]] += 1
    hist = store.market_history(last, SPARK_SESSIONS, symbols=[r["symbol"] for r in rows[:MAX_ROWS]]) if rows else {}
    fwd = forward_metrics(store)
    run = store.last_run()
    n_veto = sum(r["verdict"] == "VETO" for r in rows)

    body = []
    for r in rows[:MAX_ROWS]:
        h = hist.get(r["symbol"], [])
        closes = [x["c"] for x in h]
        mark = next((i for i, x in enumerate(h) if x["date"] == r["session"]), None)
        cls = r["verdict"].replace(" ", "") if r["verdict"] in ("VETO", "CAUTION", "NO FLAGS") else ""
        body.append(
            f"<tr><td><b>{_e(r['symbol'])}</b></td>"
            f"<td><span class='badge {cls}'>{_e(r['verdict'])}</span></td>"
            f"<td class='num'>{r['close']:,.2f}</td><td class='num'>{_pct(r['ret_5'])}</td>"
            f"<td class='num'>{_pct(r['ret_21'])}</td>"
            f"<td class='num'>{_e(r['rel_vol_30']) if r['rel_vol_30'] is not None else 'n/a'}</td>"
            f"<td>{sparkline(closes, mark)}</td>"
            f"<td class='small'>{_e(r['flags']) or '—'}</td>"
            f"<td class='small muted' style='white-space:normal;min-width:240px'>{_e(r['reasons'][:160])}</td></tr>")
    more = (f"<p class='note'>{len(rows) - MAX_ROWS} more hits not shown (use the scan_latest tool).</p>"
            if len(rows) > MAX_ROWS else "")

    def metric_row(name, m):
        rec = "n/a" if m["recall"] is None else f"{m['recall']:.0%} ({m['veto_collapsed']}/{m['collapsed']})"
        fp = "n/a" if m["fp_rate"] is None else f"{m['fp_rate']:.0%} ({m['veto_no_collapse']}/{m['no_collapse']})"
        judge = "enough to judge" if m["enough"] else "too few to judge (needs ≥ 30 each)"
        return (f"<tr><td>{name}</td><td class='num'>{m['episodes']}</td><td class='num'>{m['collapsed']}</td>"
                f"<td class='num'>{m['no_collapse']}</td><td class='num'>{m['pending']}</td>"
                f"<td class='num'>{rec}</td><td class='num'>{fp}</td><td class='small muted'>{judge}</td></tr>")

    status = (f"last refresh {run['ts']:%Y-%m-%d %H:%M} UTC: {_e(run['status'])}" if run else "no refresh has run yet")
    u = store.usage("none")
    from server.scan import MARKET_KEEP_SESSIONS
    storage = (f"Storage: {u['db_bytes'] / 1e6:.1f} MB · " if u.get("db_bytes") else "") + (
        f"market bars for the last {u['market_sessions']} of at most {MARKET_KEEP_SESSIONS} sessions · "
        f"scan log {u['scan_log_rows']} rows{' since ' + u['scan_log_since'] if u['scan_log_since'] else ''}, kept permanently")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>pd-defence scan</title><style>{CSS}</style></head>
<body><main>
<h1>pd-defence — Layer 2 scan</h1>
<p class="sub">Data from session <b>{_e(last or 'none yet')}</b> · page built {built} · {status}</p>
<div class="tiles">
  <div class="card tile"><div class="n">{len(rows)}</div><div class="l">hits on {_e(last or '—')}</div></div>
  <div class="card tile"><div class="n">{n_veto}</div><div class="l">of them VETO</div></div>
  <div class="card tile"><div class="n">{len(scanned)}</div><div class="l">sessions scanned</div></div>
  <div class="card tile"><div class="n">{sum(per.values())}</div><div class="l">hits in last {len(window)} sessions</div></div>
</div>
<section class="card"><h2>Latest scan</h2>
<p class="note">Screen: close $1–$30 and up ≥ 50% over 5 or 21 sessions. Float and market cap are not
filtered (no free point-in-time source), so this list is deliberately wide. Sorted VETO first, then by 5-session run-up.
The dot on each price line is the scan session.</p>
<div class="scroll"><table><thead><tr><th>Symbol</th><th>Layer 1</th><th class="num">Close</th>
<th class="num">5-session</th><th class="num">21-session</th><th class="num">Vol × 30d</th><th>Last {SPARK_SESSIONS} sessions</th>
<th>Flags</th><th>Why</th></tr></thead><tbody>{''.join(body) or "<tr><td colspan='9' class='muted'>No hits.</td></tr>"}</tbody></table></div>
{more}</section>
<section class="card"><h2>Hits per session</h2>{hits_chart([(d, per[d]) for d in window])}
<p class="note">N = {sum(per.values())} hits over {len(window)} scanned sessions. Hover a bar for its date and count.</p></section>
<section class="card"><h2>Does Layer 1 call them? (outcomes)</h2>
<p class="note">Each episode is labelled once 30 sessions have passed: <i>collapsed</i> means it rose ≥ 100% in ≤ 10
sessions and then fell ≥ 70% within 20 (PLAN.md L1.2). Recall = collapsed episodes with a VETO logged by the peak.
False-positive rate = episodes that did not collapse but got a VETO. <b>Forward</b> rows were logged at the time and
are the honest test; <b>backfilled</b> rows were scanned later from history.</p>
<div class="scroll"><table><thead><tr><th></th><th class="num">Episodes</th><th class="num">Collapsed</th>
<th class="num">No collapse</th><th class="num">Pending</th><th class="num">Recall</th><th class="num">FP rate</th><th></th></tr></thead>
<tbody>{metric_row('Forward', fwd['forward'])}{metric_row('Backfilled', fwd['backfilled'])}</tbody></table></div></section>
<p class="note">{_e(GATE)} Prices are end-of-day and update once after the close; the other daily refreshes pick up new SEC
filings and catch up missed sessions. {_e(storage)}. {_e(NOTE)} Not investment advice. Private page — do not share the link.</p>
</main></body></html>"""
    return page


def write_page(store: Store, directory: Path, now: dt.datetime | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / PAGE_NAME
    tmp = p.with_suffix(".tmp")
    tmp.write_text(build_page(store, now))
    tmp.replace(p)            # atomic: a reader never sees half a page
    return p
