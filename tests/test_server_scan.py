"""Layer 2 scan log, outcomes and tools (specs/004, T005/T007/T009/T011/T014).
RYDE bars are real (L1.3 seed event); everything else is synthetic."""

import datetime as dt
import pathlib
import re

import pytest

pytest.importorskip("duckdb")

from server import tools as T  # noqa: E402
from server.data import ET  # noqa: E402
from server.market import FixtureSnapshots, MassiveGrouped, check_source  # noqa: E402
from server.outcomes import forward_metrics  # noqa: E402
from server.providers import seed_fixtures  # noqa: E402
from server.scan import refresh, screen  # noqa: E402
from server.schedule import next_run, run_forever  # noqa: E402
from tests.server_fixtures import make_ds, series  # noqa: E402


def _flat_then_pump(start="2024-01-01", flat=60, k=8, step=1.12, base=4.0):
    return series([base] * flat + [base * step ** i for i in range(1, k + 1)], start, vol=2e5)


def _after(day: str, h=18) -> dt.datetime:
    return dt.datetime.fromisoformat(day).replace(hour=h, tzinfo=ET)


def _run(rows_by_symbol, until, splits=None, backfill=400):
    now = _after(until)
    ds, _ = make_ds(now=now)
    src = FixtureSnapshots(rows_by_symbol, splits)
    out = refresh(ds.store, ds, src, now=now, backfill=backfill)
    return ds, src, out


# ------------------------------------------------------------------ screen (pure)

def _hist(rows, sym="X"):
    return {sym: rows}


def test_screen_thresholds_and_price_band():
    rows = _flat_then_pump()
    first = next(i for i in range(len(rows)) if rows[i]["c"] / min(r["c"] for r in rows[max(0, i - 5):i + 1]) - 1 >= 0.5)
    day = rows[first]["date"]
    assert [h["symbol"] for h in screen(_hist(rows[:first + 1]), day)] == ["X"]
    assert screen(_hist(rows[:first]), rows[first - 1]["date"]) == []          # one session earlier: not yet
    cheap = [{**r, "c": r["c"] / 10} for r in rows[:first + 1]]                 # below $1
    dear = [{**r, "c": r["c"] * 10} for r in rows[:first + 1]]                  # above $30
    assert screen(_hist(cheap), day) == [] and screen(_hist(dear), day) == []


def test_reverse_split_is_not_a_hit_once_known():
    rows = series([2.0] * 40 + [20.0] * 3, "2024-01-01")                        # 1-for-10 reverse split
    split_day = rows[40]["date"]
    assert screen(_hist(rows), rows[-1]["date"])                                 # unknown split: flagged hit (recall)
    assert "possible_split" in screen(_hist(rows), rows[-1]["date"])[0]["flags"]
    assert screen(_hist(rows), rows[-1]["date"], {"X": [split_day]}) == []      # known split: truncated


def test_market_history_never_returns_rows_after_as_of():
    pump = _flat_then_pump()
    ds, _, _ = _run({"PMP": pump}, pump[-1]["date"])
    mid = pump[40]["date"]
    hist = ds.store.market_history(mid, 300)
    assert hist and all(r["date"] <= mid for rows in hist.values() for r in rows)
    assert hist["PMP"][-1]["date"] == mid


def test_bad_print_is_flagged_not_dropped():
    rows = series([5.0] * 30 + [20.0, 5.2, 8.0], "2024-01-01", vol=1e5)
    rows[30]["v"] = 50
    hits = screen(_hist(rows[:31]), rows[30]["date"])
    assert hits and "bad_print" not in hits[0]["flags"]                          # needs the next bar to judge
    hits = screen(_hist(rows), rows[-1]["date"])
    assert hits and "bad_print" in hits[0]["flags"]


# ------------------------------------------------------------------ US1: the log

def test_pump_is_logged_with_veto_and_rerun_changes_nothing():
    pump = _flat_then_pump()
    ds, src, out = _run({"PMP": pump, "CALM": series([10.0] * 68, "2024-01-01")}, pump[-1]["date"])
    rows = ds.store.scan_rows(symbol="PMP")
    assert rows and rows[0]["verdict"] in ("CAUTION", "VETO") and any(r["verdict"] == "VETO" for r in rows)
    assert not ds.store.scan_rows(symbol="CALM")
    before = ds.store.scan_rows()
    again = refresh(ds.store, ds, src, now=_after(pump[-1]["date"]))
    assert again["sessions_scanned"] == 0 and ds.store.scan_rows() == before    # SC-002


