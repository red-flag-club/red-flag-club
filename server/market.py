"""Whole-market daily sessions for the Layer 2 scan (spec 004, research R1).

A MarketSource returns every US stock's bar for one session, and the splits
that executed that session. Nothing here talks to a brokerage; the brokerage
payload path only reads payload files an agent already saved.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Protocol

from server.providers import (Fetch, NoData, PayloadProvider, ProviderError, RateLimiter, _status,
                              urllib_fetch)


class MarketSource(Protocol):
    name: str

    def session(self, date: str) -> list[dict]:
        """[{symbol, o, h, l, c, v}] for `date`; [] if not published (yet)."""
        ...

    def splits(self, start: str, end: str) -> list[dict]:
        """[{symbol, date, ratio}] executed in [start, end] (ratio = new/old shares)."""
        ...


class MassiveGrouped:
    """Massive (ex-Polygon) grouped daily: one call per session for the
    whole US stock market. Whether the free plan includes it is unverified
    (research R1); check_source() settles it with the owner's key."""

    name = "massive-grouped"
    BASE = "https://api.massive.com"

    def __init__(self, key: str, fetch: Fetch = urllib_fetch, limiter: RateLimiter | None = None):
        self.key, self.fetch = key, fetch
        # backfill waits rather than failing: 5 calls/min means ~12 s between calls
        self.limiter = limiter or RateLimiter(5, 60, max_wait=65)
        self.splits_available = True

    def _get(self, path: str, params: dict) -> dict:
        self.limiter.acquire()
        q = urllib.parse.urlencode({**params, "apiKey": self.key})
        code, body = self.fetch(urllib.request.Request(f"{self.BASE}{path}?{q}"))
        _status(code, path)
        return json.loads(body or b"{}")

    def session(self, date: str) -> list[dict]:
        try:
            data = self._get(f"/v2/aggs/grouped/locale/us/market/stocks/{date}", {"adjusted": "true"})
        except NoData:
            return []
        return [{"symbol": r["T"], "o": r.get("o"), "h": r.get("h"), "l": r.get("l"), "c": r.get("c"),
                 "v": r.get("v") or 0} for r in data.get("results") or [] if r.get("T")]

    def splits(self, start: str, end: str) -> list[dict]:
        """One call for the whole range (first page of up to 1,000; a
        backfill range rarely has more small-cap splits than that)."""
        if not self.splits_available:
            return []
        try:
            data = self._get("/v3/reference/splits", {"execution_date.gte": start, "execution_date.lte": end,
                                                       "limit": 1000})
        except (ProviderError, NoData):
            self.splits_available = False      # not on this plan: fall back to possible_split flags
            return []
        out = []
        for r in data.get("results") or []:
            frm, to = r.get("split_from") or 0, r.get("split_to") or 0
            if r.get("ticker") and frm and to and r.get("execution_date"):
                out.append({"symbol": r["ticker"], "date": r["execution_date"], "ratio": to / frm})
        return out


class PayloadSnapshots:
    """Sessions assembled from saved brokerage historicals payloads (the
    fallback when grouped daily is not on the free plan). Keeps
    `interpolated` for the caller's hygiene step."""

    name = "brokerage-payload"

    def __init__(self, directory: Path):
        self.by_date: dict[str, list[dict]] = {}
        for sym, rows in PayloadProvider(directory).rows.items():
            for r in rows:
                self.by_date.setdefault(r["date"], []).append({**r, "symbol": sym})

    def session(self, date: str) -> list[dict]:
        return list(self.by_date.get(date, []))

    def splits(self, start: str, end: str) -> list[dict]:
        return []


class FixtureSnapshots:
    """In-memory sessions from {symbol: [rows]} (tests, --fixture demo)."""

    name = "fixture"

    def __init__(self, rows_by_symbol: dict[str, list[dict]], splits: list[dict] | None = None):
        self.by_date: dict[str, list[dict]] = {}
        for sym, rows in rows_by_symbol.items():
            for r in rows:
                self.by_date.setdefault(r["date"], []).append({**r, "symbol": sym.upper()})
        self._splits = splits or []
        self.calls: list[str] = []

    def session(self, date: str) -> list[dict]:
        self.calls.append(date)
        return list(self.by_date.get(date, []))

    def splits(self, start: str, end: str) -> list[dict]:
        return [s for s in self._splits if start <= s["date"] <= end]


def from_settings(s) -> MarketSource | None:
    if s.scan_source == "massive":
        return MassiveGrouped(s.massive_key)
    if s.scan_source == "payload":
        return PayloadSnapshots(s.payload_dir)
    if s.scan_source == "fixture":
        from server.providers import seed_fixtures
        return FixtureSnapshots(seed_fixtures())
    return None


def check_source(src: MarketSource, date: str) -> str:
    """One call, human-readable verdict on whether the source works."""
    try:
        rows = src.session(date)
    except ProviderError as e:
        return f"not usable: {e} (for Massive a 403 means grouped daily is not on your plan)"
    if not rows:
        return f"reachable, but no rows for {date} (holiday or not yet published) — try an earlier session"
    return f"ok: {len(rows)} symbols for {date} from {src.name}"
