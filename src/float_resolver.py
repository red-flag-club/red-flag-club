"""
L1.1 - Point-in-time float resolver.

The brokerage's `float` field on `get_equity_fundamentals` is current, not
historical. RYDE reads ~110M shares today; it floated 3.0M shares in March
2024. Feeding today's value into a 2024 backtest silently invalidates the
result (see CLAUDE.md hard rule 3). This module resolves the float as it
actually stood on a given date, from SEC filings dated on or before that
date only.

Resolution order (first source that yields a parseable number wins):

    1. ipo_prospectus           - shares registered in the IPO prospectus
                                   (424B4) or, for a foreign private issuer,
                                   the registration statement (F-1), filed
                                   on or before `date`.
    2. ipo_plus_followons       - (1) plus every registered follow-on
                                   offering (424B5 / F-3) also filed on or
                                   before `date`, summed.
    3. shares_outstanding_fallback - shares outstanding disclosed on the
                                   cover of the nearest annual filing
                                   (10-K / 20-F / 40-F) filed on or before
                                   `date`. Weaker: this is a share count as
                                   of some filing date, not the float, and
                                   callers should weight it accordingly
                                   (see PLAN.md L1.1).

No lookahead
------------
Every filing this module reads is checked against `date` twice: once when
the filing index is filtered (`_filings_before`), and again immediately
before its content is fetched (`_extract_shares`'s `LookaheadError` guard).
The second check is defense in depth against a backend that ignores its own
`until` parameter - it exists so a bug in the filtering step fails loudly
instead of silently reading future data.

Data access is injected
------------------------
`float_as_of` takes `index_fn` / `filing_fn` rather than calling the
brokerage MCP tools itself, because MCP tools are only reachable from an
agent turn, not from a plain Python process such as a pytest run. Wire the
real tools through with a thin adapter:

    float_as_of(
        "RYDE", "2024-09-06",
        index_fn=lambda **kw: get_sec_filing_index(**kw),
        filing_fn=lambda **kw: get_sec_filing(**kw),
    )

Their call signatures and response shapes mirror `get_sec_filing_index`
and `get_sec_filing` exactly, so tests can pass fakes with the same shape
without touching the network.
"""

from __future__ import annotations

import re
from typing import Callable, Sequence

IPO_FORMS: tuple[str, ...] = ("424B4", "F-1")
FOLLOWON_FORMS: tuple[str, ...] = ("424B5", "F-3")
ANNUAL_FORMS: tuple[str, ...] = ("10-K", "20-F", "40-F")

SOURCE_IPO_PROSPECTUS = "ipo_prospectus"
SOURCE_IPO_PLUS_FOLLOWONS = "ipo_plus_followons"
SOURCE_SHARES_OUTSTANDING_FALLBACK = "shares_outstanding_fallback"

# Signatures matching get_sec_filing_index(symbol, form_type=, since=,
# until=, cursor=) and get_sec_filing(filing_id, section=) respectively.
IndexFn = Callable[..., dict]
FilingFn = Callable[..., dict]

_NUM = r"\d{1,3}(?:,\d{3})+|\d+"

# "We are offering 3,000,000 Class A ordinary shares...", "...to sell up to
# 1,200,000 additional shares of common stock..."
_OFFERING_RE = re.compile(
    rf"(?:offer(?:ing)?|issu(?:e|ing)|sell(?:ing)?)\s+(?:up to\s+)?"
    rf"(?P<num>{_NUM})\s+(?:additional\s+)?"
    rf"(?:shares of\s+)?(?:our\s+)?(?:Class\s+[A-Z]\s+)?"
    rf"(?:ordinary|common)?\s*shares",
    re.IGNORECASE,
)

# "As of ..., there were 12,345,678 shares of common stock outstanding."
_OUTSTANDING_RE = re.compile(
    rf"(?P<num>{_NUM})\s+shares(?:\s+of[^,.\n]{{0,60}})?\s+(?:were\s+|are\s+)?outstanding",
    re.IGNORECASE,
)

# Sections likely to state the offering/outstanding size are checked first,
# so a match is found (and reported) from the most authoritative part of
# the filing rather than an incidental mention elsewhere.
_PREFERRED_SECTION_KEYWORDS = ("offering", "summary", "cover", "prospectus")


class FloatResolutionError(RuntimeError):
    """No IPO prospectus, follow-on, or annual filing yielded a share count."""


class LookaheadError(RuntimeError):
    """Refused to read a filing dated after the as-of date."""


