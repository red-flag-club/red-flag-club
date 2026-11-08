"""Local data retention (specs/005-data-retention)."""

import datetime as dt

import pytest

pytest.importorskip("duckdb")

from server import tools as T  # noqa: E402
from server.data import CACHE_DAYS, ET, IDLE_DAYS, last_session  # noqa: E402
from server.market import FixtureSnapshots  # noqa: E402
from server.providers import seed_fixtures  # noqa: E402
from server.scan import MARKET_KEEP_SESSIONS, refresh  # noqa: E402
from server.store import _now  # noqa: E402
from tests.server_fixtures import NOW, make_ds, series  # noqa: E402


def _recent(closes, end=None):
    """Weekday series ending on the last session."""
    end = dt.date.fromisoformat(end or last_session(NOW))
    out, d = [], end
    for c in reversed(closes):
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
        out.append({"date": d.isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1e5,
                    "raw_c": c, "split_factor": 1.0})
        d -= dt.timedelta(days=1)
    return list(reversed(out))


def _count(ds, sym=None):
    q = "SELECT count(*) FROM bars" + (" WHERE symbol = ?" if sym else "")
    return ds.store._q(q, (sym,) if sym else ())[0][0]


def test_historical_question_stores_no_old_bars():
    """SC-001: was_i_pumped RYDE 2024 is answered, VETO, and nothing is written."""
    ds, prov = make_ds()
    r = T.was_i_pumped(ds, "RYDE", "2024-09-09")
    assert r["at_the_time"]["verdict"] == "VETO"
    assert r["at_the_time"]["data"]["stored"] is False and "not stored" in r["text"]
    assert "not stored" in T.check_ticker(ds, "RYDE", "2024-09-06")["text"]
    assert _count(ds, "RYDE") == 0
    n = len(prov.calls)
    T.was_i_pumped(ds, "RYDE", "2024-09-10")                     # same server session: memory hit
    T.check_ticker(ds, "RYDE", "2024-08-30")
    assert len(prov.calls) == n


def test_current_question_uses_the_disk_cache_within_the_window():
    ds, prov = make_ds({"CUR": _recent([10.0 + 0.01 * i for i in range(700)])})
    r = T.check_ticker(ds, "CUR")
    assert r["data"]["stored"] is True
    oldest = ds.store._q("SELECT min(date) FROM bars WHERE symbol = 'CUR'")[0][0].isoformat()
    assert oldest >= ds.window_start()                          # padding clamped to the window
    n = len(prov.calls)
    T.check_ticker(ds, "CUR", (dt.date.fromisoformat(last_session(NOW)) - dt.timedelta(days=20)).isoformat())
    assert len([c for c in prov.calls[n:] if c[0] == "CUR"]) == 0


def test_idle_symbols_and_out_of_window_bars_are_pruned():
    ds, _ = make_ds({"OLD": _recent([5.0] * 400), "NEW": _recent([7.0] * 400)})
    T.check_ticker(ds, "OLD")
    T.check_ticker(ds, "NEW")
    stale = _now() - dt.timedelta(days=IDLE_DAYS + 1)
    ds.store.con.execute("UPDATE coverage SET accessed_at = ? WHERE symbol = 'OLD'", (stale,))
    ds.store.con.execute("INSERT INTO bars VALUES ('NEW', '2020-01-02', 1,1,1,1,1,1,1,'x', ?)", (_now(),))
    out = ds.prune()
    assert out == {"old_bars": 1, "idle_symbols": 1}
    assert _count(ds, "OLD") == 0 and ds.store.coverage("OLD") is None
    assert _count(ds, "NEW") > 0 and ds.store._q("SELECT min(date) FROM bars")[0][0].isoformat() >= ds.window_start()
    T.check_ticker(ds, "OLD")                                    # evicted symbols simply refetch
    assert _count(ds, "OLD") > 0


