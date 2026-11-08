"""Outcome labels for logged symbols and forward metrics (spec 004, R4).

The label is the L1.2 COLLAPSE EVENT from src/collapse_events.find_runs —
shared code, not a copy. It is decided only once 30 sessions after the
symbol was first logged exist, and it never feeds a verdict: it is what the
verdicts are scored against.
"""

from __future__ import annotations

from src.collapse_events import COLLAPSE_MAX_SESSIONS, RAMP_MAX_SESSIONS, find_runs

from server.bars import to_bars
from server.store import Store

PRE = RAMP_MAX_SESSIONS                       # sessions before first logged that a ramp may start in
POST = RAMP_MAX_SESSIONS + COLLAPSE_MAX_SESSIONS   # 30: peak <= +10, trough window <= +30
NEW_EPISODE_GAP = 20                          # sessions without a log row before a new episode
MIN_N = 30                                    # below this, metrics are "too few to judge"


def episodes(store: Store) -> list[dict]:
    """One entry per episode: {symbol, first_logged, backfilled, verdict
    (first day), rows: [(session, verdict), ...]}."""
    sessions = store.sessions_all()          # pruned sessions still count for the 20-session gap
    idx = {d: i for i, d in enumerate(sessions)}
    last: dict[str, int] = {}
    current: dict[str, dict] = {}
    out = []
    for r in store.scan_rows():
        i = idx.get(r["session"])
        if i is None:
            continue
        prev = last.get(r["symbol"])
        if prev is None or i - prev > NEW_EPISODE_GAP:
            current[r["symbol"]] = {"symbol": r["symbol"], "first_logged": r["session"],
                                    "backfilled": r["backfilled"], "verdict": r["verdict"], "rows": []}
            out.append(current[r["symbol"]])
        current[r["symbol"]]["rows"].append((r["session"], r["verdict"]))
        last[r["symbol"]] = i
    return out


def label_outcomes(store: Store, as_of: str) -> int:
    """Decide every pending episode that now has POST sessions after it.
    Returns how many were decided this call. Decided labels are final."""
    sessions = [d for d in store.sessions_all() if d <= as_of]
    idx = {d: i for i, d in enumerate(sessions)}
    decided = {(o["symbol"], o["first_logged"]) for o in store.outcomes() if o["label"] != "pending"}
    n = 0
    for e in episodes(store):
        key = (e["symbol"], e["first_logged"])
        if key in decided or e["first_logged"] not in idx:
            continue
        i = idx[e["first_logged"]]
        if i + POST >= len(sessions):
            store.put_outcome({"symbol": e["symbol"], "first_logged": e["first_logged"], "label": "pending"})
            continue
        lo, hi = sessions[max(0, i - PRE)], sessions[i + POST]
        rows = [r for r in store.market_history(hi, POST + PRE + 1, symbols=[e["symbol"]]).get(e["symbol"], [])
                if lo <= r["date"] <= hi]
        bars = to_bars(rows)
        window_peak_hi = sessions[i + RAMP_MAX_SESSIONS]
        runs = [r for r in find_runs(e["symbol"], bars) if lo <= r.peak_date <= window_peak_hi]
        hit = next((r for r in runs if r.collapsed), None) or (runs[0] if runs else None)
        after = [b for b in bars if b.date >= e["first_logged"]]
        peak = max(after, key=lambda b: b.c) if after else None
        store.put_outcome({
            "symbol": e["symbol"], "first_logged": e["first_logged"],
            "label": "collapsed" if hit and hit.collapsed else "no_collapse",
            "peak_date": hit.peak_date if hit else (peak.date if peak else None),
            "peak": hit.peak_price if hit else (peak.c if peak else None),
            "drawdown": round(hit.drawdown_pct, 4) if hit and hit.drawdown_pct is not None else None,
            "decided_on": hi})
        n += 1
    return n


def _vetoed(e: dict, o: dict) -> bool:
    """A VETO logged on any session up to the peak (collapsed: in time to
    matter) or anywhere in the episode (no collapse: a false alarm)."""
    until = o["peak_date"] if o["label"] == "collapsed" and o["peak_date"] else "9999-12-31"
    return any(v == "VETO" and d <= until for d, v in e["rows"])


def forward_metrics(store: Store) -> dict:
    """How the logged verdicts compare with outcomes. Forward rows (logged
    at the time) and backfilled rows are kept apart."""
    first = {(e["symbol"], e["first_logged"]): e for e in episodes(store)}
    out = {}
    for name, want_backfilled in (("forward", False), ("backfilled", True)):
        rows = [(first[(o["symbol"], o["first_logged"])], o) for o in store.outcomes()
                if (o["symbol"], o["first_logged"]) in first
                and first[(o["symbol"], o["first_logged"])]["backfilled"] == want_backfilled]
        pos = [e for e, o in rows if o["label"] == "collapsed"]
        neg = [e for e, o in rows if o["label"] == "no_collapse"]
        pend = [e for e, o in rows if o["label"] == "pending"]
        veto_pos = sum(_vetoed(e, o) for e, o in rows if o["label"] == "collapsed")
        veto_neg = sum(_vetoed(e, o) for e, o in rows if o["label"] == "no_collapse")
        out[name] = {
            "episodes": len(rows), "pending": len(pend), "collapsed": len(pos), "no_collapse": len(neg),
            "recall": round(veto_pos / len(pos), 3) if pos else None,
            "fp_rate": round(veto_neg / len(neg), 3) if neg else None,
            "veto_collapsed": veto_pos, "veto_no_collapse": veto_neg,
            "enough": len(pos) >= MIN_N and len(neg) >= MIN_N,
        }
    return out
