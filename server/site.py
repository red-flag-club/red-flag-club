"""Public community site builder (spec 006).

Turns the DuckDB store into static JSON/CSV under <out>/data/ and copies the
single-page app from web/. Lists are risk lists, never pick lists: every row
carries its Layer 1 verdict and red flags, and meta.json carries the base
rates for buying after such runs.

Exported data never contains account, position or personal data, and — unless
the owner enables `prices` after checking the data licence — no absolute
prices: only percentages, price bands and shapes normalised to 100.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import shutil
from pathlib import Path

import server  # noqa: F401
import check_ticker as K

from server import ROOT, __version__
from server.bars import suspect_bad_prints, to_bars
from server.data import DataService
from server.outcomes import episodes, forward_metrics
from server.scan import CHECK_SESSIONS, MARKET_KEEP_SESSIONS, _possible_split
from server.store import Store, _now
from server.tools import GATE, NOTE

WEB = ROOT / "web"
BRAND = "Red Flag Club"


def stories_export() -> dict:
    """Approved, anonymised community stories (spec 007). The site workflow
    re-exports from the repo checkout so newly approved stories publish
    without rebuilding the container."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("pd_stories", ROOT / "scripts" / "stories.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.export()
PENNY_MAX = 5.0               # SEC penny-stock threshold
SMALL_CAP_MAX = 30.0          # the Layer 2 screen's ceiling; the lookup set
MIN_VALUE = 25_000.0          # average traded value over 5 sessions, $ — drops untradeable noise
TOP_N = 100
WINDOWS = {"day": 1, "week": 5, "month": 21}
SPARK = 30
SCAN_SESSIONS_EXPORT = 20

# The project's own research (research/FINDINGS.md, specs/001)
BASE_RATES = {
    "bracket": {"n": 61129, "win": 0.301, "breakeven": 0.40, "per_trade": -0.029,
                "rule": "buy the next open after a pump trigger, exit +20% / -10%"},
    "collapse": {"n_runs": 2841, "n_collapsed": 349,
                 "rule": ">=100% in <=10 sessions, then >=70% down within 20 sessions"},
}
DISCLAIMER = ("Not investment advice. Not a buy signal: these are risk lists. Patterns, not accusations — "
              "a stock on this page has not been found to be a fraud. Data can be wrong or late.")


def band(close: float | None) -> str | None:
    if close is None:
        return None
    return "under $1" if close < 1 else ("$1-5" if close < 5 else ("$5-30" if close <= 30 else "over $30"))


def _r(x, n=4):
    return None if x is None else round(x, n)


# ---------------------------------------------------------------- frame

def market_frame(store: Store, session: str) -> list[dict]:
    """One row per symbol with a bar on `session`: closes 1/5/21 sessions back,
    volume vs its 30-session average, 5-session average traded value. Reads
    nothing after `session`."""
    days = store.recent_sessions(session, 31)
    if not days or days[-1] != session:
        return []
    case = lambda col, n: f"max(CASE WHEN date = '{days[-1 - n]}' THEN {col} END)" if len(days) > n else "NULL"
    sql = (f"SELECT symbol, {case('c', 0)}, {case('c', 1)}, {case('c', 5)}, {case('c', 21)}, {case('v', 0)}, "
           f"avg(CASE WHEN date < ? THEN v END), avg(CASE WHEN date >= ? THEN c * v END) "
           f"FROM market_daily WHERE date >= ? AND date <= ? GROUP BY symbol")
    first5 = days[-5] if len(days) >= 5 else days[0]
    rows = store._q(sql, (session, first5, days[0], session))
    out = []
    for sym, c0, c1, c5, c21, v0, vavg, val5 in rows:
        if c0 is None:
            continue
        out.append({"s": sym, "c0": c0, "c1": c1, "c5": c5, "c21": c21,
                    "rv": (v0 / vavg) if vavg else None, "val5": val5 or 0.0})
    assert all(d <= session for d in days)
    return out


def _chg(r: dict, n: int) -> float | None:
    base = r.get({1: "c1", 5: "c5", 21: "c21"}[n])
    return r["c0"] / base - 1 if base else None


# ---------------------------------------------------------------- verdicts

def _flags_from_check(res: dict, bars) -> list[str]:
    f = res.get("facts", {})
    flags = list(res.get("vetoes", []))
    flags += [x for x in f.get("structural_flags", []) if x not in flags]
    if res["verdict"] == "INSUFFICIENT DATA":
        flags.append("fewer than 30 sessions of trading history (new listing?)")
    if suspect_bad_prints(bars):
        flags.append("one-day price spike on thin volume (possible bad print)")
    return flags