def test_market_keeps_a_rolling_window_and_outcomes_survive():
    """RYDE 2024 scanned through a 200-session backfill: the disk keeps 70
    sessions, the collapse label is still decided, pruned sessions are not
    re-fetched, and a later refresh logs nothing twice."""
    now = dt.datetime(2024, 11, 15, 18, tzinfo=ET)
    ds, _ = make_ds(now=now)
    src = FixtureSnapshots({"RYDE": seed_fixtures()["RYDE"]})
    out = refresh(ds.store, ds, src, now=now, backfill=200)
    assert out["sessions_pruned"] > 0
    kept = ds.store._q("SELECT count(DISTINCT date) FROM market_daily")[0][0]
    assert kept <= MARKET_KEEP_SESSIONS
    labels = {o["first_logged"]: o["label"] for o in ds.store.outcomes()}
    assert labels["2024-09-05"] == "collapsed"
    log_before = ds.store.scan_rows()
    calls = len(src.calls)
    again = refresh(ds.store, ds, src, now=now, backfill=200)
    assert len(src.calls) == calls and again["sessions_scanned"] == 0
    assert ds.store.scan_rows() == log_before
    assert {o["first_logged"]: o["label"] for o in ds.store.outcomes()} == labels


def test_pruning_does_not_split_episodes():
    """Episode grouping counts pruned sessions, so a symbol logged on
    consecutive days stays one episode after its early sessions are pruned."""
    now = dt.datetime(2024, 11, 15, 18, tzinfo=ET)
    ds, _ = make_ds(now=now)
    refresh(ds.store, ds, FixtureSnapshots({"RYDE": seed_fixtures()["RYDE"]}), now=now, backfill=200)
    from server.outcomes import episodes
    firsts = [e["first_logged"] for e in episodes(ds.store) if e["symbol"] == "RYDE"]
    assert firsts == sorted(set(firsts)) and "2024-09-06" not in firsts and "2024-09-05" in firsts


def test_scan_verdicts_unchanged_by_the_shorter_check_window():
    """Recall: VETO rules need <= 11 bars, so RYDE's 2024-09-06 VETO holds."""
    now = dt.datetime(2024, 9, 10, 18, tzinfo=ET)
    ds, _ = make_ds(now=now)
    refresh(ds.store, ds, FixtureSnapshots({"RYDE": seed_fixtures()["RYDE"]}), now=now, backfill=200)
    rows = {r["session"]: r["verdict"] for r in ds.store.scan_rows(symbol="RYDE")}
    assert rows["2024-09-06"] == "VETO" and rows["2024-09-09"] == "VETO"


def test_cache_window_constants_cover_a_current_check():
    assert CACHE_DAYS >= 430 + 30


def test_compaction_shrinks_the_file_and_keeps_every_row(tmp_path):
    from server.store import Store
    st = Store(tmp_path / "pd.duckdb")
    rows = [{"symbol": f"S{i}", "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0 + i, "v": 1.0} for i in range(1500)]
    for d in series([1.0] * 20, "2025-01-01"):
        st.put_session(d["date"], rows, "fixture", 0)
    st.log_hits([{"session": "2025-01-01", "symbol": "S1", "logged_at": _now(), "close": 2.0, "ret_1": 0.0,
                  "ret_5": 0.6, "ret_21": 0.6, "rel_vol_30": None, "reason": "x", "flags": "",
                  "backfilled": False, "verdict": "VETO", "reasons": ""}])
    assert st.prune_market(5) == 15
    before_rows = st._q("SELECT count(*) FROM market_daily")[0][0]
    before, after = st.compact()
    assert after <= before                       # the size win is measured at scale (spec 005 Result)
    assert st._q("SELECT count(*) FROM market_daily")[0][0] == before_rows == 5 * 1500
    assert len(st.scan_rows()) == 1 and st.sessions("pruned")              # still usable after the swap
    st.put_session("2025-03-03", rows[:10], "fixture", 0)
    assert not (tmp_path / "pd.compact").exists()
