"""Tool logic, independent of MCP (contracts/tools.md). Every verdict comes
from src/check_ticker.check() and scripts/monitor.holding_report() —
imported, not re-implemented (FR-002) — so the RYDE and DJT reference cases
hold here too.

No tool places, changes or cancels an order; there is no brokerage client.
"""

from __future__ import annotations

import re
import statistics as st
from typing import Sequence

import server  # noqa: F401  (sys.path set-up)
import check_ticker as K
from scripts import monitor as M

from server.bars import suspect_bad_prints, to_bars
from server.data import DataService, DataUnavailable, FutureDate, last_session
from server.providers import NoData

NOTE = "Not a buy signal. No order is placed."
GATE = ("Layer 1 is a checklist aid, not a validated classifier: its walk-forward gate is not met "
        "(recall 0.783, FP 0.782, N=295/400).")
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
MAX_SCAN = 50
BENCHMARK = "SPY"
HORIZONS = (5, 20, 60)


class ToolError(ValueError):
    """A refusal, returned to the client as an error result."""


def _symbol(s: str) -> str:
    sym = (s or "").strip().upper()
    if not SYMBOL_RE.match(sym):
        raise ToolError(f"invalid symbol {s!r}")
    return sym


def _as_of(ds: DataService, as_of: str | None) -> str:
    try:
        return ds.resolve_as_of(as_of)
    except (FutureDate, ValueError) as e:
        raise ToolError(str(e)) from e


def _benchmark(ds: DataService, as_of: str):
    try:
        rows, _ = ds.bars(BENCHMARK, as_of)
        return to_bars(rows)
    except (NoData, DataUnavailable):
        return None


def _no_data(symbol: str, as_of: str, why: str) -> dict:
    return {"symbol": symbol, "as_of": as_of, "verdict": "NO DATA", "vetoes": [], "cautions": [],
            "reason": why, "note": NOTE, "text": f"{symbol} as of {as_of} — NO DATA: {why}. {NOTE}"}


# ---------------------------------------------------------------- check_ticker

def _run_check(ds: DataService, sym: str, as_of: str, *, position_usd: float, account_usd: float,
               fundamentals: dict | None, earnings: Sequence[dict] | None, benchmark=None):
    """(check result, provenance, bars). Raises NoData / DataUnavailable."""
    rows, prov = ds.bars(sym, as_of)
    if not rows:
        raise NoData(sym)
    bars = to_bars(rows)
    filings, sec_status = ds.filings(sym, as_of)
    current = as_of >= last_session(ds.now())
    fu = fundamentals if (fundamentals and current) else None
    r = K.check(sym, bars, as_of, fundamentals=fu, filings=filings, earnings=earnings,
                benchmark=benchmark, position=position_usd, account=account_usd)
    prov = {**prov, "first_date": rows[0]["date"], "last_date": rows[-1]["date"],
            "splits": [x["date"] for x in rows if (x.get("split_factor") or 1.0) != 1.0],
            "suspect_bad_prints": suspect_bad_prints(bars), "sec": sec_status,
            "fundamentals": ("caller-supplied, current" if fu else
                             "ignored: not point-in-time for a past date" if fundamentals else "none")}
    return r, prov, bars


def _summary(r: dict) -> dict:
    f = r.get("facts", {})
    return {k: f.get(k) for k in ("last_close", "last_date", "ret_1m", "ret_3m", "vs_sma200", "vol_annual",
                                  "from_high", "structural_score", "structural_unknown", "last_sec_filing")}


def _text(r: dict, prov: dict) -> str:
    lines = [K.render(r)]
    d = (f"  data: {prov['bars']} bars {prov['first_date']}..{prov['last_date']} from {prov['source']}"
         f"{' (split-adjusted)' if prov['adjusted'] else ''}; {prov['dropped_on_fetch']} dropped as gap-fill/placeholder"
         + ("" if prov.get("stored", True) else "; fetched for this answer, not stored (older than the cache window)"))
    lines.append(d)
    if prov["splits"]:
        lines.append(f"  splits in window: {', '.join(prov['splits'])}")
    if prov["suspect_bad_prints"]:
        lines.append(f"  suspect bad prints (kept): {', '.join(prov['suspect_bad_prints'])}")
    lines.append(f"  SEC filings: {prov['sec']}; fundamentals: {prov['fundamentals']}")
    lines.append(f"  {GATE}")
    return "\n".join(lines)


