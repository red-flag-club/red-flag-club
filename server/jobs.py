"""CLI for the Layer 2 jobs (spec 004). Read-only against any brokerage.

    python3 -m server.jobs scan [--backfill N] [--check-source] [--fixture]
    python3 -m server.jobs dashboard [--fixture]
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys

from server.config import Settings
from server.dashboard import write_page
from server.data import last_session


def _settings(fixture: bool) -> Settings:
    s = Settings.from_env()
    if fixture:
        s = dataclasses.replace(s, provider="fixture", scan_source="fixture")
    return s.validate()


def _via_server(s: Settings) -> int:
    """The running server holds the database (DuckDB allows one writer
    process): ask it to refresh instead."""
    import json
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{s.port}/jobs/refresh", method="POST", data=b"",
                                 headers={"Authorization": f"Bearer {s.token}"} if s.token else {})
    with urllib.request.urlopen(req, timeout=7200) as r:
        out = json.loads(r.read())
    print(out)
    return 0 if str(out.get("status", "")).startswith(("ok", "skipped")) else 1


def main(argv=None) -> int:
    from server.app import data_service, market_source
    from server.scan import BACKFILL_SESSIONS, refresh
    ap = argparse.ArgumentParser(prog="server.jobs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan")
    sc.add_argument("--backfill", type=int, default=BACKFILL_SESSIONS)
    sc.add_argument("--check-source", action="store_true")
    sc.add_argument("--fixture", action="store_true", help="offline demo data (RYDE, RETO)")
    db = sub.add_parser("dashboard")
    db.add_argument("--fixture", action="store_true")
    st = sub.add_parser("site", help="build the public community site into PD_DATA_DIR/site (or --out)")
    st.add_argument("--fixture", action="store_true")
    st.add_argument("--out")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = _settings(a.fixture)
    try:
        ds = data_service(s)
    except Exception as e:                                  # duckdb.IOException: lock held
        if "lock" not in str(e).lower():
            raise
        if a.cmd == "scan" and not a.check_source:
            print("the server is running and holds the database; asking it to refresh", file=sys.stderr)
            return _via_server(s)
        if a.cmd == "site":
            print("the server is running and holds the database; asking it to refresh (which rebuilds the site)",
                  file=sys.stderr)
            return _via_server(s)
        print("the server is running and holds the database; it rebuilds the page on every refresh",
              file=sys.stderr)
        return 0
    if a.cmd == "dashboard":
        print(write_page(ds.store, s.data_dir))
        return 0
    if a.cmd == "site":
        from pathlib import Path
        from server.site import build_site
        from server.app import site_options
        print(build_site(ds.store, ds, Path(a.out) if a.out else s.site_dir, **site_options(s)))
        return 0
    src = market_source(s)
    if src is None:
        print("PD_SCAN_SOURCE is off: set massive, payload or fixture", file=sys.stderr)
        return 2
    if a.check_source:
        from server.market import check_source
        print(check_source(src, last_session(ds.now())))
        return 0
    backfill = a.backfill
    if a.fixture:
        # the seed data covers 2023-2026; scan all of it
        backfill = max(backfill, 900)
    from server.app import after_refresh
    out = refresh(ds.store, ds, src, backfill=backfill, on_done=lambda: after_refresh(s, ds))
    print(out)
    return 0 if out.get("status", "").startswith(("ok", "skipped")) else 1


if __name__ == "__main__":
    sys.exit(main())
