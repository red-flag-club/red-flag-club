"""SEC EDGAR filing index (research R3). Free, no key; SEC requires a
User-Agent that identifies the requester and allows 10 requests/second.

The ticker map is today's: a renamed or delisted symbol may not resolve, and
then filing inputs are unknown (scored worst-case), never a pass.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.request

from server.providers import Fetch, NoData, ProviderError, RateLimiter, urllib_fetch

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"


class EdgarClient:
    def __init__(self, contact: str, fetch: Fetch = urllib_fetch, limiter: RateLimiter | None = None):
        if not contact or "@" not in contact:
            raise ValueError("SEC requires a contact e-mail in the User-Agent (PD_SEC_CONTACT)")
        self.ua = f"pd-defence {contact}"
        self.fetch = fetch
        self.limiter = limiter or RateLimiter(5, 1.0)
        self._ciks: dict[str, str] | None = None
        self._lock = threading.Lock()

    def _get(self, url: str):
        self.limiter.acquire()
        code, body = self.fetch(urllib.request.Request(url, headers={"User-Agent": self.ua,
                                                                     "Accept-Encoding": "identity"}))
        if code == 404:
            raise NoData(url)
        if code >= 400:
            raise ProviderError(f"SEC returned {code}")
        return json.loads(body)

    def cik(self, symbol: str) -> str:
        with self._lock:
            if self._ciks is None:
                data = self._get(TICKERS_URL)
                self._ciks = {v["ticker"].upper(): f"{int(v['cik_str']):010d}" for v in data.values()}
        c = self._ciks.get(symbol.upper())
        if not c:
            raise NoData(symbol)
        return c

    def filings(self, symbol: str) -> tuple[str, list[dict]]:
        """(cik, [{form, filed}]) — every filing in the submissions history."""
        cik = self.cik(symbol)
        sub = self._get(SUBMISSIONS_URL.format(name=f"CIK{cik}.json"))
        blocks = [sub.get("filings", {}).get("recent", {})]
        for extra in sub.get("filings", {}).get("files", []):
            blocks.append(self._get(SUBMISSIONS_URL.format(name=extra["name"])))
        out = []
        for b in blocks:
            for form, filed in zip(b.get("form", []), b.get("filingDate", [])):
                out.append({"form": form, "filed": filed})
        return cik, out


class FixtureSec:
    """Offline stand-in: {symbol: [{form, filed}]}."""

    def __init__(self, filings: dict[str, list[dict]] | None = None):
        self.data = {k.upper(): v for k, v in (filings or {}).items()}
        self.calls = 0

    def filings(self, symbol: str) -> tuple[str, list[dict]]:
        self.calls += 1
        if symbol.upper() not in self.data:
            raise NoData(symbol)
        return "0000000000", self.data[symbol.upper()]


def seed_filings() -> dict[str, list[dict]]:
    """data/l14/filings.json ({symbol: [[date, form], ...]}) as fixture input,
    or the public subset in tests/fixtures/synthetic/ where data/ is absent."""
    from server import ROOT
    p = ROOT / "data" / "l14" / "filings.json"
    if not p.exists() or os.environ.get("PD_FIXTURES") == "synthetic":
        p = ROOT / "tests" / "fixtures" / "synthetic" / "filings.json"
    if not p.exists():
        return {}
    return {s: [{"form": f, "filed": d} for d, f in rows] for s, rows in json.loads(p.read_text()).items()}
