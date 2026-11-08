"""Shared offline fixtures for the MCP server tests (no network, no keys)."""

import datetime as dt

from server.data import ET, DataService
from server.providers import FixtureProvider, seed_fixtures
from server.sec import FixtureSec, seed_filings
from server.store import Store

NOW = dt.datetime(2026, 10, 15, 18, 0, tzinfo=ET)     # after the close: last session 2026-10-15


def series(closes, start="2025-06-02", vol=1e6):
    """Weekday bars, one per close."""
    d, out = dt.date.fromisoformat(start), []
    for c in closes:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        out.append({"date": d.isoformat(), "o": c * 0.99, "h": c * 1.02, "l": c * 0.97, "c": c, "v": vol,
                    "raw_c": c, "split_factor": 1.0})
        d += dt.timedelta(days=1)
    return out


def make_ds(rows=None, filings=None, *, seed=True, now=NOW, path=":memory:"):
    data = seed_fixtures() if seed else {}
    data.update(rows or {})
    fil = seed_filings() if seed else {}
    fil.update(filings or {})
    prov = FixtureProvider(data)
    return DataService(Store(path), prov, FixtureSec(fil), now=lambda: now), prov
