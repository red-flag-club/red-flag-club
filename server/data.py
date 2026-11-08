"""Cache-first data access. Every read used for a verdict is cut at as_of
(constitution II); the store's queries enforce it, and check() re-checks.
"""

from __future__ import annotations

import datetime as dt
from collections import OrderedDict
from typing import Callable
from zoneinfo import ZoneInfo

from server.bars import clean_bars
from server.providers import NoData, Provider, ProviderError, RateLimited
from server.store import Store, _now

ET = ZoneInfo("America/New_York")
LOOKBACK_DAYS = 430            # ~14 months: 252 sessions for 52w/200-day plus slack
NO_DATA_TTL = dt.timedelta(hours=24)
FILINGS_TTL = dt.timedelta(hours=24)
FETCH_PAD_DAYS = 365          # one call fetches an extra year, so nearby as_of dates are cache hits
CLOSE_SETTLED = dt.time(16, 30)   # daily bars are final a little after the close

# Retention (spec 005): only bars a current check needs are written to disk.
RECENT_DAYS = 60              # as_of within this many days of the last session uses the disk cache
CACHE_DAYS = LOOKBACK_DAYS + RECENT_DAYS   # nothing older than this is stored
IDLE_DAYS = 30                # symbols not looked up for this long are evicted
EPHEMERAL_ENTRIES = 32        # in-memory ranges for historical questions (gone on restart)
PRUNE_EVERY = dt.timedelta(hours=24)


class EphemeralCache:
    """Historical ranges fetched for one answer: memory only, LRU."""

    def __init__(self, size: int = EPHEMERAL_ENTRIES):
        self.size, self.items = size, OrderedDict()

    def get(self, symbol: str, start: str, end: str):
        e = self.items.get(symbol)
        if e and e["start"] <= start and e["end"] >= end:
            self.items.move_to_end(symbol)
            return e
        return None

    def put(self, symbol: str, entry: dict) -> None:
        self.items[symbol] = entry
        self.items.move_to_end(symbol)
        while len(self.items) > self.size:
            self.items.popitem(last=False)


class DataUnavailable(RuntimeError):
    """Not cached and the provider can't be asked right now."""


class FutureDate(ValueError):
    pass


def et_now() -> dt.datetime:
    return dt.datetime.now(ET)


def last_session(now: dt.datetime) -> str:
    """Last weekday whose close has settled (holidays are not modelled; a
    holiday just yields no bar)."""
    d = now.date() if now.time() >= CLOSE_SETTLED else now.date() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d.isoformat()


