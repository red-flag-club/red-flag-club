"""Layer 2 scan log (spec 004; PLAN.md L2.1-L2.2).

refresh() is idempotent: it loads missing sessions, screens every loaded
session not yet screened (in date order, each with data up to its own date
only), appends hits to the append-only scan_log with that day's Layer 1
verdict, refreshes SEC filings for recent hits, labels outcomes and rebuilds
the dashboard.
"""

from __future__ import annotations

import datetime as dt
import logging
import statistics as st
import threading
from typing import Callable, Sequence

import server  # noqa: F401
import check_ticker as K

from server.bars import clean_bars, suspect_bad_prints, to_bars
from server.data import DataService, last_session
from server.market import MarketSource
from server.providers import ProviderError, RateLimited
from server.store import Store, _now

log = logging.getLogger("pd-defence.scan")

# PLAN.md L2.1 with free inputs (research R2)
PRICE_MIN, PRICE_MAX = 1.0, 30.0
RUNUP_5, RUNUP_21 = 0.50, 0.50
REL_VOL_LOOKBACK = 30
WARMUP_SESSIONS = 22          # a session is screened once this many sessions precede it
SCREEN_SESSIONS = 32          # history the screen reads (21-session run-up + 30-session volume)
CHECK_SESSIONS = 60           # check() at scan time: VETO rules need <= 11 bars (spec 005)
BACKFILL_SESSIONS = 60        # first run: 22 warm-up + ~38 scanned (~12 min at 5 calls/min)
MARKET_KEEP_SESSIONS = 70     # rolling window kept on disk: screen 32, outcomes 41, sparklines 60
BACKFILLED_AFTER = 5          # sessions older than this when logged are marked backfilled
SPLIT_JUMP = 3.0
EMPTY_TRIES = 3               # an empty recent weekday becomes `no_session` after this many tries
RECENT_EMPTY_RETRY = 3        # empty days older than this many sessions are `no_session` at once
BENCHMARK = "SPY"

_lock = threading.Lock()


def weekdays(start: str, end: str) -> list[str]:
    d, e, out = dt.date.fromisoformat(start), dt.date.fromisoformat(end), []
    while d <= e:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _weekdays_back(end: str, n: int) -> str:
    d = dt.date.fromisoformat(end)
    while n > 0:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d.isoformat()


# ---------------------------------------------------------------- screen (pure)

def _run_up(rows: Sequence[dict], n: int, start: str | None) -> float | None:
    """Close over the lowest close in the window: the last n+1 market
    sessions when `start` (the first of them) is given, else the symbol's own
    last n+1 bars."""
    w = [r["c"] for r in rows if r["date"] >= start] if start else [r["c"] for r in rows[-(n + 1):]]
    if len(w) < 2:
        return None
    lo = min(w)
    return w[-1] / lo - 1 if lo > 0 else None


def _possible_split(c: Sequence[float]) -> bool:
    """A one-session jump of >= 3x (or <= 1/3) that holds for the next two
    sessions. Flag only: a real pump can look the same."""
    for i in range(1, len(c) - 2):
        j = c[i] / c[i - 1]
        if j >= SPLIT_JUMP and min(c[i + 1:i + 3]) / c[i - 1] >= SPLIT_JUMP * 0.67:
            return True
        if j <= 1 / SPLIT_JUMP and max(c[i + 1:i + 3]) / c[i - 1] <= 1 / (SPLIT_JUMP * 0.67):
            return True
    return False