def test_ryde_is_logged_on_its_run_and_vetoed_at_the_peak():
    ds, _, _ = _run({"RYDE": seed_fixtures()["RYDE"]}, "2024-11-15", backfill=200)
    rows = {r["session"]: r for r in ds.store.scan_rows(symbol="RYDE")}
    assert "2024-09-05" in rows and rows["2024-09-06"]["verdict"] == "VETO"      # SC-001
    out = {o["first_logged"]: o for o in ds.store.outcomes()}
    assert out["2024-09-05"]["label"] == "collapsed" and out["2024-09-05"]["drawdown"] > 0.9


def test_logged_verdict_is_identical_without_later_sessions():
    """SC-003 truncation: what was logged for day D cannot depend on D+1.."""
    ryde = seed_fixtures()["RYDE"]
    full, _, _ = _run({"RYDE": ryde}, "2024-11-15", backfill=200)
    cut, _, _ = _run({"RYDE": [r for r in ryde if r["date"] <= "2024-09-10"]}, "2024-09-10", backfill=200)
    strip = lambda rs: [{k: v for k, v in r.items() if k not in ("logged_at", "backfilled")} for r in rs]
    a = strip(full.store.scan_rows(since="2024-04-01"))
    b = strip(cut.store.scan_rows(since="2024-04-01"))
    assert a[:len(b)] == b and len(b) > 5


def test_missed_sessions_are_caught_up_in_order_and_backfill_is_marked():
    pump = _flat_then_pump()
    ds, src, _ = _run({"PMP": pump}, pump[-1]["date"])
    assert src.calls == sorted(src.calls)
    rows = ds.store.scan_rows(symbol="PMP")
    assert all(r["backfilled"] is False for r in rows if r["session"] >= pump[-5]["date"])


def test_rate_limit_mid_backfill_stops_cleanly_and_resumes():
    from server.providers import RateLimited
    pump = _flat_then_pump()
    now = _after(pump[-1]["date"])
    ds, _ = make_ds(now=now)
    src = FixtureSnapshots({"PMP": pump})
    real, n = src.session, {"calls": 0}

    def flaky(d):
        n["calls"] += 1
        if n["calls"] == 30:
            raise RateLimited("free tier")
        return real(d)
    src.session = flaky
    out = refresh(ds.store, ds, src, now=now)
    assert out["status"].startswith("partial: rate limit")
    out = refresh(ds.store, ds, src, now=now)
    assert out["status"] == "ok" and ds.store.scan_rows(symbol="PMP")


def test_scan_log_is_never_updated_or_deleted_in_code():
    root = pathlib.Path(__file__).resolve().parent.parent / "server"
    for f in root.glob("*.py"):
        text = f.read_text()
        assert not re.search(r"(UPDATE|DELETE\s+FROM|INSERT\s+OR\s+REPLACE\s+INTO)\s+scan_log", text, re.I), f
        assert not re.search(r'_insert\("scan_log"[^)]*verb="INSERT OR REPLACE"', text), f


# ------------------------------------------------------------------ US2: outcomes

def test_outcome_waits_thirty_sessions_then_labels_collapse():
    crash = _flat_then_pump(k=8)
    peak = crash[-1]["c"]
    tail = series([peak * 0.25] * 40, "2024-01-01")
    d = dt.date.fromisoformat(crash[-1]["date"])
    for r in tail:                                                               # re-date after the pump
        d += dt.timedelta(days=1)
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        r["date"] = d.isoformat()
    rows = crash + tail
    early, _, _ = _run({"CRS": rows[:len(crash) + 10]}, rows[len(crash) + 9]["date"])
    assert {o["label"] for o in early.store.outcomes()} == {"pending"}
    late, _, _ = _run({"CRS": rows}, rows[-1]["date"])
    assert {o["label"] for o in late.store.outcomes()} == {"collapsed"}


def test_forward_metrics_exclude_backfilled_rows():
    ds, _, _ = _run({"RYDE": seed_fixtures()["RYDE"]}, "2024-11-15", backfill=200)
    m = forward_metrics(ds.store)
    assert m["forward"]["episodes"] == 0 and m["backfilled"]["collapsed"] == 1
    assert m["backfilled"]["recall"] == 1.0 and m["backfilled"]["enough"] is False


# ------------------------------------------------------------------ US3: tools