class DataService:
    def __init__(self, store: Store, provider: Provider, sec=None, *,
                 now: Callable[[], dt.datetime] = et_now, today_ttl_min: int = 240):
        self.store, self.provider, self.sec = store, provider, sec
        self.now = now
        self.today_ttl = dt.timedelta(minutes=today_ttl_min)
        self.ephemeral = EphemeralCache()
        self._pruned_at: dt.datetime | None = None

    # ------------------------------------------------------------ dates
    @property
    def today(self) -> str:
        return self.now().date().isoformat()

    def resolve_as_of(self, as_of: str | None) -> str:
        if as_of is None:
            return last_session(self.now())
        try:
            d = dt.date.fromisoformat(as_of)
        except ValueError as e:
            raise ValueError(f"as_of must be YYYY-MM-DD, got {as_of!r}") from e
        if d.isoformat() > self.today:
            raise FutureDate(f"{as_of} is in the future")
        return d.isoformat()

    # ------------------------------------------------------------ retention
    def window_start(self) -> str:
        """Oldest date the disk cache holds."""
        return (dt.date.fromisoformat(last_session(self.now())) - dt.timedelta(days=CACHE_DAYS)).isoformat()

    def prune(self) -> dict:
        self._pruned_at = _now()
        return self.store.prune_bars(self.window_start(), _now() - dt.timedelta(days=IDLE_DAYS))

    def maybe_prune(self) -> None:
        if self._pruned_at is None or _now() - self._pruned_at > PRUNE_EVERY:
            self.prune()

    def _fetch_ephemeral(self, symbol: str, start: str) -> dict:
        """[start, last session] from the provider, cleaned, kept in memory
        only. One call serves both the verdict (cut at as_of by the caller)
        and the hindsight of was_i_pumped."""
        end = last_session(self.now())
        hit = self.ephemeral.get(symbol, start, end)
        if hit:
            return hit
        cov = self.store.coverage(symbol)
        if cov and cov["status"] == "no_data" and _now() - cov["fetched_at"] < NO_DATA_TTL:
            raise NoData(symbol)
        lo = (dt.date.fromisoformat(start) - dt.timedelta(days=FETCH_PAD_DAYS)).isoformat()
        try:
            raw = self.provider.daily(symbol, lo, end)       # padded: nearby dates are memory hits
        except NoData:
            self.store.log_call(self.provider.name, symbol, "no_data")
            self.store.set_coverage(symbol, None, None, self.provider.name, "no_data")
            raise
        except (RateLimited, ProviderError) as e:
            self.store.log_call(self.provider.name, symbol, type(e).__name__)
            raise DataUnavailable(f"{symbol}: {e}; history not cached — try later") from e
        self.store.log_call(self.provider.name, symbol, "ok")
        rows, stats = clean_bars(raw)
        if not rows:
            raise NoData(symbol)
        entry = {"start": lo, "end": end, "rows": rows, "dropped": stats.dropped,
                 "source": self.provider.name}
        self.ephemeral.put(symbol, entry)
        return entry

    # ------------------------------------------------------------ bars
    def _covered(self, cov: dict | None, start: str, end: str) -> bool:
        if not cov or cov["status"] != "ok":
            return False
        if cov["first_date"] > start or cov["last_date"] < end:
            return False
        if end >= last_session(self.now()) and _now() - cov["fetched_at"] > self.today_ttl:
            return False          # today's bar may have been revised or appeared since
        return True

    def ensure(self, symbol: str, start: str, end: str) -> dict:
        """Make the cache cover [start, end]; returns the coverage row.
        One provider call fetches the union of old and new ranges."""
        end = min(end, last_session(self.now()))
        cov = self.store.coverage(symbol)
        if cov and cov["status"] == "no_data" and _now() - cov["fetched_at"] < NO_DATA_TTL:
            raise NoData(symbol)
        if self._covered(cov, start, end):
            return cov
        pad = max((dt.date.fromisoformat(start) - dt.timedelta(days=FETCH_PAD_DAYS)).isoformat(),
                  self.window_start())               # never fetch-and-store before the window
        lo = min(pad, cov["first_date"]) if cov and cov["status"] == "ok" else pad
        hi = max(end, cov["last_date"]) if cov and cov["status"] == "ok" else end
        try:
            raw = self.provider.daily(symbol, lo, hi)
        except NoData:
            self.store.log_call(self.provider.name, symbol, "no_data")
            self.store.set_coverage(symbol, None, None, self.provider.name, "no_data")
            raise
        except (RateLimited, ProviderError) as e:
            self.store.log_call(self.provider.name, symbol, type(e).__name__)
            if cov and cov["status"] == "ok" and cov["first_date"] <= start and cov["last_date"] >= end:
                return cov        # stale but covering: better than refusing
            raise DataUnavailable(f"{symbol}: {e}; not cached — try later") from e
        self.store.log_call(self.provider.name, symbol, "ok")
        rows, stats = clean_bars(raw)
        if not rows:
            self.store.set_coverage(symbol, None, None, self.provider.name, "no_data", stats.dropped)
            raise NoData(symbol)
        self.store.put_bars(symbol, rows, self.provider.name)
        self.store.set_coverage(symbol, lo, hi, self.provider.name, "ok", stats.dropped)
        return self.store.coverage(symbol)

    def bars(self, symbol: str, as_of: str, lookback_days: int = LOOKBACK_DAYS) -> tuple[list[dict], dict]:
        """Clean rows dated (as_of - lookback, as_of], plus provenance.
        Recent questions use the disk cache; older ones are fetched and kept
        in memory only (spec 005)."""
        self.maybe_prune()
        start = (dt.date.fromisoformat(as_of) - dt.timedelta(days=lookback_days)).isoformat()
        if start < self.window_start():
            e = self._fetch_ephemeral(symbol, start)
            rows = [r for r in e["rows"] if start <= r["date"] <= as_of]
            stored = False
            cov = {"dropped": e["dropped"], "source": e["source"]}
        else:
            cov = self.ensure(symbol, start, as_of)
            self.store.touch(symbol)
            rows = self.store.bars(symbol, start, as_of)
            stored = True
        assert all(r["date"] <= as_of for r in rows)
        return rows, {"bars": len(rows), "dropped_on_fetch": cov.get("dropped") or 0,
                      "source": cov.get("source"), "adjusted": cov.get("source") in ("tiingo", "massive"),
                      "stored": stored}

    def hindsight(self, symbol: str, after: str) -> list[dict]:
        """Bars strictly after `after`, up to the last session. Outcome data
        only; callers must never feed it to a verdict."""
        end = last_session(self.now())
        if after < self.window_start():
            e = self._fetch_ephemeral(symbol, after)
            return [{k: r[k] for k in ("date", "o", "h", "l", "c", "v")} for r in e["rows"]
                    if after < r["date"] <= end]
        if after < end:
            self.ensure(symbol, after, end)
        return self.store.bars_after(symbol, after, end)

    # ------------------------------------------------------------ filings
    def filings(self, symbol: str, as_of: str) -> tuple[list[dict], str]:
        """Filing index entries filed <= as_of, and a status string. Unknown
        is returned as [] so check() scores filer type as unknown."""
        if self.sec is None:
            return [], "SEC not configured (set PD_SEC_CONTACT)"
        fc = self.store.filings_coverage(symbol)
        if not fc or _now() - fc["fetched_at"] > FILINGS_TTL:
            try:
                cik, rows = self.sec.filings(symbol)
                self.store.put_filings(symbol, cik, rows)
                self.store.log_call("sec", symbol, "ok")
            except NoData:
                self.store.put_filings(symbol, None, [], "no_cik")
                self.store.log_call("sec", symbol, "no_cik")
            except (RateLimited, ProviderError) as e:
                self.store.log_call("sec", symbol, type(e).__name__)
                if not fc:
                    return [], f"SEC unavailable ({e})"
            fc = self.store.filings_coverage(symbol)
        if fc["status"] == "no_cik":
            return [], "no SEC CIK for this symbol (OTC, renamed or delisted?)"
        return self.store.filings(symbol, as_of), "ok"
