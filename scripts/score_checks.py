"""
Score past checks against what happened next.

    python3 scripts/score_checks.py --historicals PAYLOAD... [--horizons 5 20]

Reads every logged check (results/paper/checks.jsonl and
results/monitor/log.jsonl), finds the close on the check date and N sessions
later in the payloads, and reports by verdict: N, mean and median forward
return, and the share that fell more than 10%. Only checks with enough later
bars are scored, so a check is never scored with data it could not see coming
(the forward window is the outcome, not an input).
Writes results/monitor/scorecard.md.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))

LOGS = [ROOT / "results" / "paper" / "checks.jsonl", ROOT / "results" / "monitor" / "log.jsonl"]


def load_checks(paths=LOGS) -> list[dict]:
    seen, out = set(), []
    for p in paths:
        if not Path(p).exists():
            continue
        for line in open(p):
            if not line.strip():
                continue
            r = json.loads(line)
            key = (r["symbol"], r["as_of"])
            if key in seen:
                continue
            seen.add(key)
            out.append({"symbol": r["symbol"], "as_of": r["as_of"], "verdict": r["verdict"]})
    return out


def forward_returns(checks, series, horizons=(5, 20)) -> list[dict]:
    rows = []
    for c in checks:
        bars = series.get(c["symbol"])
        if not bars:
            continue
        dates = [b.date for b in bars]
        base = max((i for i, d in enumerate(dates) if d <= c["as_of"]), default=None)
        if base is None:
            continue
        r = dict(c)
        for h in horizons:
            if base + h < len(bars):
                r[f"ret_{h}"] = bars[base + h].c / bars[base].c - 1
        rows.append(r)
    return rows


def scorecard(rows, horizons=(5, 20)) -> str:
    lines = ["# Check scorecard", "",
             "Forward close-to-close return after each check, by verdict. "
             "A useful VETO/CAUTION should be followed by worse returns than NO FLAGS.", ""]
    for h in horizons:
        lines += [f"## {h} sessions later", "", "| Verdict | N | Mean | Median | Share down >10% |",
                  "|---|---|---|---|---|"]
        by = defaultdict(list)
        for r in rows:
            if f"ret_{h}" in r:
                by[r["verdict"]].append(r[f"ret_{h}"])
        for v in ("VETO", "CAUTION", "NO FLAGS"):
            xs = by.get(v, [])
            if xs:
                lines.append(f"| {v} | {len(xs)} | {st.mean(xs):+.1%} | {st.median(xs):+.1%} | "
                             f"{sum(x < -0.10 for x in xs) / len(xs):.0%} |")
            else:
                lines.append(f"| {v} | 0 | — | — | — |")
        lines.append("")
    pending = sum(1 for r in rows if f"ret_{horizons[0]}" not in r)
    lines.append(f"{len(rows)} checks with price data; {pending} too recent to score.")
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    import datetime as dt
    import bracket as B
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--historicals", nargs="+", required=True)
    ap.add_argument("--as-of", default=dt.date.today().isoformat())
    ap.add_argument("--horizons", nargs="+", type=int, default=[5, 20])
    a = ap.parse_args(argv)
    series, _ = B.load(a.historicals, a.as_of)
    text = scorecard(forward_returns(load_checks(), series, a.horizons), a.horizons)
    out = ROOT / "results" / "monitor"
    out.mkdir(parents=True, exist_ok=True)
    (out / "scorecard.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
