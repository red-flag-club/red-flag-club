"""
`check TICKER` — a pre-trade insight report. It never says BUY and places no
orders; it says what is known, what the risks are in dollars, and whether a
veto applies.

    python3 src/check_ticker.py HOOD --as-of 2026-10-14 --position 250 \
        --historicals PAYLOAD.txt [--transcript SESSION.jsonl ...]

Inputs come from read-only brokerage MCP tools the agent calls first:
  get_equity_historicals (daily, ~14 months, the symbol plus SPY),
  get_equity_fundamentals, get_sec_filing_index, get_earnings_results.
Large historicals spill to a file (--historicals); the small responses are
read from the session transcript (--transcript), the same way scripts/l14.py
extracts filing indexes. Every check is appended to results/paper/checks.jsonl
so its flags can be scored against what happened later.

Verdicts:
  VETO       a Layer 1 rule fires (pump profile, ghost quote, or >= 4 of 6
             structural red flags) — do not buy
  CAUTION    no veto, but listed risks apply
  NO FLAGS   none of the checks fired; still not a buy signal
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import statistics as st
import sys
from typing import Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from layer1 import Bar, Issuer, structural_score  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKS = os.path.join(ROOT, "results", "paper", "checks.jsonl")

ACCOUNT = 1_000.0
RISK_BUDGET = 0.05            # a 1-in-100 bad week should cost <= 5% of the account
STRESS_Z = 2.33               # 99th percentile, normal approximation (fat tails make it worse)
EARNINGS_WINDOW_DAYS = 14     # calendar days
PUMP_RUNUP, PUMP_SESSIONS = 1.0, 10
HIGH_VOL = 0.50               # annualised
SMALL_CAP_SCOPE = 500e6       # unknown structural inputs only matter below this market cap


class LookaheadError(ValueError):
    pass


def _sma(c: Sequence[float], n: int) -> float | None:
    return sum(c[-n:]) / n if len(c) >= n else None


def _ret(c: Sequence[float], n: int) -> float | None:
    return c[-1] / c[-1 - n] - 1 if len(c) > n else None


def _f(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def earnings_reactions(bars: Sequence[Bar], reports: Sequence[dict]) -> list[dict]:
    """Close-to-close move across each past report (pm -> next session)."""
    dates = [b.date for b in bars]
    out = []
    for r in reports:
        d, timing = r["report"]["date"], r["report"].get("timing")
        if r.get("eps", {}).get("actual") is None or d not in dates:
            continue
        i = dates.index(d)
        before, after = (i, i + 1) if timing == "pm" else (i - 1, i)
        if before < 0 or after >= len(bars):
            continue
        out.append({"date": d, "move": round(bars[after].c / bars[before].c - 1, 4)})
    return out


def check(symbol: str, bars: Sequence[Bar], as_of: str, *, fundamentals: dict | None = None,
          filings: Sequence[dict] | None = None, earnings: Sequence[dict] | None = None,
          benchmark: Sequence[Bar] | None = None, position: float = 250.0,
          account: float = ACCOUNT) -> dict:
    if any(b.date > as_of for b in bars) or any(b.date > as_of for b in (benchmark or [])):
        raise LookaheadError(f"bar after as-of date {as_of}")
    if len(bars) < 30:
        return {"symbol": symbol, "as_of": as_of, "verdict": "INSUFFICIENT DATA",
                "reasons": [f"only {len(bars)} real daily bars"]}
    fu = fundamentals or {}
    c = [b.c for b in bars]
    last = bars[-1]
    vetoes, cautions, facts = [], [], {}

    # --- price facts
    sma50, sma200 = _sma(c, 50), _sma(c, 200)
    rets = [c[i] / c[i - 1] - 1 for i in range(1, len(c))]
    vol = st.pstdev(rets[-60:]) * math.sqrt(252)
    facts.update({
        "last_close": last.c, "last_date": last.date,
        "sma50": round(sma50, 2) if sma50 else None, "sma200": round(sma200, 2) if sma200 else None,
        "vs_sma200": round(last.c / sma200 - 1, 4) if sma200 else None,
        "ret_1m": _ret(c, 21), "ret_3m": _ret(c, 63), "ret_12m": _ret(c, 252),
        "vol_annual": round(vol, 3),
        "high_52w": _f(fu.get("high_52_weeks")) or max(c[-252:]),
        "low_52w": _f(fu.get("low_52_weeks")) or min(c[-252:]),
    })
    facts["from_high"] = round(last.c / facts["high_52w"] - 1, 4)
    for k in ("ret_1m", "ret_3m", "ret_12m"):
        facts[k] = None if facts[k] is None else round(facts[k], 4)

    # --- Layer 1 vetoes checkable from price
    if last.o == last.h == last.l == last.c:
        vetoes.append("last bar is flat (ghost quote)")
    low10 = min(c[-(PUMP_SESSIONS + 1):])
    if low10 > 0 and last.c / low10 - 1 >= PUMP_RUNUP:
        vetoes.append(f"up {last.c / low10 - 1:.0%} in <= {PUMP_SESSIONS} sessions (pump profile)")

    # --- structural score (unknowns stay unknown and are listed)
    forms = [f["form_type"] for f in (filings or []) if f["date_filed"] <= as_of]
    last_filing = max((f["date_filed"] for f in (filings or []) if f["date_filed"] <= as_of), default=None)
    days_since = ((dt.date.fromisoformat(as_of) - dt.date.fromisoformat(last_filing)).days
                  if last_filing else None)
    pe = _f(fu.get("pe_ratio"))
    iss = Issuer(symbol=symbol, public_float=_f(fu.get("float")), market_cap=_f(fu.get("market_cap")),
                 form_types=forms, months_since_first_filing=None,
                 net_income=(-1.0 if pe is not None and pe < 0 else (1.0 if pe else None)),
                 days_since_last_filing=days_since)
    score, flags = structural_score(iss)
    unknown = [n for n, v in (("float", iss.public_float), ("market cap", iss.market_cap),
                              ("filer type", forms or None), ("listing age", None),
                              ("profitability", iss.net_income), ("filing recency", days_since))
               if v is None]
    facts.update({"structural_score": f"{score}/6", "structural_flags": flags,
                  "structural_unknown": unknown, "market_cap": iss.market_cap,
                  "float": iss.public_float, "pe": pe, "last_sec_filing": last_filing})
    if score >= 4:
        vetoes.append(f"structural score {score}/6 (FINRA 22-25 profile)")
    elif score + len(unknown) >= 4 and (iss.market_cap is None or iss.market_cap < SMALL_CAP_SCOPE):
        cautions.append(f"structural score {score}/6 with {len(unknown)} unknown — could reach the veto")

    # --- cautions
    if sma200 and last.c < sma200:
        cautions.append(f"below its 200-day average ({last.c:.2f} < {sma200:.2f})")
    if vol >= HIGH_VOL:
        cautions.append(f"high volatility: {vol:.0%} a year")
    if benchmark and len(benchmark) > 61:
        bc = [b.c for b in benchmark]
        bvol = st.pstdev([bc[i] / bc[i - 1] - 1 for i in range(len(bc) - 60, len(bc))]) * math.sqrt(252)
        facts["benchmark_vol_annual"] = round(bvol, 3)
        facts["vol_vs_benchmark"] = round(vol / bvol, 1) if bvol else None
    if facts["from_high"] <= -0.30:
        cautions.append(f"{facts['from_high']:.0%} below its 52-week high")
    upcoming = [e for e in (earnings or []) if e.get("eps", {}).get("actual") is None
                and e["report"]["date"] >= as_of]
    if upcoming:
        nxt = min(upcoming, key=lambda e: e["report"]["date"])
        days = (dt.date.fromisoformat(nxt["report"]["date"]) - dt.date.fromisoformat(as_of)).days
        facts["next_earnings"] = {"date": nxt["report"]["date"], "timing": nxt["report"].get("timing"),
                                  "verified": nxt["report"].get("verified"), "days": days}
        if days <= EARNINGS_WINDOW_DAYS:
            cautions.append(f"earnings in {days} days ({nxt['report']['date']} {nxt['report'].get('timing') or ''})".strip())
    reactions = earnings_reactions(bars, earnings or [])
    if reactions:
        facts["earnings_reactions"] = reactions
        facts["avg_abs_earnings_move"] = round(sum(abs(r["move"]) for r in reactions) / len(reactions), 4)

    # --- dollars at risk and a suggested ceiling
    d1 = vol / math.sqrt(252)
    week_stress = STRESS_Z * d1 * math.sqrt(5)
    max_pos = account * RISK_BUDGET / week_stress if week_stress > 0 else position
    if facts.get("next_earnings", {}).get("days", 99) <= EARNINGS_WINDOW_DAYS:
        max_pos /= 2
    facts["risk"] = {
        "position": position,
        "typical_day": round(d1 * position, 2),
        "bad_week_1_in_100": round(week_stress * position, 2),
        "earnings_gap_typical": (round(facts["avg_abs_earnings_move"] * position, 2)
                                 if reactions else None),
        "suggested_max_position": round(min(max_pos, account), 2),
        "exit_rule": (f"sell if it closes below its 200-day average (now {sma200:.2f}), decided before buying"
                      if sma200 else "set a time stop before buying (no 200-day history)"),
    }
    if position > facts["risk"]["suggested_max_position"]:
        cautions.append(f"${position:,.0f} is above the suggested ceiling of "
                        f"${facts['risk']['suggested_max_position']:,.0f} for a ${account:,.0f} account")

    verdict = "VETO" if vetoes else ("CAUTION" if cautions else "NO FLAGS")
    return {"symbol": symbol, "as_of": as_of, "verdict": verdict, "vetoes": vetoes,
            "cautions": cautions, "facts": facts,
            "note": "Not a buy signal. No order is placed."}


def render(r: dict) -> str:
    if "facts" not in r:
        return f"{r['symbol']} {r['as_of']}: {r['verdict']} — {'; '.join(r['reasons'])}"
    f, k = r["facts"], r["facts"]["risk"]
    pct = lambda x: "n/a" if x is None else f"{x:+.1%}"
    lines = [f"{r['symbol']} as of {r['as_of']} — {r['verdict']}  (not a buy signal; no order placed)"]
    lines += [f"  VETO: {v}" for v in r["vetoes"]] + [f"  caution: {c}" for c in r["cautions"]]
    lines.append(f"  close {f['last_close']} ({f['last_date']}); 200-day {f['sma200']} ({pct(f['vs_sma200'])}); "
                 f"1m {pct(f['ret_1m'])}, 3m {pct(f['ret_3m'])}, 12m {pct(f['ret_12m'])}; "
                 f"{pct(f['from_high'])} from 52w high {f['high_52w']}")
    lines.append(f"  volatility {f['vol_annual']:.0%}/yr"
                 + (f" ({f['vol_vs_benchmark']}x SPY)" if f.get("vol_vs_benchmark") else ""))
    lines.append(f"  structural {f['structural_score']}: {f['structural_flags'] or 'no red flags'}"
                 + (f"; unknown: {', '.join(f['structural_unknown'])}" if f['structural_unknown'] else ""))
    if f.get("next_earnings"):
        e = f["next_earnings"]
        lines.append(f"  next earnings {e['date']} {e['timing'] or ''} ({'verified' if e['verified'] else 'tentative'}, {e['days']} days)")
    if f.get("earnings_reactions"):
        lines.append("  past earnings moves: " + ", ".join(f"{x['date']} {x['move']:+.1%}" for x in f["earnings_reactions"]))
    lines.append(f"  on ${k['position']:,.0f}: typical day ±${k['typical_day']:.0f}; 1-in-100 week −${k['bad_week_1_in_100']:.0f}"
                 + (f"; typical earnings gap ±${k['earnings_gap_typical']:.0f}" if k["earnings_gap_typical"] else ""))
    lines.append(f"  suggested max position ${k['suggested_max_position']:,.0f}; exit: {k['exit_rule']}")
    return "\n".join(lines)


def log(r: dict, path: str = CHECKS) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(r) + "\n")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _from_transcripts(paths: Sequence[str], symbol: str) -> dict:
    """Latest fundamentals, filing index and earnings for `symbol` found in the
    session transcripts."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from l14 import _iter_calls  # noqa: E402
    from pathlib import Path
    found: dict = {}
    for p in paths:
        for name, inp, text in _iter_calls(Path(p)):
            try:
                data = json.loads(text)["data"]
            except (ValueError, KeyError, TypeError):
                continue
            if name.endswith("get_equity_fundamentals"):
                for r in data.get("results") or []:
                    if r and r.get("symbol") == symbol:
                        found["fundamentals"] = r
            elif name.endswith("get_sec_filing_index") and data.get("symbol") == symbol:
                found["filings"] = data.get("filings") or []
            elif name.endswith("get_earnings_results"):
                rs = [r for r in data.get("results") or [] if r.get("symbol") == symbol]
                if rs:
                    found["earnings"] = rs
    return found


if __name__ == "__main__":
    import argparse
    import bracket as B

    ap = argparse.ArgumentParser(description="Pre-trade insight report (no orders).")
    ap.add_argument("symbol")
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--position", type=float, default=250.0)
    ap.add_argument("--account", type=float, default=ACCOUNT)
    ap.add_argument("--historicals", nargs="+", required=True)
    ap.add_argument("--transcript", nargs="*", default=[])
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    series, hy = B.load(a.historicals, a.as_of)
    if a.symbol not in series:
        sys.exit(f"no daily bars for {a.symbol} in the payloads")
    extra = _from_transcripts(a.transcript, a.symbol) if a.transcript else {}
    r = check(a.symbol, series[a.symbol], a.as_of, benchmark=series.get("SPY"),
              position=a.position, account=a.account, **extra)
    r["inputs"] = {"bars": len(series[a.symbol]), "interpolated_dropped": hy.interpolated,
                   "fundamentals": "fundamentals" in extra, "filings": "filings" in extra,
                   "earnings": "earnings" in extra}
    print(render(r))
    if not a.no_log:
        log(r)