def float_as_of(
    symbol: str,
    date: str,
    *,
    index_fn: IndexFn,
    filing_fn: FilingFn,
) -> dict:
    """Resolve `symbol`'s float as of `date` (inclusive), ISO YYYY-MM-DD.

    Returns {"shares": float, "source": str, "filing_date": str}. `source`
    is one of SOURCE_IPO_PROSPECTUS, SOURCE_IPO_PLUS_FOLLOWONS,
    SOURCE_SHARES_OUTSTANDING_FALLBACK. Raises FloatResolutionError if no
    source yields a number, rather than returning a fabricated value.
    """
    symbol = symbol.upper()

    ipo_filings = _filings_before(symbol, date, IPO_FORMS, index_fn)
    ipo_filing, ipo_shares = _first_parseable(ipo_filings, date, filing_fn, _OFFERING_RE)

    if ipo_filing is not None:
        followon_filings = _filings_before(symbol, date, FOLLOWON_FORMS, index_fn)
        followon_total = 0.0
        latest_followon_date = None
        for filing in followon_filings:
            shares = _extract_shares(filing, date, filing_fn, _OFFERING_RE)
            if shares:
                followon_total += shares
                if latest_followon_date is None or filing["date_filed"] > latest_followon_date:
                    latest_followon_date = filing["date_filed"]

        if followon_total > 0:
            return {
                "shares": ipo_shares + followon_total,
                "source": SOURCE_IPO_PLUS_FOLLOWONS,
                "filing_date": latest_followon_date,
            }

        return {
            "shares": ipo_shares,
            "source": SOURCE_IPO_PROSPECTUS,
            "filing_date": ipo_filing["date_filed"],
        }

    annual_filings = _filings_before(symbol, date, ANNUAL_FORMS, index_fn)
    annual_filing, shares = _first_parseable(annual_filings, date, filing_fn, _OUTSTANDING_RE)
    if annual_filing is not None:
        return {
            "shares": shares,
            "source": SOURCE_SHARES_OUTSTANDING_FALLBACK,
            "filing_date": annual_filing["date_filed"],
        }

    raise FloatResolutionError(
        f"no IPO prospectus, follow-on offering, or annual filing with a "
        f"parseable share count found for {symbol} on or before {date}"
    )


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------

def _unwrap(raw: dict) -> dict:
    """MCP responses nest their payload under "data"; accept either shape."""
    return raw.get("data", raw)


def _filings_before(symbol: str, date: str, forms: Sequence[str], index_fn: IndexFn) -> list[dict]:
    """Filings of `forms` filed on or before `date`, most recent first.

    Passes `until=date` to `index_fn` as the first line of defence, then
    filters the result again client-side - `index_fn` is an injected
    dependency and must never be trusted alone to enforce no-lookahead.
    """
    raw = index_fn(symbol=symbol, form_type=list(forms), until=date)
    filings = _unwrap(raw).get("filings", [])
    before = [f for f in filings if f["form_type"] in forms and f["date_filed"] <= date]
    return sorted(before, key=lambda f: f["date_filed"], reverse=True)


def _first_parseable(
    filings: Sequence[dict], date: str, filing_fn: FilingFn, pattern: re.Pattern
) -> tuple[dict | None, float | None]:
    """Try filings most-recent-first; return the first one that parses."""
    for filing in filings:
        shares = _extract_shares(filing, date, filing_fn, pattern)
        if shares:
            return filing, shares
    return None, None


def _extract_shares(
    filing: dict, date: str, filing_fn: FilingFn, pattern: re.Pattern
) -> float | None:
    """Read one filing's sections looking for `pattern`. Never reads a
    filing dated after `date`, even if it slipped past `_filings_before`.
    """
    if filing["date_filed"] > date:
        raise LookaheadError(
            f"refusing to read {filing.get('form_type')} filing "
            f"{filing.get('filing_id')} dated {filing['date_filed']}, "
            f"after as-of date {date}"
        )

    filing_id = filing["filing_id"]
    toc = _unwrap(filing_fn(filing_id=filing_id))
    sections = toc.get("table_of_contents", {}).get("sections", [])

    for section in _ordered_sections(sections):
        payload = _unwrap(filing_fn(filing_id=filing_id, section=section["id"]))
        content = payload.get("section", {}).get("content", "")
        match = pattern.search(content)
        if match:
            return float(match.group("num").replace(",", ""))

    return None


def _ordered_sections(sections: Sequence[dict]) -> list[dict]:
    """Sections whose title suggests the offering/cover page first."""
    preferred, rest = [], []
    for section in sections:
        title = section.get("title", "").lower()
        (preferred if any(k in title for k in _PREFERRED_SECTION_KEYWORDS) else rest).append(section)
    return preferred + rest