def check_ticker(ds: DataService, symbol: str, as_of: str | None = None, position_usd: float = 250.0,
                 account_usd: float = 1000.0, fundamentals: dict | None = None,
                 earnings: list | None = None, detail: bool = False, *, tool: str = "check_ticker") -> dict:
    sym, day = _symbol(symbol), _as_of(ds, as_of)
    if position_usd < 0 or account_usd <= 0:
        raise ToolError("position_usd must be >= 0 and account_usd > 0")
    try:
        r, prov, _ = _run_check(ds, sym, day, position_usd=position_usd, account_usd=account_usd,
                                fundamentals=fundamentals, earnings=earnings, benchmark=_benchmark(ds, day))
    except NoData:
        out = _no_data(sym, day, "the data provider has no daily bars for this symbol up to this date")
        ds.store.log_check(tool, sym, day, out["verdict"])
        return out
    ds.store.log_check(tool, sym, day, r["verdict"])
    out = {"symbol": sym, "as_of": day, "verdict": r["verdict"], "vetoes": r.get("vetoes", []),
           "cautions": r.get("cautions", r.get("reasons", [])), "summary": _summary(r), "data": prov,
           "note": NOTE, "text": _text(r, prov) if "facts" in r else K.render(r) + f"\n  {NOTE}"}
    if detail:
        out["facts"] = r.get("facts")
    return out


# ---------------------------------------------------------------- was_i_pumped

def was_i_pumped(ds: DataService, symbol: str, buy_date: str) -> dict:
    sym, day = _symbol(symbol), _as_of(ds, buy_date)
    at = check_ticker(ds, sym, day, tool="was_i_pumped")     # data <= buy_date only
    if at["verdict"] == "NO DATA" or at["data"]["last_date"] < _days_before(day, 7):
        raise ToolError(f"no daily bars for {sym} on or shortly before {day}")
    buy = at["summary"].get("last_close") or ds.store.bars(sym, _days_before(day, 10), day)[-1]["c"]
    after = ds.hindsight(sym, day)                           # outcome only, never fed back
    hs: dict = {"buy_close": buy, "sessions_since": len(after)}
    for n in HORIZONS:
        hs[f"ret_{n}"] = round(after[n - 1]["c"] / buy - 1, 4) if len(after) >= n else "not yet"
    if after:
        pk = max(after, key=lambda b: b["h"])
        tr = min(after, key=lambda b: b["l"])
        hs.update({"peak_after": pk["h"], "peak_date": pk["date"],
                   "max_drawdown_from_buy": round(tr["l"] / buy - 1, 4), "trough_date": tr["date"],
                   "last_close": after[-1]["c"], "last_date": after[-1]["date"]})
    pct = lambda x: x if isinstance(x, str) else f"{x:+.1%}"
    lines = [f"{sym}, bought {day}: at the time — {at['verdict']}"]
    lines += [f"  VETO: {v}" for v in at["vetoes"]] + [f"  caution: {c}" for c in at["cautions"]]
    lines.append(f"  (verdict uses only data dated on or before {day}"
                 + ("; history fetched for this answer, not stored)" if not at["data"].get("stored", True) else ")"))
    lines.append(f"HINDSIGHT (not used for the verdict), from the {day} close {buy}:")
    lines.append("  " + ", ".join(f"{n} sessions {pct(hs[f'ret_{n}'])}" for n in HORIZONS))
    if after:
        lines.append(f"  peak {hs['peak_after']} on {hs['peak_date']}; worst {pct(hs['max_drawdown_from_buy'])} "
                     f"on {hs['trough_date']}; last {hs['last_close']} ({hs['last_date']})")
    lines.append(f"  {NOTE}")
    return {"symbol": sym, "buy_date": day, "at_the_time": {k: v for k, v in at.items() if k != "text"},
            "hindsight": hs, "note": NOTE, "text": "\n".join(lines)}