def screen(history: dict[str, list[dict]], session: str,
           splits: dict[str, list[str]] | None = None, starts: dict[int, str] | None = None) -> list[dict]:
    """Hits for `session`. `history` holds rows dated <= session (asserted).
    Only symbols with a bar on `session` are screened. `starts` gives the
    first market session of the 5- and 21-session windows."""
    starts = starts or {}
    hits = []
    for sym, rows in history.items():
        if not rows or rows[-1]["date"] != session:
            continue
        assert rows[-1]["date"] <= session and all(r["date"] <= session for r in rows[-3:])
        flags = []
        cut = max((d for d in (splits or {}).get(sym, []) if d <= session), default=None)
        if cut:
            if any(r["date"] < cut for r in rows):
                flags.append("split")
            rows = [r for r in rows if r["date"] >= cut]
        rows = rows[-SCREEN_SESSIONS:]
        c, v = [r["c"] for r in rows], [r["v"] for r in rows]
        close = c[-1]
        if not (PRICE_MIN <= close <= PRICE_MAX):
            continue
        r5, r21 = _run_up(rows, 5, starts.get(5)), _run_up(rows, 21, starts.get(21))
        reasons = []
        if r5 is not None and r5 >= RUNUP_5:
            reasons.append("5-session run-up")
        if r21 is not None and r21 >= RUNUP_21:
            reasons.append("21-session run-up")
        if not reasons:
            continue
        base = v[-(REL_VOL_LOOKBACK + 1):-1]
        rel = (v[-1] / st.mean(base)) if len(base) >= REL_VOL_LOOKBACK and st.mean(base) > 0 else None
        if len(c) < WARMUP_SESSIONS:
            flags.append("short_history")
        if not cut and _possible_split(c):
            flags.append("possible_split")
        if suspect_bad_prints(to_bars(rows)):
            flags.append("bad_print")
        hits.append({"symbol": sym, "close": close, "ret_1": round(c[-1] / c[-2] - 1, 4) if len(c) > 1 else None,
                     "ret_5": round(r5, 4) if r5 is not None else None,
                     "ret_21": round(r21, 4) if r21 is not None else None,
                     "rel_vol_30": round(rel, 2) if rel is not None else None,
                     "reason": " + ".join(reasons), "flags": ",".join(flags)})
    return sorted(hits, key=lambda h: h["symbol"])


# ---------------------------------------------------------------- load sessions

def load_sessions(store: Store, source: MarketSource, until: str, backfill: int = BACKFILL_SESSIONS) -> dict:
    """Fetch every weekday in range not yet loaded. Stops cleanly at a rate
    limit; the next run resumes."""
    known = store.sessions_all()                  # loaded or pruned
    start = min(known[0], _weekdays_back(until, backfill)) if known else _weekdays_back(until, backfill)
    settled = _weekdays_back(until, RECENT_EMPTY_RETRY)
    todo = [d for d in weekdays(start, until) if store.session_status(d) not in ("loaded", "no_session", "pruned")]
    got, status = 0, "ok"
    if todo:
        try:
            store.put_splits(source.splits(todo[0], until))
        except (RateLimited, ProviderError) as e:
            log.warning("splits unavailable: %s", e)
    for d in todo:
        try:
            raw = source.session(d)
        except RateLimited as e:
            status = f"partial: rate limit at {d} ({e})"
            break
        except ProviderError as e:
            status = f"partial: {e} at {d}"
            break
        if not raw:
            # an old empty day is a holiday or before the data starts; a recent
            # one may simply not be published yet, so it is retried
            tries = store.session_tries(d)
            store.mark_session(d, "no_session" if d < settled or (d < until and tries + 1 >= EMPTY_TRIES)
                               else "empty")
            continue
        clean = []
        dropped = 0
        by_sym: dict[str, list[dict]] = {}
        for r in raw:
            by_sym.setdefault(r["symbol"].upper(), []).append({**r, "date": d})
        for sym, rows in by_sym.items():
            kept, stats = clean_bars(rows, as_of=d)
            dropped += stats.dropped
            clean += [{**k, "symbol": sym} for k in kept]
        store.put_session(d, clean, source.name, dropped)
        got += 1
    return {"requested": len(todo), "loaded": got, "status": status}


# ---------------------------------------------------------------- log

