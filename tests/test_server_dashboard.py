"""Private dashboard page and its route (specs/004, T015)."""

import datetime as dt
import re

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("mcp")

from starlette.testclient import TestClient  # noqa: E402

from server.app import build_app  # noqa: E402
from server.config import Settings  # noqa: E402
from server.dashboard import build_page, write_page  # noqa: E402
from server.data import ET  # noqa: E402
from server.market import FixtureSnapshots  # noqa: E402
from server.providers import seed_fixtures  # noqa: E402
from server.scan import refresh  # noqa: E402
from tests.server_fixtures import make_ds  # noqa: E402

TOKEN = "d" * 40


@pytest.fixture(scope="module")
def scanned():
    now = dt.datetime(2024, 9, 6, 18, tzinfo=ET)
    ds, _ = make_ds(now=now)
    refresh(ds.store, ds, FixtureSnapshots({"RYDE": seed_fixtures()["RYDE"]}), now=now, backfill=200)
    return ds


def test_page_shows_the_hit_with_n_and_disclaimers(scanned):
    page = build_page(scanned.store)
    assert "RYDE" in page and "VETO" in page
    assert "N = " in page and "too few to judge" in page
    for must in ("Not a buy signal", "Not investment advice", "gate is not met"):
        assert must in page


def test_page_is_self_contained_and_small(scanned):
    page = build_page(scanned.store)
    assert len(page.encode()) < 1_000_000                                        # SC-004
    assert not re.search(r'(src|href)\s*=\s*"(https?:)?//', page)
    assert "<script" not in page and "@import" not in page
    assert "prefers-color-scheme: dark" in page and 'data-theme="dark"' in page


def test_page_has_no_personal_or_position_data(scanned):
    page = build_page(scanned.store).lower()
    for word in ("account", "average cost", "quantity", "p&l"):
        assert word not in page


def test_dashboard_route_needs_the_token(scanned, tmp_path):
    write_page(scanned.store, tmp_path)
    app = build_app(Settings(token=TOKEN, host="0.0.0.0", provider="fixture", data_dir=tmp_path), scanned)
    with TestClient(app, base_url="http://localhost:8765") as c:
        assert c.get("/dashboard/").status_code == 401
        r = c.get(f"/t/{TOKEN}/dashboard/")
        assert r.status_code == 200 and "RYDE" in r.text
        assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]


def test_dashboard_route_before_first_build_is_503(scanned, tmp_path):
    app = build_app(Settings(token=TOKEN, host="0.0.0.0", provider="fixture", data_dir=tmp_path / "empty"), scanned)
    with TestClient(app, base_url="http://localhost:8765") as c:
        assert c.get(f"/t/{TOKEN}/dashboard/").status_code == 503


def test_jobs_refresh_endpoint_is_token_gated_and_runs(scanned, tmp_path):
    calls = []
    app = build_app(Settings(token=TOKEN, host="0.0.0.0", provider="fixture", data_dir=tmp_path), scanned,
                    job=lambda: calls.append(1) or {"status": "ok"})
    with TestClient(app, base_url="http://localhost:8765") as c:
        assert c.post("/jobs/refresh").status_code == 401 and not calls
        r = c.post("/jobs/refresh", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.json() == {"status": "ok"} and calls == [1]