def _days_before(d: str, n: int) -> str:
    import datetime as dt
    return (dt.date.fromisoformat(d) - dt.timedelta(days=n)).isoformat()


# ---------------------------------------------------------------- pump_scan

def _run_up(c: Sequence[float], n: int) -> float | None:
    if len(c) <= n:
        return None
    lo = min(c[-(n + 1):])
    return round(c[-1] / lo - 1, 4) if lo > 0 else None


def pump_scan(ds: DataService, symbols: Sequence[str], as_of: str | None = None) -> dict:
    if not symbols:
        raise ToolError("symbols is empty")
    if len(symbols) > MAX_SCAN:
        raise ToolError(f"at most {MAX_SCAN} symbols per scan, got {len(symbols)}")
    day = _as_of(ds, as_of)
    syms = list(dict.fromkeys(_symbol(s) for s in symbols))
    bench = _benchmark(ds, day)
    rows = []
    for sym in syms:
        try:
            r, prov, bars = _run_check(ds, sym, day, position_usd=250.0, account_usd=1000.0,
                                       fundamentals=None, earnings=None, benchmark=bench)
        except NoData:
            rows.append({"symbol": sym, "verdict": "NO DATA", "reason": "no bars"})
            continue
        except DataUnavailable as e:
            rows.append({"symbol": sym, "verdict": "UNAVAILABLE", "reason": str(e)})
            continue
        ds.store.log_check("pump_scan", sym, day, r["verdict"])
        c, v = [b.c for b in bars], [b.v for b in bars]
        base = st.median(v[-21:-1]) if len(v) > 21 else None
        reason = (r.get("vetoes") or r.get("cautions") or r.get("reasons") or ["—"])[0]
        rows.append({"symbol": sym, "verdict": r["verdict"], "run_up_5": _run_up(c, 5), "run_up_10": _run_up(c, 10),
                     "volume_ratio_20": round(v[-1] / base, 1) if base else None, "last_close": c[-1],
                     "reason": reason})
    order = {"VETO": 0, "CAUTION": 1, "INSUFFICIENT DATA": 2, "NO FLAGS": 3, "UNAVAILABLE": 4, "NO DATA": 5}
    rows.sort(key=lambda x: (order.get(x["verdict"], 9), -(x.get("run_up_10") or 0)))
    pct = lambda x: "n/a" if x is None else f"{x:+.0%}"
    lines = [f"pump_scan as of {day}: {len(rows)} symbols, "
             f"{sum(r['verdict'] == 'VETO' for r in rows)} VETO", "",
             "| Symbol | Verdict | 5-session | 10-session | Vol x20d | Close | Reason |", "|---|---|---|---|---|---|---|"]
    for x in rows:
        lines.append(f"| {x['symbol']} | {x['verdict']} | {pct(x.get('run_up_5'))} | {pct(x.get('run_up_10'))} | "
                     f"{x.get('volume_ratio_20') or 'n/a'} | {x.get('last_close', 'n/a')} | {x['reason']} |")
    lines += ["", NOTE]
    return {"as_of": day, "rows": rows, "note": NOTE, "text": "\n".join(lines)}


# ---------------------------------------------------------------- monitor_digest

