"""MCP server data layer: bar hygiene, cache, no lookahead (specs/003, T009)."""

import datetime as dt

import pytest

pytest.importorskip("duckdb")

from server.bars import LookaheadError, clean_bars, suspect_bad_prints, to_bars  # noqa: E402
from server.data import DataUnavailable, last_session  # noqa: E402
from server.providers import NoData, PayloadProvider, RateLimited, RateLimiter, parse_brokerage_payload  # noqa: E402
from server.store import Store  # noqa: E402
from tests.server_fixtures import NOW, make_ds, series  # noqa: E402


def test_clean_bars_drops_only_uninformative_rows_and_counts_them():
    rows = [
        {"date": "2024-02-29", "o": 0, "h": 0, "l": 0, "c": 0, "v": 0},          # RYDE-style placeholder
        {"date": "2024-03-01", "o": 5, "h": 5, "l": 5, "c": 5, "v": 0, "interpolated": True},
        {"date": "2024-03-04", "o": 5, "h": 5, "l": 5, "c": 5, "v": 0},          # flat: kept (ghost quote)
        {"date": "2024-03-05", "o": 5, "h": 6, "l": 4, "c": 5.5, "v": 100},
        {"date": "2024-03-05", "o": 5, "h": 6, "l": 4, "c": 5.6, "v": 100},      # refetch wins
    ]
    kept, s = clean_bars(rows)
    assert [r["date"] for r in kept] == ["2024-03-04", "2024-03-05"]
    assert kept[-1]["c"] == 5.6
    assert (s.total, s.kept, s.dropped_nonpositive, s.dropped_interpolated, s.dropped_duplicate) == (5, 2, 1, 1, 1)


def test_clean_bars_refuses_bars_after_as_of():
    with pytest.raises(LookaheadError):
        clean_bars(series([1.0] * 3, "2024-03-04"), as_of="2024-03-05")


def test_bad_print_is_flagged_not_dropped_and_heavy_volume_spike_is_not_flagged():
    rows = series([27.0] * 25 + [1123.5, 22.5] + [22.0] * 3, "2023-01-02")
    rows[25]["v"] = 196                                   # REED 2023-01-25: 196 shares
    bars = to_bars(clean_bars(rows)[0])
    assert len(bars) == 30 and suspect_bad_prints(bars) == [rows[25]["date"]]
    rows[25]["v"] = 5e7                                   # JAGX-style real spike
    assert suspect_bad_prints(to_bars(clean_bars(rows)[0])) == []


def test_store_reads_are_cut_at_as_of():
    st = Store()
    st.put_bars("X", series([1.0, 2.0, 3.0], "2024-03-04"), "fixture")
    assert [r["date"] for r in st.bars("X", "2024-01-01", "2024-03-05")] == ["2024-03-04", "2024-03-05"]


def test_cache_hit_makes_no_provider_call():
    ds, prov = make_ds({"ABC": series([10.0] * 400, "2025-01-01")})
    ds.bars("ABC", "2025-12-01")
    n = len(prov.calls)
    rows, meta = ds.bars("ABC", "2025-11-01")
    assert len(prov.calls) == n and rows[-1]["date"] <= "2025-11-01" and meta["bars"] == len(rows)


def test_truncation_bars_identical_with_and_without_later_data_cached():
    full = series([10.0 + i * 0.1 for i in range(400)], "2025-01-01")
    a, _ = make_ds({"ABC": full})
    a.bars("ABC", last_session(NOW))                       # cache holds everything
    b, _ = make_ds({"ABC": [r for r in full if r["date"] <= "2025-09-01"]})
    assert a.bars("ABC", "2025-09-01")[0] == b.bars("ABC", "2025-09-01")[0]


def test_unknown_symbol_is_memoised_as_no_data():
    ds, prov = make_ds()
    for _ in range(2):
        with pytest.raises(NoData):
            ds.bars("ZZZZ", "2026-10-01")
    assert sum(1 for c in prov.calls if c[0] == "ZZZZ") == 1


def test_rate_limit_without_cache_is_unavailable_not_a_verdict():
    ds, prov = make_ds({"ABC": series([10.0] * 50)})
    prov.rate_limited = True
    with pytest.raises(DataUnavailable):
        ds.bars("ABC", "2025-08-01")


def test_rate_limit_with_stale_covering_cache_serves_cache():
    ds, prov = make_ds({"ABC": series([10.0] * 400, "2025-06-02")})
    ds.bars("ABC", last_session(NOW))
    ds.today_ttl = dt.timedelta(0)                         # force "stale"
    prov.rate_limited = True
    rows, _ = ds.bars("ABC", last_session(NOW))
    assert rows


def test_filings_are_cut_at_as_of():
    ds, _ = make_ds()
    early, status = ds.filings("RYDE", "2024-06-30")
    assert status == "ok" and early and all(f["date_filed"] <= "2024-06-30" for f in early)
    assert len(ds.filings("RYDE", "2026-10-01")[0]) > len(early)