def log_session(store: Store, ds: DataService, session: str, *, backfilled: bool) -> int:
    """Screen one session and append its hits with the Layer 1 verdict as of
    that session. Everything read is dated <= session."""
    recent = store.recent_sessions(session, 22)
    starts = {5: recent[-6] if len(recent) >= 6 else recent[0], 21: recent[0]}
    cands = store.screen_candidates(session, starts[5], starts[21], PRICE_MIN, PRICE_MAX, RUNUP_5, RUNUP_21)
    splits = store.splits_until(session)
    hist = store.market_history(session, SCREEN_SESSIONS, symbols=cands) if cands else {}
    hits = screen(hist, session, splits, starts)
    rows = []
    if hits:
        syms = [h["symbol"] for h in hits]
        full = store.market_history(session, CHECK_SESSIONS, symbols=syms + [BENCHMARK])
        bench = to_bars(full.get(BENCHMARK, [])) or None
        for h in hits:
            bars_rows = full.get(h["symbol"], [])
            cut = max((d for d in splits.get(h["symbol"], []) if d <= session), default=None)
            if cut:
                bars_rows = [r for r in bars_rows if r["date"] >= cut]
            filings, _ = ds.filings(h["symbol"], session)
            # position=0: the scan sizes nothing, so no position-size caution
            r = K.check(h["symbol"], to_bars(bars_rows), session, filings=filings, benchmark=bench, position=0.0)
            reasons = r.get("vetoes", []) + r.get("cautions", []) + r.get("reasons", [])
            rows.append({**h, "session": session, "logged_at": _now(), "backfilled": backfilled,
                         "verdict": r["verdict"], "reasons": "; ".join(reasons)})
    n = store.log_hits(rows)
    store.mark_scanned(session)
    return n


COMPACT_EVERY_DAYS = 7


def _maybe_compact(store: Store, now: dt.datetime) -> None:
    last = store.get_meta("compacted_on")
    today = now.date()
    if last and (today - dt.date.fromisoformat(last)).days < COMPACT_EVERY_DAYS:
        return
    sizes = store.compact()
    store.set_meta("compacted_on", today.isoformat())
    if sizes:
        log.info("compacted database %.1f MB -> %.1f MB", sizes[0] / 1e6, sizes[1] / 1e6)


def refresh(store: Store, ds: DataService, source: MarketSource, *, now: dt.datetime | None = None,
            backfill: int = BACKFILL_SESSIONS, on_done: Callable[[], None] | None = None) -> dict:
    """The scheduled job. Returns a summary; never raises on data problems."""
    if not _lock.acquire(blocking=False):
        return {"status": "skipped: a refresh is already running"}
    try:
        now = now or ds.now()
        until = last_session(now)
        load = load_sessions(store, source, until, backfill)
        loaded = store.sessions("loaded")
        done = store.scanned_sessions()
        recent_cut = _weekdays_back(until, BACKFILLED_AFTER)
        scanned = hits = 0
        for i, s in enumerate(loaded):
            if i < WARMUP_SESSIONS or s in done:
                continue
            hits += log_session(store, ds, s, backfilled=s < recent_cut)
            scanned += 1
        # new SEC filings for recent hits (dilution 8-Ks/6-Ks land intraday)
        for sym in sorted({r["symbol"] for r in store.scan_rows(since=recent_cut)}):
            ds.filings(sym, until)
        from server.outcomes import label_outcomes
        labelled = label_outcomes(store, until)
        pruned = store.prune_market(MARKET_KEEP_SESSIONS)      # after labelling, which reads 41 sessions
        ds.prune()
        _maybe_compact(store, now)
        status = load["status"]
        store.log_run(scanned, hits, status)
        if on_done:
            on_done()
        out = {"status": status, "sessions_loaded": load["loaded"], "sessions_scanned": scanned,
               "hits": hits, "outcomes_decided": labelled, "sessions_pruned": pruned, "last_session": until}
        log.info("refresh %s", out)
        return out
    finally:
        _lock.release()