def test_is_pumping_and_scan_latest():
    ds, _, _ = _run({"RYDE": seed_fixtures()["RYDE"]}, "2024-09-10", backfill=200)
    r = T.is_pumping(ds, "ryde")
    assert r["on_scan_today"] and r["days_on_scan"] >= 3 and r["first_seen"] <= "2024-09-05"
    assert "Not a buy signal" in r["text"]
    s = T.scan_latest(ds)
    assert s["session"] == "2024-09-10" and s["rows"][0]["symbol"] == "RYDE"
    never = T.is_pumping(ds, "ZZZZ")
    assert never["days_on_scan"] == 0 and "never on the scan" in never["text"]
    with pytest.raises(T.ToolError):
        T.scan_latest(ds, limit=500)


def test_scan_latest_before_any_scan_is_refused():
    ds, _ = make_ds()
    with pytest.raises(T.ToolError):
        T.scan_latest(ds)


# ------------------------------------------------------------------ sources and schedule

def test_massive_grouped_parses_and_check_source_explains_a_403():
    import json
    body = json.dumps({"results": [{"T": "RYDE", "o": 8, "h": 9, "l": 7, "c": 8.5, "v": 100}]}).encode()
    seen = []
    src = MassiveGrouped("k", fetch=lambda req: (seen.append(req.full_url), (200, body))[1])
    assert src.session("2024-09-06") == [{"symbol": "RYDE", "o": 8, "h": 9, "l": 7, "c": 8.5, "v": 100}]
    assert "/grouped/locale/us/market/stocks/2024-09-06" in seen[0]
    denied = MassiveGrouped("k", fetch=lambda req: (403, b""))
    assert "not on your plan" in check_source(denied, "2024-09-06")
    assert denied.splits("2024-01-01", "2024-09-06") == [] and denied.splits_available is False


def test_next_run_skips_weekends_and_past_slots():
    times = ("10:00", "12:30", "15:00", "17:30")
    fri_evening = dt.datetime(2026, 10, 16, 18, 0, tzinfo=ET)
    assert next_run(fri_evening, times) == dt.datetime(2026, 10, 19, 10, 0, tzinfo=ET)
    assert next_run(dt.datetime(2026, 10, 15, 12, 30, tzinfo=ET), times).time() == dt.time(15, 0)


def test_failed_job_does_not_stop_the_schedule():
    t = [dt.datetime(2026, 10, 15, 9, 59, tzinfo=ET)]
    def boom():
        raise RuntimeError("provider down")
    run_forever(boom, ("10:00",), now=lambda: t[0],
                sleep=lambda s: t.__setitem__(0, t[0] + dt.timedelta(seconds=s)), once=True)
    assert t[0] >= dt.datetime(2026, 10, 15, 10, 0, tzinfo=ET)


def test_sql_prefilter_never_drops_a_screen_hit():
    """The SQL candidate query must return a superset of screen()'s hits,
    or the prefilter would silently cut recall (hard rule 4)."""
    import random
    from server.scan import PRICE_MAX, PRICE_MIN, RUNUP_21, RUNUP_5, SCREEN_SESSIONS
    rng = random.Random(7)
    rows = {}
    for i in range(300):
        p, sym, out = rng.uniform(0.6, 35), f"R{i}", []
        for r in series([1.0] * 40, "2025-01-01"):
            if rng.random() < 0.15:                                  # sparse symbols: missing sessions
                continue
            p *= rng.choice([0.9, 0.97, 1.0, 1.03, 1.1, 1.25])
            out.append({**r, "o": p, "h": p, "l": p, "c": p})
        rows[sym] = out
    last = series([1.0] * 40, "2025-01-01")[-1]["date"]
    ds, _, _ = _run(rows, last)
    seen = 0
    for session in ds.store.recent_sessions(last, 10):
        recent = ds.store.recent_sessions(session, 22)
        starts = {5: recent[-6], 21: recent[0]}
        cands = set(ds.store.screen_candidates(session, starts[5], starts[21], PRICE_MIN, PRICE_MAX, RUNUP_5, RUNUP_21))
        full = ds.store.market_history(session, SCREEN_SESSIONS)
        hits = {h["symbol"] for h in screen(full, session, None, starts)}
        assert hits <= cands, hits - cands
        seen += len(hits)
        assert hits == {h["symbol"] for h in screen({s: full[s] for s in cands if s in full}, session, None, starts)}
    assert seen > 20                                                   # not vacuous
