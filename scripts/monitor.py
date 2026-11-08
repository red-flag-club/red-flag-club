"""
Daily monitor — Layer 1 checks + Layer 3 position rules in one digest.
Read-only: it reads positions and orders and never places, changes or cancels
an order.

    python3 scripts/monitor.py --as-of 2026-10-15 \
        --historicals PAYLOAD... --transcript SESSION.jsonl [--watchlist data/watchlist.txt]

Before each run a Claude agent calls the read-only brokerage MCP tools:
  get_equity_positions, get_equity_orders   (your holdings and order history)
  get_equity_historicals                    (~14 months daily, holdings +
                                             watchlist + SPY; spills to a file)
  get_equity_fundamentals, get_sec_filing_index, get_earnings_results
                                            (per symbol)
Small responses are read from the session transcript (--transcript), or from
--positions / --orders JSON files.

For each holding the digest reports:
  - the Layer 1 check (VETO / CAUTION / NO FLAGS) on the current position size
  - EXIT RULE   closed below its 200-day average
  - TIME STOP   Layer 3 L3.1: a VETO name (pump profile or FINRA 22-25
                score >= 4/6) held N sessions past its
                first entry (later buys do not reset the clock)
  - EARNINGS    report within EARNINGS_ALERT_DAYS, with the typical move in $
  - ABANDONED   Layer 3 L3.4: last order a dead sell, >= 30 days, no replacement
  - unrealised P&L and the 1-in-100 bad week in dollars
Watchlist symbols get the Layer 1 check only. Output: results/monitor/<date>.md
and an append-only results/monitor/log.jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import check_ticker as K  # noqa: E402
from src.layer3 import Order as L3Order, abandoned, time_stop_date, TIME_STOP_SESSIONS  # noqa: E402

OUT = ROOT / "results" / "monitor"
EARNINGS_ALERT_DAYS = 7
DUST_USD = 1.0             # positions worth less than this are leftovers, not holdings
LOSS_ALERT = 0.15          # 15% below average cost


def _f(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# parsing broker payloads (tolerant of field-name variants)
# --------------------------------------------------------------------------

def parse_positions(data: dict | list, account: str | None = None) -> list[dict]:
    rows = data.get("positions") or data.get("results") or [] if isinstance(data, dict) else data
    out = []
    for r in rows:
        sym = r.get("symbol") or (r.get("instrument") or {}).get("symbol")
        qty = _f(r.get("quantity") or r.get("shares"))
        cost = _f(r.get("average_buy_price") or r.get("average_cost") or r.get("avg_cost"))
        if sym and qty:
            out.append({"symbol": sym.upper(), "quantity": qty,
                        "average_cost": cost if cost and cost > 0 else None, "account": account})
    return out


def mask(account: str | None) -> str:
    return f"••{account[-4:]}" if account else "—"


def _date(x) -> str | None:
    return x[:10] if isinstance(x, str) and len(x) >= 10 else None


def parse_orders(data: dict | list) -> list[dict]:
    rows = data.get("orders") or data.get("results") or [] if isinstance(data, dict) else data
    out = []
    for r in rows:
        sym = r.get("symbol") or (r.get("instrument") or {}).get("symbol")
        if not sym:
            continue
        state = (r.get("state") or "").lower()
        if state.startswith("partially_filled") and (_f(r.get("cumulative_quantity")) or 0) > 0:
            state = "filled"            # the filled part is a real buy or sell
        placed = _date(r.get("created_at"))
        closed = _date(r.get("last_transaction_at") or r.get("updated_at")) if state in (
            "filled", "cancelled", "canceled", "rejected", "failed", "expired") else None
        out.append({"id": r.get("id"), "symbol": sym.upper(), "side": (r.get("side") or "").lower(),
                    "state": "cancelled" if state == "canceled" else state,
                    "placed": placed, "closed": closed,
                    "price": _f(r.get("average_price") or r.get("price")),
                    "quantity": _f(r.get("cumulative_quantity") or r.get("quantity"))})
    return [o for o in out if o["placed"]]


def first_entry(symbol: str, orders: Sequence[dict]) -> str | None:
    """Date of the first filled buy since the last filled sell (the start of
    the current holding period)."""
    mine = sorted((o for o in orders if o["symbol"] == symbol and o["state"] == "filled"),
                  key=lambda o: o["closed"] or o["placed"])
    start = None
    for o in mine:
        d = o["closed"] or o["placed"]
        if o["side"] == "buy" and start is None:
            start = d
        elif o["side"] == "sell":
            start = None
    return start


def l3_orders(symbol: str, orders: Sequence[dict]) -> list[L3Order]:
    return [L3Order(o["placed"], o["side"], o["state"] if o["state"] in
                    ("filled", "cancelled", "expired") else "open", o["closed"])
            for o in orders if o["symbol"] == symbol and o["side"] in ("buy", "sell")]


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------

def holding_report(pos: dict, bars, orders: Sequence[dict], as_of: str, *,
                   extra: dict | None = None, benchmark=None, account: float = K.ACCOUNT) -> dict:
    sym = pos["symbol"]
    if any(b.date > as_of for b in bars):
        raise K.LookaheadError(f"{sym}: bar after {as_of}")
    last = bars[-1].c if bars else None
    value = round(pos["quantity"] * last, 2) if last else None
    chk = K.check(sym, bars, as_of, position=value or 0.0, account=account,
                  benchmark=benchmark, **(extra or {}))
    alerts = []
    f = chk.get("facts", {})
    if f.get("sma200") and last < f["sma200"]:
        alerts.append(f"EXIT RULE: closed {last:.2f}, below its 200-day average {f['sma200']:.2f}")
    entry = first_entry(sym, orders)
    ts = None
    if entry and bars:
        sessions = [b.date for b in bars]
        if entry in sessions:
            ts = time_stop_date(entry, sessions + [], TIME_STOP_SESSIONS)
            if chk["verdict"] == "VETO" and ts and ts <= as_of:
                alerts.append(f"TIME STOP: {chk['verdict']} name held since {entry}; "
                              f"Layer 3 exit was due {ts}")
    ne = f.get("next_earnings")
    if ne and ne["days"] <= EARNINGS_ALERT_DAYS:
        gap = f.get("avg_abs_earnings_move")
        alerts.append(f"EARNINGS in {ne['days']} days ({ne['date']} {ne['timing'] or ''})"
                      + (f"; typical move ±${gap * value:,.0f} on this position" if gap and value else ""))
    ab = abandoned(l3_orders(sym, orders), as_of)
    if ab:
        alerts.append(f"ABANDONED: {ab['reason']}")
    pnl = pnl_pct = None
    if pos.get("average_cost") and last:
        pnl = round((last - pos["average_cost"]) * pos["quantity"], 2)
        pnl_pct = round(last / pos["average_cost"] - 1, 4)
        if pnl_pct <= -LOSS_ALERT:
            alerts.append(f"LOSS: {pnl_pct:.0%} below your average cost")
    for v in chk.get("vetoes", []):
        alerts.append(f"VETO: {v}")
    return {"symbol": sym, "kind": "holding", "account": pos.get("account"), "quantity": pos["quantity"],
            "average_cost": pos.get("average_cost"), "last_close": last, "value": value,
            "unrealized_pnl": pnl, "unrealized_pct": pnl_pct, "first_entry": entry,
            "time_stop_date": ts, "alerts": alerts, "check": chk}


def watch_report(sym: str, bars, as_of: str, *, extra: dict | None = None, benchmark=None,
                 position: float = 250.0, account: float = K.ACCOUNT) -> dict:
    chk = K.check(sym, bars, as_of, position=position, account=account,
                  benchmark=benchmark, **(extra or {}))
    return {"symbol": sym, "kind": "watch", "alerts": [f"VETO: {v}" for v in chk.get("vetoes", [])],
            "check": chk}


def digest(as_of: str, holdings: Sequence[dict], watch: Sequence[dict], notes: Sequence[str] = ()) -> str:
    n_alerts = sum(len(h["alerts"]) for h in holdings) + sum(len(w["alerts"]) for w in watch)
    lines = [f"# Monitor {as_of}", "",
             f"{len(holdings)} holdings, {len(watch)} watchlist symbols, {n_alerts} alerts. "
             "Read-only: no orders were placed or changed.", ""]
    lines += [f"> {n}" for n in notes] + ([""] if notes else [])
    if holdings:
        lines += ["## Holdings", "",
                  "| Symbol | Account | Qty | Avg cost | Close | Value | P&L | Check | Alerts |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for h in sorted(holdings, key=lambda h: (-len(h["alerts"]), h["symbol"])):
            pnl = "n/a" if h["unrealized_pnl"] is None else f"${h['unrealized_pnl']:+,.0f} ({h['unrealized_pct']:+.0%})"
            lines.append(f"| {h['symbol']} | {mask(h.get('account'))} | {h['quantity']:g} | {h['average_cost'] or 'n/a'} | "
                         f"{h['last_close']} | ${h['value'] or 0:,.0f} | {pnl} | {h['check']['verdict']} | "
                         f"{'<br>'.join(h['alerts']) or '—'} |")
        lines.append("")
    if watch:
        lines += ["## Watchlist", ""]
        for w in watch:
            lines += ["```", K.render(w["check"]), "```"]
        lines.append("")
    lines += ["## Holding detail", ""]
    for h in holdings:
        lines += [f"### {h['symbol']} ({mask(h.get('account'))})", "```", K.render(h["check"]), "```"]
    return "\n".join(lines) + "\n"


def write(as_of: str, text: str, holdings, watch, out: Path = OUT) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{as_of}.md"
    p.write_text(text)
    with open(out / "log.jsonl", "a") as fh:
        for r in list(holdings) + list(watch):
            c = r["check"]
            fh.write(json.dumps({"as_of": as_of, "symbol": r["symbol"], "kind": r["kind"],
                                 "verdict": c["verdict"], "last_close": c.get("facts", {}).get("last_close"),
                                 "alerts": r["alerts"]}) + "\n")
    return p


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def merge_orders(responses) -> list[dict]:
    """Every order seen in any get_equity_orders response (full history,
    symbol-filtered, paged), de-duplicated by order id."""
    seen, out = set(), []
    for data in responses:
        for o in parse_orders(data):
            key = o["id"] or (o["symbol"], o["side"], o["placed"], o["state"])
            if key not in seen:
                seen.add(key)
                out.append(o)
    return out


def _all_from_transcripts(paths, tool: str) -> list:
    sys.path.insert(0, str(ROOT / "scripts"))
    from l14 import _iter_calls
    out = []
    for p in paths:
        for name, _, text in _iter_calls(Path(p)):
            if name.endswith(tool):
                try:
                    out.append(json.loads(text)["data"])
                except (ValueError, KeyError, TypeError):
                    pass
    return out


def _per_account_from_transcripts(paths, tool: str) -> dict:
    """Latest response of `tool` per account_number (pages merged by cursor
    order as they appear)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from l14 import _iter_calls
    found: dict = {}
    for p in paths:
        for name, inp, text in _iter_calls(Path(p)):
            if not name.endswith(tool):
                continue
            try:
                data = json.loads(text)["data"]
            except (ValueError, KeyError, TypeError):
                continue
            acct = inp.get("account_number")
            if inp.get("cursor"):
                found.setdefault(acct, []).append(data)
            else:
                found[acct] = [data]        # a fresh first page replaces older runs
    return found


