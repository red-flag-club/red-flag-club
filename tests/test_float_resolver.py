"""
Tests for L1.1 (src/float_resolver.py).

`float_as_of` takes `index_fn`/`filing_fn` rather than calling the
brokerage MCP tools directly, so these tests run as plain pytest with no
network or MCP access. The fakes below reproduce the exact response shapes
of `get_sec_filing_index` / `get_sec_filing`.

The RYDE fixture's filing dates and form types are the real ones read live
from `get_sec_filing_index("RYDE")` while building this resolver: the
sandbox's filing index for RYDE carries only 6-K filings before 2025 (no
424B4/F-1 is indexed for RYDE at all), and content-fetch 404s on every
filing it does carry. That is precisely the gap `float_as_of`'s source
chain and `FloatResolutionError` exist for. To exercise the primary path
end-to-end without live data, the fixture adds one synthetic 424B4 whose
content matches the publicly filed prospectus (3,000,000 Class A ordinary
shares, priced 2024-03-05) and keeps every other row - including the real
post-cutoff 424B5/424B3 follow-on filings - genuine.
"""

import pytest

from src.float_resolver import (
    FloatResolutionError,
    LookaheadError,
    SOURCE_IPO_PLUS_FOLLOWONS,
    SOURCE_IPO_PROSPECTUS,
    SOURCE_SHARES_OUTSTANDING_FALLBACK,
    _extract_shares,
    float_as_of,
)

AS_OF = "2024-09-06"

# (form_type, date_filed, filing_id) - real RYDE rows plus one synthetic
# 424B4 (see module docstring). Several rows post-date AS_OF on purpose.
RYDE_INDEX = [
    ("424B4", "2024-03-01", "ryde-424b4"),        # synthetic; see docstring
    ("6-K", "2024-03-06", "ryde-6k-2024-03-06"),
    ("6-K", "2024-03-08", "ryde-6k-2024-03-08"),
    ("6-K", "2024-03-15", "ryde-6k-2024-03-15"),
    ("6-K", "2024-06-07", "ryde-6k-2024-06-07"),
    ("6-K", "2024-06-21", "ryde-6k-2024-06-21"),
    ("6-K", "2024-09-27", "ryde-6k-2024-09-27"),  # after AS_OF
    ("6-K", "2024-10-10", "ryde-6k-2024-10-10"),  # after AS_OF
    ("424B3", "2025-03-13", "ryde-424b3-2025-03-13"),  # after AS_OF
    ("424B5", "2025-09-10", "ryde-424b5-2025-09-10"),  # after AS_OF
    ("424B5", "2025-12-03", "ryde-424b5-2025-12-03"),  # after AS_OF
]

POST_CUTOFF_IDS = {fid for _, d, fid in RYDE_INDEX if d > AS_OF}

RYDE_TOC = {
    "ryde-424b4": [{"id": "cover", "title": "Prospectus Summary", "level": 1}],
}
RYDE_SECTIONS = {
    ("ryde-424b4", "cover"): (
        "We are offering 3,000,000 Class A ordinary shares in this "
        "offering at a public offering price of $4.00 per share."
    ),
}


def _make_fakes():
    """A leaky index_fn (ignores `until`, like a backend that forgets to
    filter) paired with a filing_fn that hard-fails on any post-cutoff
    filing_id and records every id it's asked to read.
    """
    read_calls: list[str] = []

    def index_fn(symbol, form_type=None, since=None, until=None, cursor=None):
        forms = set(form_type or [])
        rows = [r for r in RYDE_INDEX if not forms or r[0] in forms]
        return {
            "data": {
                "symbol": symbol,
                "filings": [
                    {"filing_id": fid, "form_type": ft, "date_filed": d}
                    for ft, d, fid in rows
                ],
            }
        }

    def filing_fn(filing_id, section=None):
        read_calls.append(filing_id)
        if filing_id in POST_CUTOFF_IDS:
            raise AssertionError(
                f"read a filing dated after {AS_OF}: {filing_id!r}"
            )
        if section is None:
            return {"data": {"table_of_contents": {"sections": RYDE_TOC.get(filing_id, [])}}}
        content = RYDE_SECTIONS.get((filing_id, section), "")
        return {"data": {"section": {"content": content}}}

    return index_fn, filing_fn, read_calls


