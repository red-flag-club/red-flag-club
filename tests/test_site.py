"""Community site build (specs/006-community-site)."""

import datetime as dt
import json
import random
import re

import pytest

pytest.importorskip("duckdb")

from server.data import ET  # noqa: E402
from server.market import FixtureSnapshots  # noqa: E402
from server.providers import seed_fixtures  # noqa: E402
from server.scan import refresh, weekdays  # noqa: E402
from server.site import PENNY_MAX, TOP_N, WEB, band, build_data, build_site  # noqa: E402
from tests.server_fixtures import make_ds  # noqa: E402

NOW = dt.datetime(2024, 9, 6, 18, tzinfo=ET)


def _universe(n=260, seed=3):
    """RYDE (real bars) plus n synthetic small caps; every 10th is pumped."""
    rng = random.Random(seed)
    days = weekdays("2024-03-01", "2024-09-06")
    rows = {"RYDE": seed_fixtures()["RYDE"]}
    for i in range(n):
        p = rng.choice([0.4, 0.9, 2.0, 3.5, 8.0, 20.0, 45.0])
        out = []
        for k, d in enumerate(days):
            step = rng.uniform(0.15, 0.3) if (i % 10 == 0 and len(days) - 8 <= k) else rng.gauss(0, 0.03)
            p = max(0.05, p * (1 + step))
            out.append({"date": d, "o": p, "h": p * 1.02, "l": p * 0.98, "c": round(p, 4), "v": 5e5})
        rows[f"S{i:03d}"] = out
    return rows


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    ds, _ = make_ds(now=NOW)
    refresh(ds.store, ds, FixtureSnapshots(_universe()), now=NOW, backfill=200)
    out = tmp_path_factory.mktemp("site") / "site"
    build_site(ds.store, ds, out, now=dt.datetime(2024, 9, 6, 22))
    data = {p.name: json.loads(p.read_text()) for p in (out / "data").glob("*.json")}
    return ds, out, data


def test_all_pages_and_data_files_exist(built):
    _, out, data = built
    for f in ("index.html", "app.js", "app.css", "assistant.js", ".nojekyll"):
        assert (out / f).exists(), f
    assert not (out / "assistant.test.mjs").exists() and not (out / "package.json").exists()
    assert set(data) == {"meta.json", "movers.json", "symbols.json", "scan.json", "outcomes.json", "stories.json"}
    for f in ("movers_day.csv", "movers_week.csv", "movers_month.csv", "symbols.csv"):
        assert (out / "data" / f).read_text().count("\n") >= 2


def test_top_lists_are_penny_capped_sorted_and_carry_risk(built):
    ds, _, data = built
    lists = data["movers.json"]["lists"]
    assert set(lists) == {"day", "week", "month"}
    syms = {r[0]: r for r in data["symbols.json"]["rows"]}
    for name, rows in lists.items():
        assert 0 < len(rows) <= TOP_N
        assert all(r["band"] in ("under $1", "$1-5") for r in rows)          # penny = under $5
        chg = [r["chg"] for r in rows]
        assert chg == sorted(chg, reverse=True) and min(chg) > 0
        assert all(r["verdict"] for r in rows)                               # every row checked
    week = lists["week"]
    assert week[0]["verdict"] == "VETO" and week[0]["flags"]                 # planted pumps lead, flagged


def test_ryde_on_its_reference_day(built):
    """SC-001: RYDE ($17, not penny) is on the scan and VETO in the lookup set."""
    _, _, data = built
    f = data["symbols.json"]["fields"]
    ryde = dict(zip(f, next(r for r in data["symbols.json"]["rows"] if r[0] == "RYDE")))
    assert ryde["verdict"] == "VETO" and ryde["band"] == "$5-30" and ryde["scan_days"] >= 2
    latest = data["scan.json"]["sessions"][0]
    assert latest["session"] == "2024-09-06" and latest["hits"][0]["verdict"] == "VETO"
    assert any(h["s"] == "RYDE" for h in latest["hits"])