def _load_file(f):
    text = Path(f).read_text().strip()
    if not text:
        return {}
    try:
        d = json.loads(text)
    except ValueError:
        sys.exit(f"{f}: not valid JSON")
    return d.get("data", d) if isinstance(d, dict) else d


def main(argv=None) -> None:
    import bracket as B
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--historicals", nargs="+", required=True)
    ap.add_argument("--transcript", nargs="*", default=[])
    ap.add_argument("--positions", help="JSON file with the get_equity_positions response")
    ap.add_argument("--orders", help="JSON file with the get_equity_orders response")
    ap.add_argument("--watchlist", default=str(ROOT / "data" / "watchlist.txt"))
    ap.add_argument("--account", type=float, default=None,
                    help="account size for position ceilings (default: total value of holdings)")
    a = ap.parse_args(argv)

    series, hy = B.load(a.historicals, a.as_of)
    positions, orders = [], []
    if a.positions:
        positions = parse_positions(_load_file(a.positions))
    else:
        for acct, pages in _per_account_from_transcripts(a.transcript, "get_equity_positions").items():
            for d in pages:
                positions += parse_positions(d, acct)
    if a.orders:
        orders = parse_orders(_load_file(a.orders))
    else:
        orders = merge_orders(_all_from_transcripts(a.transcript, "get_equity_orders"))
    watch_syms = []
    if os.path.exists(a.watchlist):
        watch_syms = [l.split("#")[0].strip().upper() for l in open(a.watchlist)
                      if l.split("#")[0].strip()]
    notes = [f"daily bars: {hy.kept} kept, {hy.interpolated} interpolated dropped"]
    if a.account is None:
        a.account = round(sum(p["quantity"] * series[p["symbol"]][-1].c for p in positions
                              if p["symbol"] in series), 2) or K.ACCOUNT
        notes.append(f"position ceilings use the holdings total, ${a.account:,.0f}")
    held = {p["symbol"] for p in positions}
    if any(o["symbol"] for o in orders) and not positions:
        notes.append("orders read but no positions; check the account numbers")
    holdings, watch = [], []
    for p in positions:
        last = series[p["symbol"]][-1].c if p["symbol"] in series else None
        if last is not None and p["quantity"] * last < DUST_USD:
            notes.append(f"{p['symbol']} ({mask(p['account'])}): {p['quantity']:g} shares worth "
                         f"${p['quantity'] * last:.2f}, leftover fraction skipped")
            continue
        if p["symbol"] not in series:
            notes.append(f"no daily bars for holding {p['symbol']}; not checked")
            continue
        extra = K._from_transcripts(a.transcript, p["symbol"]) if a.transcript else {}
        holdings.append(holding_report(p, series[p["symbol"]], orders, a.as_of, extra=extra,
                                       benchmark=series.get("SPY"), account=a.account))
    for s in watch_syms:
        if s in held:
            continue
        if s not in series:
            notes.append(f"no daily bars for watchlist {s}; not checked")
            continue
        extra = K._from_transcripts(a.transcript, s) if a.transcript else {}
        watch.append(watch_report(s, series[s], a.as_of, extra=extra, benchmark=series.get("SPY"),
                                  account=a.account))
    text = digest(a.as_of, holdings, watch, notes)
    path = write(a.as_of, text, holdings, watch)
    print(text)
    print(f"written: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