def test_ryde_resolves_to_3_million_as_of_2024_09_06():
    index_fn, filing_fn, _ = _make_fakes()

    result = float_as_of("RYDE", AS_OF, index_fn=index_fn, filing_fn=filing_fn)

    assert result == {
        "shares": 3_000_000.0,
        "source": SOURCE_IPO_PROSPECTUS,
        "filing_date": "2024-03-01",
    }


def test_no_filing_after_date_is_ever_read():
    index_fn, filing_fn, read_calls = _make_fakes()

    float_as_of("RYDE", AS_OF, index_fn=index_fn, filing_fn=filing_fn)

    # The filing_fn fake would already have raised had a post-cutoff id
    # been read; this is the direct assertion of the same invariant.
    assert not (set(read_calls) & POST_CUTOFF_IDS)
    assert read_calls, "sanity: the resolver must have read something"


def test_lookahead_guard_rejects_filing_dated_after_cutoff():
    """Unit test of the guard itself, independent of _filings_before
    having already excluded the filing - defense in depth."""
    future_filing = {
        "filing_id": "ryde-424b5-2025-09-10",
        "form_type": "424B5",
        "date_filed": "2025-09-10",
    }

    def filing_fn(filing_id, section=None):
        raise AssertionError("should never be called")

    with pytest.raises(LookaheadError):
        _extract_shares(future_filing, AS_OF, filing_fn, pattern=None)


def test_adds_registered_followon_offering():
    index = [
        ("424B4", "2024-03-01", "abc-424b4"),
        ("424B5", "2024-06-01", "abc-424b5"),  # before AS_OF -> must be added
        ("424B5", "2025-01-01", "abc-424b5-late"),  # after AS_OF -> must not
    ]
    toc = {
        "abc-424b4": [{"id": "cover", "title": "Prospectus Summary"}],
        "abc-424b5": [{"id": "cover", "title": "Prospectus Summary"}],
    }
    sections = {
        ("abc-424b4", "cover"): "We are offering 1,000,000 shares of common stock.",
        ("abc-424b5", "cover"): "We are offering 500,000 additional shares of common stock.",
    }

    def index_fn(symbol, form_type=None, since=None, until=None, cursor=None):
        forms = set(form_type or [])
        rows = [r for r in index if not forms or r[0] in forms]
        return {"filings": [{"filing_id": fid, "form_type": ft, "date_filed": d} for ft, d, fid in rows]}

    def filing_fn(filing_id, section=None):
        assert filing_id != "abc-424b5-late"
        if section is None:
            return {"data": {"table_of_contents": {"sections": toc[filing_id]}}}
        return {"data": {"section": {"content": sections[(filing_id, section)]}}}

    result = float_as_of("ABC", AS_OF, index_fn=index_fn, filing_fn=filing_fn)

    assert result == {
        "shares": 1_500_000.0,
        "source": SOURCE_IPO_PLUS_FOLLOWONS,
        "filing_date": "2024-06-01",
    }


def test_falls_back_to_shares_outstanding_when_no_ipo_filing():
    index = [("10-K", "2024-02-01", "xyz-10k")]
    toc = {"xyz-10k": [{"id": "cover", "title": "Cover Page"}]}
    sections = {
        ("xyz-10k", "cover"): "As of January 15, 2024, there were 8,200,000 shares of common stock outstanding.",
    }

    def index_fn(symbol, form_type=None, since=None, until=None, cursor=None):
        forms = set(form_type or [])
        rows = [r for r in index if not forms or r[0] in forms]
        return {"filings": [{"filing_id": fid, "form_type": ft, "date_filed": d} for ft, d, fid in rows]}

    def filing_fn(filing_id, section=None):
        if section is None:
            return {"data": {"table_of_contents": {"sections": toc[filing_id]}}}
        return {"data": {"section": {"content": sections[(filing_id, section)]}}}

    result = float_as_of("XYZ", AS_OF, index_fn=index_fn, filing_fn=filing_fn)

    assert result == {
        "shares": 8_200_000.0,
        "source": SOURCE_SHARES_OUTSTANDING_FALLBACK,
        "filing_date": "2024-02-01",
    }


def test_raises_when_nothing_resolvable():
    def index_fn(symbol, form_type=None, since=None, until=None, cursor=None):
        return {"filings": []}

    def filing_fn(filing_id, section=None):
        raise AssertionError("should never be called")

    with pytest.raises(FloatResolutionError):
        float_as_of("NOPE", AS_OF, index_fn=index_fn, filing_fn=filing_fn)