def verdicts(store: Store, ds: DataService, session: str, symbols: list[str]) -> dict[str, dict]:
    """Layer 1 check as of `session` for each symbol, from the scan window
    (60 sessions) and SEC filings filed <= session."""
    if not symbols:
        return {}
    hist = store.market_history(session, CHECK_SESSIONS, symbols=symbols)
    splits = store.splits_until(session)
    out = {}
    for sym in symbols:
        rows = hist.get(sym, [])
        cut = max((d for d in splits.get(sym, []) if d <= session), default=None)
        if cut:
            rows = [r for r in rows if r["date"] >= cut]
        bars = to_bars(rows)
        filings, _ = ds.filings(sym, session)
        res = K.check(sym, bars, session, filings=filings, position=0.0)
        flags = _flags_from_check(res, bars)
        if cut:
            flags.append(f"stock split on {cut}: earlier prices not compared")
        elif _possible_split([b.c for b in bars[-SPARK:]]):
            flags.append("price jump that may be a split")
        why = (res.get("vetoes") or res.get("cautions") or res.get("reasons") or ["no rule fired"])[0]
        out[sym] = {"verdict": res["verdict"], "flags": flags, "why": why,
                    "closes": [b.c for b in bars[-SPARK:]], "split": bool(cut)}
    return out


def spark(closes: list[float]) -> list[float]:
    if len(closes) < 2 or not closes[0]:
        return []
    return [round(c / closes[0] * 100, 2) for c in closes]


# ---------------------------------------------------------------- build

def build_data(store: Store, ds: DataService, *, now: dt.datetime | None = None, prices: bool = False,
               discussions_url: str | None = None, site_url: str | None = None,
               stories_submit_url: str | None = None, turnstile_sitekey: str | None = None) -> dict[str, object]:
    scanned = sorted(store.scanned_sessions())
    loaded = store.sessions("loaded")
    session = loaded[-1] if loaded else None
    frame = market_frame(store, session) if session else []
    recent_scan = scanned[-SCAN_SESSIONS_EXPORT:]
    scan_rows = store.scan_rows(since=recent_scan[0]) if recent_scan else []
    all_log = store.scan_rows()
    first_seen: dict[str, str] = {}
    for r in all_log:
        first_seen.setdefault(r["symbol"], r["session"])
    scan_days: dict[str, int] = {}
    for r in scan_rows:
        scan_days[r["symbol"]] = scan_days.get(r["symbol"], 0) + 1

    # risk lists
    penny = [r for r in frame if r["c0"] < PENNY_MAX and r["val5"] >= MIN_VALUE]
    picked: dict[str, list[dict]] = {}
    for name, n in WINDOWS.items():
        ranked = sorted((r for r in penny if (_chg(r, n) or 0) > 0), key=lambda r: -_chg(r, n))
        picked[name] = ranked[:TOP_N * 2]                     # spare rows for split-guarded drops
    last_hits = [r["symbol"] for r in scan_rows if r["session"] == (scanned[-1] if scanned else None)]
    need = sorted({r["s"] for rows in picked.values() for r in rows} | set(last_hits))
    v = verdicts(store, ds, session, need) if session else {}

    def row(r: dict, n: int) -> dict:
        vv = v.get(r["s"], {})
        out = {"s": r["s"], "band": band(r["c0"]), "chg": _r(_chg(r, n)), "rv": _r(r["rv"], 2),
               "verdict": vv.get("verdict"), "flags": vv.get("flags", []), "why": vv.get("why"),
               "scan_days": scan_days.get(r["s"], 0), "spark": spark(vv.get("closes", []))}
        if prices:
            out["close"] = r["c0"]
        return out

    lists = {}
    for name, n in WINDOWS.items():
        rows = [row(r, n) for r in picked[name] if not v.get(r["s"], {}).get("split")]
        lists[name] = rows[:TOP_N]

    # lookup / analytics index
    fields = ["s", "band", "r1", "r5", "r21", "rv", "verdict", "flags", "why", "scan_days", "first_seen"]
    if prices:
        fields.append("close")
    sym_rows = []
    for r in sorted(frame, key=lambda r: r["s"]):
        if r["c0"] > SMALL_CAP_MAX:
            continue
        vv = v.get(r["s"], {})
        rec = [r["s"], band(r["c0"]), _r(_chg(r, 1)), _r(_chg(r, 5)), _r(_chg(r, 21)), _r(r["rv"], 2),
               vv.get("verdict"), vv.get("flags", []), vv.get("why"), scan_days.get(r["s"], 0), first_seen.get(r["s"])]
        if prices:
            rec.append(r["c0"])
        sym_rows.append(rec)

    # scan history
    by_session: dict[str, list[dict]] = {}
    for r in scan_rows:
        by_session.setdefault(r["session"], []).append(
            {"s": r["symbol"], "reason": r["reason"], "verdict": r["verdict"], "r5": r["ret_5"],
             "r21": r["ret_21"], "flags": [f for f in (r["flags"] or "").split(",") if f],
             "why": (r["reasons"] or "").split("; ")[0]})
    scan = {"sessions": [{"session": s, "hits": sorted(by_session.get(s, []),
                                                        key=lambda h: (h["verdict"] != "VETO", -(h["r5"] or 0)))}
                         for s in reversed(recent_scan)]}

    # outcomes
    eps = {(e["symbol"], e["first_logged"]): e for e in episodes(store)}
    ep_rows = []
    for o in store.outcomes():
        e = eps.get((o["symbol"], o["first_logged"]))
        if not e:
            continue
        ep_rows.append({"s": o["symbol"], "first_logged": o["first_logged"], "label": o["label"],
                        "peak_date": o["peak_date"], "drawdown": o["drawdown"],
                        "vetoed": any(vd == "VETO" for _, vd in e["rows"]), "backfilled": e["backfilled"],
                        "days_logged": len(e["rows"])})
    ep_rows.sort(key=lambda x: x["first_logged"], reverse=True)
    fm = forward_metrics(store)
    outcomes = {"forward": fm["forward"], "backfilled": fm["backfilled"], "episodes": ep_rows[:500]}

    from server.data import CACHE_DAYS
    meta = {
        "version": __version__, "built_at": (now or _now()).strftime("%Y-%m-%dT%H:%MZ"),
        "data_session": session, "last_scanned": scanned[-1] if scanned else None, "prices": prices,
        "counts": {"symbols": len(sym_rows), "penny_tradeable": len(penny),
                   "risk_list": {k: len(x) for k, x in lists.items()},
                   "scan_hits_latest": len(last_hits), "sessions_scanned": len(scanned)},
        "rules": {"penny_max": PENNY_MAX, "min_value": MIN_VALUE, "top_n": TOP_N,
                  "screen": "close $1-$30 and up >= 50% over 5 or 21 sessions"},
        "retention": f"market data: last {MARKET_KEEP_SESSIONS} sessions; per-symbol cache {CACHE_DAYS} days",
        "gate": GATE, "base_rates": BASE_RATES, "disclaimer": DISCLAIMER, "note": NOTE,
        "discussions_url": discussions_url, "site_url": site_url, "brand": BRAND,
        "stories_submit_url": stories_submit_url, "turnstile_sitekey": turnstile_sitekey,
    }
    return {"meta.json": meta,
            "movers.json": {"session": session, "penny_max": PENNY_MAX, "min_value": MIN_VALUE, "lists": lists},
            "symbols.json": {"session": session, "fields": fields, "rows": sym_rows},
            "scan.json": scan, "outcomes.json": outcomes, "stories.json": stories_export()}