def test_future_as_of_is_refused():
    ds, _ = make_ds()
    with pytest.raises(ValueError):
        ds.resolve_as_of("2026-10-16")


def test_last_session_skips_weekends_and_unsettled_today():
    from server.data import ET
    assert last_session(dt.datetime(2026, 10, 17, 12, tzinfo=ET)) == "2026-10-16"   # Saturday
    assert last_session(dt.datetime(2026, 10, 15, 10, tzinfo=ET)) == "2026-10-14"   # before the close


def test_rate_limiter_refuses_rather_than_hanging():
    t = [0.0]
    rl = RateLimiter(2, 60, max_wait=1, clock=lambda: t[0], sleep=lambda s: None)
    rl.acquire(); rl.acquire()
    with pytest.raises(RateLimited):
        rl.acquire()
    t[0] = 61
    rl.acquire()


def test_brokerage_payload_keeps_interpolated_flag_for_cleaning(tmp_path):
    payload = {"data": {"results": [{"symbol": "ryde", "interval": "day", "bars": [
        {"begins_at": "2024-09-05T00:00:00Z", "open_price": "8", "high_price": "9", "low_price": "7",
         "close_price": "8.5", "volume": 10, "interpolated": False},
        {"begins_at": "2024-09-06T00:00:00Z", "open_price": "8", "high_price": "8", "low_price": "8",
         "close_price": "8", "volume": 0, "interpolated": True}]}]}}
    assert len(parse_brokerage_payload(payload)["RYDE"]) == 2
    import json
    (tmp_path / "p.json").write_text(json.dumps(payload))
    rows = PayloadProvider(tmp_path).daily("RYDE", "2024-01-01", "2024-12-31")
    assert len(clean_bars(rows)[0]) == 1


# ------------------------------------------------------------------ HTTP adapters (fake fetch, no network)

def _fetch(responses, seen):
    def f(req):
        seen.append(req)
        return responses.pop(0)
    return f


def test_tiingo_uses_adjusted_prices_and_keeps_split_factor():
    import json
    from server.providers import TiingoProvider
    seen = []
    body = json.dumps([{"date": "2024-09-06T00:00:00.000Z", "open": 80, "high": 90, "low": 70, "close": 85,
                        "volume": 10, "adjOpen": 8, "adjHigh": 9, "adjLow": 7, "adjClose": 8.5,
                        "adjVolume": 100, "splitFactor": 0.1}]).encode()
    p = TiingoProvider("k", fetch=_fetch([(200, body)], seen))
    r = p.daily("RYDE", "2024-09-01", "2024-09-06")[0]
    assert (r["date"], r["c"], r["raw_c"], r["split_factor"], r["v"]) == ("2024-09-06", 8.5, 85, 0.1, 100)
    assert seen[0].get_header("Authorization") == "Token k" and "k" not in seen[0].full_url
    with pytest.raises(NoData):
        TiingoProvider("k", fetch=_fetch([(404, b"")], [])).daily("ZZZZ", "2024-01-01", "2024-02-01")
    with pytest.raises(RateLimited):
        TiingoProvider("k", fetch=_fetch([(429, b"")], [])).daily("A", "2024-01-01", "2024-02-01")


def test_massive_parses_aggregates():
    import json
    from server.providers import MassiveProvider
    body = json.dumps({"status": "OK", "resultsCount": 1,
                       "results": [{"t": 1725595200000, "o": 8, "h": 9, "l": 7, "c": 8.5, "v": 100}]}).encode()
    r = MassiveProvider("k", fetch=_fetch([(200, body)], [])).daily("RYDE", "2024-09-01", "2024-09-06")
    assert r[0]["date"] == "2024-09-06" and r[0]["c"] == 8.5


def test_edgar_maps_ticker_and_reads_all_filing_pages():
    import json
    from server.sec import EdgarClient
    seen = []
    tickers = json.dumps({"0": {"cik_str": 1849056, "ticker": "RYDE", "title": "Ryde Group"}}).encode()
    sub = json.dumps({"filings": {"recent": {"form": ["6-K", "20-F"], "filingDate": ["2024-09-27", "2024-04-30"]},
                                  "files": [{"name": "CIK0001849056-submissions-001.json"}]}}).encode()
    old = json.dumps({"form": ["F-1"], "filingDate": ["2023-01-05"]}).encode()
    c = EdgarClient("owner@example.com", fetch=_fetch([(200, tickers), (200, sub), (200, old)], seen))
    cik, rows = c.filings("ryde")
    assert cik == "0001849056" and {"form": "F-1", "filed": "2023-01-05"} in rows and len(rows) == 3
    assert all(r.get_header("User-agent") == "pd-defence owner@example.com" for r in seen)
    with pytest.raises(NoData):
        c.filings("NOPE")
    with pytest.raises(ValueError):
        EdgarClient("")