def test_no_absolute_prices_or_personal_data_by_default(built):
    """SC-004 / FR-004."""
    _, out, data = built
    assert data["meta.json"]["prices"] is False
    assert "close" not in data["symbols.json"]["fields"]
    blob = "".join(p.read_text() for p in (out / "data").iterdir())
    assert '"close"' not in blob and '"c0"' not in blob
    for word in ("account_number", "\"account\"", "average_cost", "\"quantity\"", "\"position\"", "token\""):
        assert word not in blob.lower(), word
    for r in data["movers.json"]["lists"]["week"]:
        if r["spark"]:
            assert r["spark"][0] == 100.0                                    # shape, not price


def test_prices_appear_only_when_enabled(built, tmp_path):
    ds, _, _ = built
    d = build_data(ds.store, ds, prices=True)
    assert d["meta.json"]["prices"] is True and "close" in d["symbols.json"]["fields"]
    assert "close" in d["movers.json"]["lists"]["day"][0]


def test_no_external_requests_in_the_app():
    """Only the share page may load Cloudflare Turnstile, and only when configured."""
    for f in WEB.glob("*"):
        if f.suffix not in (".html", ".js", ".css"):
            continue
        text = f.read_text()
        assert not re.search(r'<script[^>]+src="https?://', text), f
        assert not re.search(r'<link[^>]+href="https?://', text), f
        assert "@import" not in text and "fetch(\"http" not in text and "fetch(`http" not in text, f
        hosts = set(re.findall(r"https://([a-z0-9.-]+)", text)) - {"challenges.cloudflare.com"}
        if f.name in ("app.js", "stories.js", "quiz.js", "index.html", "app.css"):
            # links people can click are fine; anything else must be a regulator or GitHub page
            assert hosts <= {"www.sec.gov", "www.ic3.gov", "www.finra.org", "www.investor.gov", "www.irs.gov"}, (f, hosts)


def test_wording_describes_risk_not_fraud_or_advice():
    text = " ".join(f.read_text() for f in WEB.glob("*.js")) + (WEB / "index.html").read_text()
    low = text.lower()
    for bad in ("is a scam", "is a fraud", "strong buy", "buy now!", "guaranteed return", "guaranteed profit"):
        assert bad not in low
    assert "not investment advice" in low and "not a buy signal" in low
    assert "has not been found to be a fraud" in low


def test_meta_has_base_rates_and_counts(built):
    _, _, data = built
    m = data["meta.json"]
    assert m["base_rates"]["bracket"]["n"] == 61129 and m["base_rates"]["collapse"]["n_collapsed"] == 349
    assert m["data_session"] == "2024-09-06" and m["counts"]["risk_list"]["day"] <= TOP_N


def test_band_edges():
    assert band(0.99) == "under $1" and band(1.0) == "$1-5" and band(PENNY_MAX) == "$5-30" and band(31) == "over $30"


def test_build_is_atomic_and_repeatable(built, tmp_path):
    ds, _, _ = built
    out = tmp_path / "site"
    build_site(ds.store, ds, out)
    first = (out / "data" / "movers.json").read_text()
    build_site(ds.store, ds, out)
    assert (out / "data" / "movers.json").read_text() == first
    assert not (tmp_path / "site.tmp").exists() and not (tmp_path / "site.old").exists()


def test_site_reads_nothing_after_the_data_session(built):
    """The frame for session D is identical whether or not later sessions exist."""
    from server.site import market_frame
    ds, _, _ = built
    d = ds.store.recent_sessions("2024-09-06", 3)[0]
    a = market_frame(ds.store, d)
    ds2, _ = make_ds(now=NOW)
    uni = {s: [r for r in rows if r["date"] <= d] for s, rows in _universe().items()}
    refresh(ds2.store, ds2, FixtureSnapshots(uni), now=dt.datetime.fromisoformat(d).replace(hour=18, tzinfo=ET),
            backfill=200)
    b = market_frame(ds2.store, d)
    key = lambda rows: sorted((r["s"], round(r["c0"], 6), r["c1"], r["c5"]) for r in rows)
    assert key(a) == key(b)
