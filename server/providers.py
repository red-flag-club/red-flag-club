"""Daily-bar sources. Each returns normalised rows {date, o, h, l, c, v,
raw_c, split_factor} for [start, end], split-adjusted where the source can
adjust (research R1). HTTP is stdlib urllib, injectable for tests.

None of these talk to a brokerage. The brokerage data path is the
PayloadProvider, which only reads files an agent already saved.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Callable, Protocol


class NoData(LookupError):
    """The source does not know this symbol."""


class RateLimited(RuntimeError):
    """The free-tier limit is reached; try later."""


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    name: str

    def daily(self, symbol: str, start: str, end: str) -> list[dict]: ...


class RateLimiter:
    """At most `calls` per `per_seconds`, sliding window. Never sleeps longer
    than `max_wait`; beyond that it raises RateLimited so a request is
    answered from cache or refused, not left hanging."""

    def __init__(self, calls: int, per_seconds: float, max_wait: float = 2.0,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.calls, self.per, self.max_wait = calls, per_seconds, max_wait
        self.clock, self.sleep = clock, sleep
        self.hits: deque[float] = deque()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            now = self.clock()
            while self.hits and now - self.hits[0] >= self.per:
                self.hits.popleft()
            if len(self.hits) >= self.calls:
                wait = self.per - (now - self.hits[0])
                if wait > self.max_wait:
                    raise RateLimited(f"limit of {self.calls} calls per {self.per:g}s reached")
                self.sleep(wait)
                self.hits.popleft()
            self.hits.append(self.clock())


Fetch = Callable[[urllib.request.Request], tuple[int, bytes]]


def urllib_fetch(req: urllib.request.Request, timeout: float = 20.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""
    except urllib.error.URLError as e:
        raise ProviderError(f"network error: {e.reason}") from e


def _status(code: int, symbol: str) -> None:
    if code == 404:
        raise NoData(symbol)
    if code == 429:
        raise RateLimited("provider returned 429")
    if code in (401, 403):
        raise ProviderError(f"provider refused the API key ({code})")
    if code >= 400:
        raise ProviderError(f"provider error {code}")


class TiingoProvider:
    """Tiingo end-of-day. Free tier ~50 requests/hour, 500 unique symbols a
    month (check the pricing page). Full history."""

    name = "tiingo"
    BASE = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"

    def __init__(self, key: str, fetch: Fetch = urllib_fetch, limiter: RateLimiter | None = None):
        self.key, self.fetch = key, fetch
        self.limiter = limiter or RateLimiter(45, 3600)

    def daily(self, symbol: str, start: str, end: str) -> list[dict]:
        self.limiter.acquire()
        q = urllib.parse.urlencode({"startDate": start, "endDate": end, "format": "json"})
        req = urllib.request.Request(self.BASE.format(symbol=urllib.parse.quote(symbol.lower())) + "?" + q,
                                     headers={"Authorization": f"Token {self.key}",
                                              "Content-Type": "application/json"})
        code, body = self.fetch(req)
        _status(code, symbol)
        rows = json.loads(body or b"[]")
        if not isinstance(rows, list):
            raise ProviderError(f"unexpected Tiingo response: {str(rows)[:120]}")
        return [{"date": r["date"][:10], "o": r.get("adjOpen"), "h": r.get("adjHigh"), "l": r.get("adjLow"),
                 "c": r.get("adjClose"), "v": r.get("adjVolume") or 0, "raw_c": r.get("close"),
                 "split_factor": r.get("splitFactor") or 1.0} for r in rows]


class MassiveProvider:
    """Massive (ex-Polygon) free tier: 5 requests/minute, two years of
    history, end of day. api.polygon.io accepts the same keys."""

    name = "massive"
    BASE = "https://api.massive.com/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}"

    def __init__(self, key: str, fetch: Fetch = urllib_fetch, limiter: RateLimiter | None = None):
        self.key, self.fetch = key, fetch
        self.limiter = limiter or RateLimiter(5, 60, max_wait=15)

    def daily(self, symbol: str, start: str, end: str) -> list[dict]:
        self.limiter.acquire()
        url = self.BASE.format(symbol=urllib.parse.quote(symbol.upper()), start=start, end=end)
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(
            {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.key}))
        code, body = self.fetch(req)
        _status(code, symbol)
        data = json.loads(body or b"{}")
        rows = data.get("results") or []
        if not rows and data.get("resultsCount", 0) == 0 and data.get("status") not in ("OK", "DELAYED"):
            raise NoData(symbol)
        import datetime as dt
        return [{"date": dt.datetime.fromtimestamp(r["t"] / 1000, dt.timezone.utc).date().isoformat(),
                 "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r.get("v") or 0,
                 "raw_c": None, "split_factor": 1.0} for r in rows]


def parse_brokerage_payload(data) -> dict[str, list[dict]]:
    """Brokerage get_equity_historicals payload -> {symbol: rows}. Keeps the
    `interpolated` flag so clean_bars drops gap-fill (hard rule 5)."""
    while isinstance(data, dict) and isinstance(data.get("data") or data.get("result"), dict):
        data = data.get("data") or data.get("result")
    items = (data.get("results") or []) if isinstance(data, dict) else data
    out: dict[str, list[dict]] = {}
    for it in items or []:
        sym = (it.get("symbol") or "").upper() if isinstance(it, dict) else ""
        if not sym or it.get("interval", "day") != "day":
            continue
        out.setdefault(sym, []).extend(
            {"date": b["begins_at"][:10], "o": b.get("open_price"), "h": b.get("high_price"),
             "l": b.get("low_price"), "c": b.get("close_price"), "v": b.get("volume") or 0,
             "interpolated": bool(b.get("interpolated")), "raw_c": None, "split_factor": 1.0}
            for b in (it.get("bars") or it.get("historicals") or []))
    return out


class PayloadProvider:
    """Saved brokerage historicals payloads (*.json / *.txt) in a directory.
    Offline; used to seed the cache from data the project already has."""

    name = "brokerage-payload"

    def __init__(self, directory: Path):
        self.rows: dict[str, list[dict]] = {}
        for f in sorted(Path(directory).glob("*")):
            if f.suffix not in (".json", ".txt"):
                continue
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(data, list) and data and isinstance(data[0], dict) and "text" in data[0]:
                try:
                    data = json.loads(data[0]["text"])
                except json.JSONDecodeError:
                    continue
            for sym, rows in parse_brokerage_payload(data).items():
                self.rows.setdefault(sym, []).extend(rows)

    def daily(self, symbol: str, start: str, end: str) -> list[dict]:
        rows = self.rows.get(symbol.upper())
        if not rows:
            raise NoData(symbol)
        return [r for r in rows if start <= r["date"] <= end]


class FixtureProvider:
    """In-memory rows for tests and offline demos. Counts calls."""

    name = "fixture"

    def __init__(self, rows: dict[str, list[dict]] | None = None):
        self.rows = {k.upper(): v for k, v in (rows or {}).items()}
        self.calls: list[tuple[str, str, str]] = []
        self.rate_limited = False

    def daily(self, symbol: str, start: str, end: str) -> list[dict]:
        self.calls.append((symbol, start, end))
        if self.rate_limited:
            raise RateLimited("fixture rate limit")
        rows = self.rows.get(symbol.upper())
        if rows is None:
            raise NoData(symbol)
        return [r for r in rows if start <= r["date"] <= end]


def from_settings(s) -> Provider:
    if s.provider == "tiingo":
        return TiingoProvider(s.tiingo_key)
    if s.provider == "massive":
        return MassiveProvider(s.massive_key)
    if s.provider == "payload":
        return PayloadProvider(s.payload_dir)
    return FixtureProvider(seed_fixtures())


def seed_fixtures() -> dict[str, list[dict]]:
    """Repo data for PD_PROVIDER=fixture: the L1.3 seed events (RYDE, RETO),
    one row set per symbol. The real events exist only in the private repo;
    elsewhere the synthetic ones (scripts/make_synthetic.py) stand in."""
    from server import ROOT
    rows: dict[str, dict[str, dict]] = {}
    p = ROOT / "data" / "events" / "events_seed.jsonl"
    if not p.exists() or os.environ.get("PD_FIXTURES") == "synthetic":
        p = ROOT / "tests" / "fixtures" / "synthetic" / "events_seed.jsonl"
    if p.exists():
        for line in p.read_text().splitlines():
            e = json.loads(line)
            for d, o, h, l, c, v in e["bars"]:
                rows.setdefault(e["symbol"], {})[d] = {"date": d, "o": o, "h": h, "l": l, "c": c, "v": v,
                                                       "raw_c": None, "split_factor": 1.0}
    return {s: [r[d] for d in sorted(r)] for s, r in rows.items()}