def _csv(fields: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(fields)
    for r in rows:
        w.writerow(["; ".join(x) if isinstance(x, list) else x for x in r])
    return buf.getvalue()


def write_site(data: dict, out: Path) -> Path:
    """Build into a sibling temp dir, then swap, so a publish never copies a
    half-written site."""
    out = Path(out)
    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(WEB, tmp, ignore=shutil.ignore_patterns("*.test.mjs", "node_modules", "package.json"))
    site_url = data["meta.json"].get("site_url") or ""
    if site_url and not site_url.endswith("/"):
        site_url += "/"
    index = tmp / "index.html"
    index.write_text(index.read_text().replace("{{SITE_URL}}", site_url))
    d = tmp / "data"
    d.mkdir()
    for name, obj in data.items():
        (d / name).write_text(json.dumps(obj, separators=(",", ":"), default=str))
    lists = data["movers.json"]["lists"]
    cols = ["s", "band", "chg", "rv", "verdict", "flags", "why", "scan_days"] + (
        ["close"] if data["meta.json"]["prices"] else [])
    for name, rows in lists.items():
        (d / f"movers_{name}.csv").write_text(_csv(cols, [[r.get(c) for c in cols] for r in rows]))
    sy = data["symbols.json"]
    (d / "symbols.csv").write_text(_csv(sy["fields"], sy["rows"]))
    (tmp / ".nojekyll").write_text("")
    old = out.with_name(out.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if out.exists():
        out.rename(old)
    tmp.rename(out)
    if old.exists():
        shutil.rmtree(old)
    return out


def build_site(store: Store, ds: DataService, out: Path, **kw) -> Path:
    return write_site(build_data(store, ds, **kw), out)