def monitor_digest(ds: DataService, positions: Sequence[dict], orders: Sequence[dict] | None = None,
                   as_of: str | None = None) -> dict:
    """Layer 3 + check alerts on positions the caller passes in. Only symbol,
    quantity and average cost are read; nothing from the request is stored
    or logged (FR-009)."""
    day = _as_of(ds, as_of)
    clean = [{"symbol": p.get("symbol"), "quantity": p.get("quantity") or p.get("shares"),
              "average_cost": p.get("average_cost") or p.get("average_buy_price")}
             for p in positions or [] if isinstance(p, dict)]
    pos = M.parse_positions(clean)
    ords = M.parse_orders(list(orders or []))
    bench = _benchmark(ds, day)
    out, skipped = [], []
    for p in pos:
        try:
            sym = _symbol(p["symbol"])
            rows, _ = ds.bars(sym, day)
        except (ToolError, NoData, DataUnavailable) as e:
            skipped.append(f"{p['symbol']}: {e or 'no data'}")
            continue
        bars = to_bars(rows)
        if not bars or p["quantity"] * bars[-1].c < M.DUST_USD:
            continue
        filings, _ = ds.filings(sym, day)
        h = M.holding_report(p, bars, ords, day, extra={"filings": filings}, benchmark=bench)
        out.append({"symbol": sym, "quantity": h["quantity"], "average_cost": h["average_cost"],
                    "last_close": h["last_close"], "value": h["value"], "unrealized_pnl": h["unrealized_pnl"],
                    "unrealized_pct": h["unrealized_pct"], "verdict": h["check"]["verdict"],
                    "alerts": h["alerts"]})
    out.sort(key=lambda h: (-len(h["alerts"]), h["symbol"]))
    n = sum(len(h["alerts"]) for h in out)
    lines = [f"Monitor {day}: {len(out)} holdings, {n} alerts. Read-only: no orders were placed or changed."]
    for h in out:
        pnl = "" if h["unrealized_pnl"] is None else f" P&L ${h['unrealized_pnl']:+,.0f} ({h['unrealized_pct']:+.0%})"
        lines.append(f"- {h['symbol']} {h['verdict']} ${h['value'] or 0:,.0f}{pnl}"
                     + ("".join(f"\n    {a}" for a in h["alerts"]) if h["alerts"] else ""))
    if skipped:
        lines.append("skipped: " + "; ".join(skipped))
    lines.append(NOTE)
    return {"as_of": day, "holdings": out, "alert_count": n, "skipped": skipped,
            "note": "Read-only: no orders were placed or changed. " + NOTE, "text": "\n".join(lines)}


# ---------------------------------------------------------------- data_status

LIMITS = {"tiingo": "~50 requests/hour, 500 unique symbols/month (free tier; verify on tiingo.com)",
          "massive": "5 requests/minute, 2 years of history (free tier)",
          "brokerage-payload": "offline files", "fixture": "offline fixtures"}


def data_status(ds: DataService) -> dict:
    u = ds.store.usage(ds.provider.name)
    from server.data import CACHE_DAYS, IDLE_DAYS
    from server.scan import MARKET_KEEP_SESSIONS
    out = {"provider": ds.provider.name, "limits": LIMITS.get(ds.provider.name, ""),
           "sec_configured": ds.sec is not None, "last_session": last_session(ds.now()),
           "db_path": ds.store.path, "cache_window_start": ds.window_start(),
           "retention": (f"per-symbol bars: {CACHE_DAYS} days, evicted after {IDLE_DAYS} idle days; "
                         f"market scan: last {MARKET_KEEP_SESSIONS} sessions; older history fetched per "
                         "question and not stored; scan log, outcomes and filings kept"), **u}
    size = f"{u['db_bytes'] / 1e6:.1f} MB" if u.get("db_bytes") else "in memory"
    out["text"] = (f"provider {out['provider']} ({out['limits']}); {u['symbols_cached']} symbols / "
                   f"{u['bars_cached']} bars cached; {u['calls_last_hour']} provider calls in the last hour, "
                   f"{u['unique_symbols_this_month']} unique symbols this month; SEC "
                   f"{'configured' if out['sec_configured'] else 'not configured'}; last session {out['last_session']}.\n"
                   f"storage: {size}; market scan {u['market_sessions']} sessions; scan log {u['scan_log_rows']} rows"
                   f"{' since ' + u['scan_log_since'] if u['scan_log_since'] else ''}.\nretention: {out['retention']}.")
    return out


# ---------------------------------------------------------------- Layer 2 (spec 004)

MAX_SCAN_ROWS = 200
ON_SCAN_WINDOW = 20


