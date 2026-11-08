"""
L1.4 walk-forward CLI. The agent (or its subagents) fetches filing indexes and
financials from the brokerage MCP server; this script reads those responses
back out of the session transcripts and runs the harness.

    select                      choose the events to replay -> data/l14/sample.json
    extract TRANSCRIPT...       pull get_sec_filing_index / get_financials
                                results out of session transcripts
                                -> data/l14/filings.json, data/l14/financials.json
    tune                        L1.5: one knob at a time, PLAN order -> data/l14/tuning.json
    run [--threshold N] [--k K] [--latch N] [--release R] [--save PATH]
                                replay every sampled event, print metrics with N

Small filing-index responses never spill to disk, so they are read from the
session's JSONL transcripts (the main one and subagents/*.jsonl). Python never
calls the brokerage. See specs/002-l14-walk-forward/.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SEED = 42
CONTROL_SAMPLE = 400
INDEX_SINCE = "2021-01-01"
INDEX_UNTIL = "2026-10-08"
INDEX_FORMS = ["10-K", "10-Q", "8-K", "20-F", "6-K", "40-F", "10-K/A", "10-Q/A",
               "20-F/A", "S-1", "F-1", "424B4", "S-1/A", "F-1/A"]


def _paths(root: Path) -> dict[str, Path]:
    d = root / "data" / "l14"
    return {"dir": d, "sample": d / "sample.json", "filings": d / "filings.json",
            "financials": d / "financials.json", "events": root / "data" / "events"}


def _read_events(root: Path) -> list[dict]:
    out = []
    for f in sorted(_paths(root)["events"].glob("events_*.jsonl")):
        out += [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    return out


def event_key(e: dict) -> str:
    return f"{e['symbol']}|{e['ramp_start_date']}|{e['peak_date']}"


# --------------------------------------------------------------------------
# select
# --------------------------------------------------------------------------

def select(root: Path, n_controls: int = CONTROL_SAMPLE, seed: int = SEED) -> dict:
    """Every positive, plus a seeded random sample of controls."""
    events = _read_events(root)
    positives = [e for e in events if e["label"] == "positive"]
    controls = [e for e in events if e["label"] == "control"]
    sample = random.Random(seed).sample(controls, min(n_controls, len(controls)))
    out = {
        "seed": seed,
        "n_controls_total": len(controls),
        "positives": sorted(event_key(e) for e in positives),
        "controls": sorted(event_key(e) for e in sample),
    }
    out["symbols"] = sorted({k.split("|")[0] for k in out["positives"] + out["controls"]})
    p = _paths(root)["sample"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1) + "\n")
    return out


# --------------------------------------------------------------------------
# extract
# --------------------------------------------------------------------------

def _tool_text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(x.get("text", "") for x in content if isinstance(x, dict))


def _iter_calls(transcript: Path):
    """Yield (tool_name, input, result_text) for every MCP call in a transcript."""
    uses: dict[str, tuple[str, dict]] = {}
    for line in transcript.read_text().splitlines():
        try:
            msg = json.loads(line).get("message") or {}
        except json.JSONDecodeError:
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_use":
                uses[part["id"]] = (part.get("name", ""), part.get("input") or {})
            elif part.get("type") == "tool_result" and part.get("tool_use_id") in uses:
                name, inp = uses[part["tool_use_id"]]
                yield name, inp, _tool_text(part.get("content"))


def parse_index_call(inp: dict, text: str) -> dict | None:
    """One get_sec_filing_index response made with the standard L1.4 arguments,
    reduced to [date, form] pairs. Calls with other arguments are ignored."""
    if (inp.get("since") != INDEX_SINCE or inp.get("until") != INDEX_UNTIL
            or sorted(inp.get("form_type") or []) != sorted(INDEX_FORMS)):
        return None
    try:
        data = json.loads(text)["data"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    return {"symbol": data["symbol"], "cursor": inp.get("cursor"), "next": data.get("next"),
            "filings": [[f["date_filed"], f["form_type"]] for f in data.get("filings", [])]}


def parse_financials_call(inp: dict, text: str) -> dict[str, list] | None:
    """Annual rows per symbol as [period_end_date, net_income or None]."""
    if inp.get("period") != "annual":
        return None
    try:
        results = json.loads(text)["data"]["results"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    out = {}
    for sym, r in zip(inp.get("symbols") or [], results):
        rows = (r or {}).get("financials") or []
        out[sym.upper()] = [[x["period_end_date"],
                             None if x.get("net_income") is None else float(x["net_income"])]
                            for x in rows if x.get("fiscal_quarter") is None]
    return out


def extract(root: Path, transcripts: list[Path]) -> dict:
    p = _paths(root)
    filings = json.loads(p["filings"].read_text()) if p["filings"].exists() else {}
    financials = json.loads(p["financials"].read_text()) if p["financials"].exists() else {}
    pages: dict[str, dict] = {}
    for t in transcripts:
        for name, inp, text in _iter_calls(t):
            if name.endswith("get_sec_filing_index"):
                page = parse_index_call(inp, text)
                if page:
                    pages.setdefault(page["symbol"], {})[page["cursor"]] = page
            elif name.endswith("get_financials"):
                rows = parse_financials_call(inp, text)
                if rows:
                    financials.update(rows)
    incomplete = []
    for sym, by_cursor in pages.items():
        # Walk the cursor chain from the first page; keep the symbol only if complete.
        page, seen = by_cursor.get(None), []
        while page is not None:
            seen += page["filings"]
            nxt = page["next"]
            page = by_cursor.get(nxt) if nxt else None
            if nxt and page is None:
                incomplete.append(sym)
                break
        else:
            filings[sym] = sorted({tuple(f) for f in seen}, key=lambda f: (f[0], f[1]))
            filings[sym] = [list(f) for f in filings[sym]]
    p["dir"].mkdir(parents=True, exist_ok=True)
    p["filings"].write_text(json.dumps(filings, indent=0, sort_keys=True) + "\n")
    p["financials"].write_text(json.dumps(financials, indent=0, sort_keys=True) + "\n")
    return {"filings_symbols": len(filings), "financials_symbols": len(financials),
            "incomplete": sorted(set(incomplete))}


# --------------------------------------------------------------------------
# run / tune
# --------------------------------------------------------------------------

def _inputs(root: Path):
    p = _paths(root)
    sample = json.loads(p["sample"].read_text())
    filings = json.loads(p["filings"].read_text())
    financials = json.loads(p["financials"].read_text())
    done = json.loads((root / "data" / "l13" / "progress.json").read_text())["done"]
    by_key = {event_key(e): e for e in _read_events(root)}
    return sample, filings, financials, done, by_key


def run(root: Path, cfg=None, block_threshold: int | None = None) -> dict:
    """Replay every sampled event and return metrics for each bound and subset."""
    from src.harness import metrics, replay
    from src.layer1 import STRUCTURAL_BLOCK_THRESHOLD, PumpConfig

    cfg = cfg or PumpConfig()
    block_threshold = STRUCTURAL_BLOCK_THRESHOLD if block_threshold is None else block_threshold
    sample, filings, financials, done, by_key = _inputs(root)
    missing = sorted(s for s in sample["symbols"] if s not in filings)
    reps: dict[str, list] = {"positive": [], "control": []}
    skipped = 0
    for group in ("positives", "controls"):
        for k in sample[group]:
            e = by_key[k]
            r = replay(e, filings.get(e["symbol"], []), financials.get(e["symbol"]) or [],
                       done.get(e["symbol"], {}).get("first_bar"), cfg, block_threshold)
            if r is None:
                skipped += 1
                continue
            reps[e["label"]].append((r, e))
    pos_all = [r for r, _ in reps["positive"]]
    pos_clean = [r for r, e in reps["positive"]
                 if not e.get("suspect_bad_print") and not e.get("stale_quote")]
    ctl = [r for r, _ in reps["control"]]
    w = sample["n_controls_total"] / len(sample["controls"])
    out = {"config": {"window": cfg.window, "k": cfg.k, "latch_sessions": cfg.latch_sessions,
                      "release_ratio": cfg.release_ratio, "block_threshold": block_threshold},
           "skipped_short": skipped, "symbols_without_filing_index": missing, "results": []}
    for subset, pos in (("all", pos_all), ("unflagged", pos_clean)):
        for bound in ("hi", "lo", "pump"):
            out["results"].append({"positives": subset, **metrics(pos, ctl, bound, w)})
    unknown = Counter(u for r in pos_all + ctl for u in r.unknown_at_peak)
    out["unknown_at_peak"] = {k: f"{v}/{len(pos_all) + len(ctl)}" for k, v in sorted(unknown.items())}
    return out


def _print_run(r: dict) -> None:
    c = r["config"]
    print(f"config: threshold {c['block_threshold']}/6, window {c['window']}, k {c['k']}, "
          f"latch {c['latch_sessions']}, release {c['release_ratio']}")
    print(f"skipped (peak within the first {c['window']} bars): {r['skipped_short']}; "
          f"symbols with no filing index fetched: {len(r['symbols_without_filing_index'])}")
    print(f"{'positives':10} {'bound':5} {'N+':>4} {'recall':>7} {'rec@2':>6} {'lead':>5} "
          f"{'N-':>4} {'FP':>6} {'latchP':>7}")
    for m in r["results"]:
        print(f"{m['positives']:10} {m['bound']:5} {m['n_positives']:>4} {m['recall']!s:>7} "
              f"{m['recall_lead_ge_2']!s:>6} {m['median_lead']!s:>5} {m['n_controls']:>4} "
              f"{m['fp_rate']!s:>6} {m['latch_precision']!s:>7}")
    print("unknown at peak:", r["unknown_at_peak"])


# L1.5: PLAN order. `window` stays 5 (the latch is the fix for self-contamination).
TUNE_GRID = [
    ("block_threshold", [2, 3, 4, 5, 6]),
    ("latch_sessions", [5, 10, 15, 20, 30]),
    ("k", [1.5, 1.75, 2.0, 2.5, 3.0]),
    ("release_ratio", [1.05, 1.15, 1.3, 1.5]),
]
GATE = {"recall": 0.85, "median_lead": 2, "fp_rate": 0.35}


def _gate_row(r: dict) -> dict:
    return next(m for m in r["results"] if m["positives"] == "unflagged" and m["bound"] == "hi")


def meets_gate(m: dict) -> bool:
    return (m["recall"] is not None and m["recall"] >= GATE["recall"]
            and m["median_lead"] is not None and m["median_lead"] >= GATE["median_lead"]
            and m["fp_rate"] is not None and m["fp_rate"] <= GATE["fp_rate"])


def choose(rows: list[tuple[object, dict]], current) -> tuple[object, str]:
    """Pick one knob value from (value, gate_row) pairs.

    Values that meet the gate: the lowest FP rate, ties to higher recall.
    If none does, keep the current value. Never move to a value that buys a
    lower FP rate with lower recall (CLAUDE.md hard rule 4); the frontier is
    recorded in tuning.json for the owner to judge.
    """
    ok = [(v, m) for v, m in rows if meets_gate(m)]
    if ok:
        v, _ = min(ok, key=lambda x: (x[1]["fp_rate"], -x[1]["recall"]))
        return v, "meets gate; lowest FP"
    return current, "gate not met at any value; kept"


def tune(root: Path) -> list[dict]:
    from src.layer1 import STRUCTURAL_BLOCK_THRESHOLD, PumpConfig

    current = {"block_threshold": STRUCTURAL_BLOCK_THRESHOLD, **{
        k: getattr(PumpConfig(), k) for k in ("latch_sessions", "k", "release_ratio")}}
    runs_dir = _paths(root)["dir"] / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    log = []
    for knob, values in TUNE_GRID:
        rows = []
        for v in values:
            trial = dict(current, **{knob: v})
            cfg = PumpConfig(latch_sessions=trial["latch_sessions"], k=trial["k"],
                             release_ratio=trial["release_ratio"])
            r = run(root, cfg, trial["block_threshold"])
            name = "_".join(f"{k}={trial[k]}" for k in sorted(trial))
            (runs_dir / f"{name}.json").write_text(json.dumps(r, indent=1) + "\n")
            rows.append((v, _gate_row(r)))
        chosen, why = choose(rows, current[knob])
        current[knob] = chosen
        log.append({"knob": knob, "chosen": chosen, "why": why,
                    "trials": [{"value": v, **m} for v, m in rows]})
    (_paths(root)["dir"] / "tuning.json").write_text(json.dumps(
        {"gate": GATE, "final": current, "steps": log}, indent=1) + "\n")
    return log


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    ex = sub.add_parser("extract")
    ex.add_argument("transcripts", nargs="+", type=Path)
    rn = sub.add_parser("run")
    rn.add_argument("--threshold", type=int)
    rn.add_argument("--k", type=float)
    rn.add_argument("--latch", type=int)
    rn.add_argument("--release", type=float)
    sub.add_parser("tune")
    rn.add_argument("--save", type=Path, help="write the full result as JSON")
    args = ap.parse_args(argv)
    if args.cmd == "select":
        s = select(ROOT)
        print(json.dumps({"positives": len(s["positives"]), "controls": len(s["controls"]),
                          "symbols": len(s["symbols"])}))
    elif args.cmd == "extract":
        print(json.dumps(extract(ROOT, args.transcripts)))
    elif args.cmd == "tune":
        for step in tune(ROOT):
            print(f"{step['knob']}: chose {step['chosen']} ({step['why']})")
            for t in step["trials"]:
                print(f"   {t['value']!s:>6}  recall {t['recall']}  rec@2 {t['recall_lead_ge_2']}  "
                      f"lead {t['median_lead']}  FP {t['fp_rate']}  (N+ {t['n_positives']}, N- {t['n_controls']})")
    elif args.cmd == "run":
        from src.layer1 import PumpConfig
        base = PumpConfig()
        cfg = PumpConfig(window=base.window,
                         k=base.k if args.k is None else args.k,
                         latch_sessions=base.latch_sessions if args.latch is None else args.latch,
                         release_ratio=base.release_ratio if args.release is None else args.release)
        r = run(ROOT, cfg, args.threshold)
        _print_run(r)
        if args.save:
            args.save.write_text(json.dumps(r, indent=1) + "\n")


if __name__ == "__main__":
    main()