def _forward_summary(store) -> dict:
    from server.outcomes import forward_metrics
    f = forward_metrics(store)["forward"]
    f["note"] = ("forward rows only (logged at the time, never backfilled); "
                 + ("enough to judge" if f["enough"] else "too few to judge yet (< 30 each side)"))
    return f


def scan_latest(ds: DataService, session: str | None = None, limit: int = 25) -> dict:
    if not 1 <= limit <= MAX_SCAN_ROWS:
        raise ToolError(f"limit must be 1..{MAX_SCAN_ROWS}")
    scanned = sorted(ds.store.scanned_sessions())
    if not scanned:
        raise ToolError("no session has been scanned yet (the scan runs after the close; see data_status)")
    day = session or scanned[-1]
    if day not in scanned:
        raise ToolError(f"{day} has not been scanned")
    rows = ds.store.scan_rows(session=day)
    order = {"VETO": 0, "CAUTION": 1, "INSUFFICIENT DATA": 2, "NO FLAGS": 3}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), -(r["ret_5"] or 0)))
    keep = ["symbol", "close", "ret_5", "ret_21", "rel_vol_30", "verdict", "reason", "flags"]
    out_rows = [{k: r[k] for k in keep} for r in rows[:limit]]
    fwd = _forward_summary(ds.store)
    pct = lambda x: "n/a" if x is None else f"{x:+.0%}"
    lines = [f"Scan {day}: {len(rows)} hits, {sum(r['verdict'] == 'VETO' for r in rows)} VETO "
             f"(screen: $1-$30 and +50% over 5 or 21 sessions; float/market cap not filtered).", "",
             "| Symbol | Verdict | 5-session | 21-session | Vol x30d | Close | Flags |", "|---|---|---|---|---|---|---|"]
    for r in out_rows:
        lines.append(f"| {r['symbol']} | {r['verdict']} | {pct(r['ret_5'])} | {pct(r['ret_21'])} | "
                     f"{r['rel_vol_30'] or 'n/a'} | {r['close']} | {r['flags'] or '—'} |")
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit} more (raise limit)")
    lines += ["", f"Forward check of Layer 1: {fwd['collapsed']} collapsed, {fwd['no_collapse']} did not, "
                  f"{fwd['pending']} pending; recall {fwd['recall']}, FP rate {fwd['fp_rate']} — {fwd['note']}.",
              NOTE]
    return {"session": day, "n_hits": len(rows), "n_veto": sum(r["verdict"] == "VETO" for r in rows),
            "rows": out_rows, "forward": fwd, "note": NOTE, "text": "\n".join(lines)}


def is_pumping(ds: DataService, symbol: str) -> dict:
    """PLAN.md L2.3: is this symbol on the scan, and what does Layer 1 say."""
    sym = _symbol(symbol)
    scanned = sorted(ds.store.scanned_sessions())
    last = scanned[-1] if scanned else None
    window = scanned[-ON_SCAN_WINDOW:]
    rows = ds.store.scan_rows(symbol=sym)
    recent = [r for r in rows if r["session"] in set(window)]
    chk = check_ticker(ds, sym, tool="is_pumping")
    out = {"symbol": sym, "last_session": last, "on_scan_today": bool(last and any(r["session"] == last for r in rows)),
           "days_on_scan": len(recent), "first_seen": rows[0]["session"] if rows else None,
           "last_seen": rows[-1]["session"] if rows else None,
           "recent": [{"session": r["session"], "reason": r["reason"], "verdict": r["verdict"]} for r in recent],
           "check": {k: v for k, v in chk.items() if k != "text"}, "note": NOTE}
    if not scanned:
        head = f"{sym}: the scan has not run yet, so on-scan status is unknown."
    elif not rows:
        head = f"{sym}: never on the scan (scanned {len(scanned)} sessions up to {last})."
    else:
        head = (f"{sym}: on the scan {len(recent)} of the last {len(window)} sessions"
                f"{' including ' + last if out['on_scan_today'] else ''}; first seen {out['first_seen']}, "
                f"last seen {out['last_seen']}.")
    out["text"] = head + "\n" + chk["text"] + f"\n{NOTE}"
    return out
