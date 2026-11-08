"""
L1.3 event-set CLI. The agent fetches from the brokerage MCP server; this
script ingests the JSON payloads the harness spills to disk.

    universe-add PAYLOAD...       record preview_scan market-cap bands
    universe-build --date D       merge bands into a snapshot; list gaps
    next-batch --size N           next unprocessed symbols, in groups of 10
    ingest --batch ID --as-of D PAYLOAD...   label and store events
    report                        counts, each with its N

All state lives under data/ (committed). See specs/001-l13-event-sets/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.event_sets import (  # noqa: E402
    LABEL_CONTROL,
    LABEL_PENDING,
    LABEL_POSITIVE,
    clean_bars,
    label_events,
)

UNIVERSE_MAX_CAP = 500_000_000
SCAN_ROW_CAP = 200
SYMBOLS_PER_CALL = 10
SEED = 42


# --------------------------------------------------------------------------
# paths and json helpers
# --------------------------------------------------------------------------

def _paths(root: Path) -> dict[str, Path]:
    return {
        "bands": root / "data" / "universe" / "bands.jsonl",
        "universe": root / "data" / "universe",
        "events": root / "data" / "events",
        "progress": root / "data" / "l13" / "progress.json",
    }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1) + "\n")


def _load_payload(path: Path) -> dict:
    payload = json.loads(Path(path).read_text())
    return payload.get("data", payload)


# --------------------------------------------------------------------------
# universe
# --------------------------------------------------------------------------

def parse_band(payload: dict, fetched: str) -> dict:
    """One preview_scan payload -> band record. Bounds come from the echoed
    market-cap filter, so the record cannot disagree with what was run."""
    result = payload["result"]
    cap = next(f for f in result["filters_applied"]
               if f.get("filter_type_enum") == "FILTER_TYPE_MARKET_CAP")
    if cap["predicate"] != "BETWEEN":
        raise ValueError(f"expected a BETWEEN market-cap band, got {cap['predicate']}")
    lo, hi = (int(float(v)) for v in cap["values"])
    rows = result["results"]

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    return {
        "lo": lo,
        "hi": hi,
        "total_items": int(result["total_items"]),
        "rows": len(rows),
        "saturated": int(result["total_items"]) > len(rows),
        "fetched": fetched,
        "tickers": [{
            "symbol": r["ticker"],
            "market_cap": num(r["columns"].get("Market cap")),
            "float": num(r["columns"].get("Float")),
            "name": r["columns"].get("Name"),
        } for r in rows],
    }


def universe_add(root: Path, payload_paths: list[Path], fetched: str) -> list[dict]:
    p = _paths(root)
    bands = {(b["lo"], b["hi"]): b for b in _read_jsonl(p["bands"])}
    added = []
    for path in payload_paths:
        band = parse_band(_load_payload(path), fetched)
        bands[(band["lo"], band["hi"])] = band
        added.append(band)
    _write_jsonl(p["bands"], sorted(bands.values(), key=lambda b: (b["lo"], b["hi"])))
    return added


def coverage_gaps(bands: list[dict], lo: int = 0, hi: int = UNIVERSE_MAX_CAP) -> list[tuple[int, int]]:
    """Parts of [lo, hi] not covered by any unsaturated band. Bands are
    inclusive integer ranges; touching bands ([a, b], [b, c]) are contiguous."""
    covered = sorted((b["lo"], b["hi"]) for b in bands if not b["saturated"])
    gaps, cursor = [], lo
    for b_lo, b_hi in covered:
        if b_lo > cursor:
            gaps.append((cursor, min(b_lo, hi)))
        cursor = max(cursor, b_hi)
        if cursor >= hi:
            break
    if cursor < hi:
        gaps.append((cursor, hi))
    return gaps


def universe_build(root: Path, date: str) -> dict:
    p = _paths(root)
    bands = _read_jsonl(p["bands"])
    gaps = coverage_gaps(bands)
    saturated = [(b["lo"], b["hi"], b["total_items"]) for b in bands if b["saturated"]]
    symbols = sorted({t["symbol"] for b in bands for t in b["tickers"]})
    snapshot = {
        "date": date,
        "complete": not gaps,
        "bands": [{k: b[k] for k in ("lo", "hi", "total_items", "rows", "saturated", "fetched")}
                  for b in bands],
        "gaps": gaps,
        "saturated": saturated,
        "n_symbols": len(symbols),
        "symbols": symbols,
    }
    _write_json(p["universe"] / f"snapshot_{date}.json", snapshot)
    return snapshot


# --------------------------------------------------------------------------
# progress / batches
# --------------------------------------------------------------------------

def _latest_snapshot(root: Path) -> Path:
    snaps = sorted(_paths(root)["universe"].glob("snapshot_*.json"))
    if not snaps:
        raise SystemExit("no universe snapshot; run universe-build first")
    return snaps[-1]


def load_progress(root: Path) -> dict:
    path = _paths(root)["progress"]
    if path.exists():
        return json.loads(path.read_text())
    snap_path = _latest_snapshot(root)
    snap = json.loads(snap_path.read_text())
    if not snap["complete"]:
        raise SystemExit(f"{snap_path.name} is incomplete (gaps {snap['gaps']}); finish the universe first")
    order = list(snap["symbols"])
    random.Random(SEED).shuffle(order)
    return {
        "snapshot": str(snap_path.relative_to(root)),
        "seed": SEED,
        "order": order,
        "done": {},
        "batches": [],
    }


def save_progress(root: Path, progress: dict) -> None:
    _write_json(_paths(root)["progress"], progress)


def next_batch(root: Path, size: int) -> dict:
    """Return the open batch if one exists (resume), else open a new one from
    the next `size` symbols in seeded order that are not done."""
    progress = load_progress(root)
    open_batches = [b for b in progress["batches"] if not b.get("ingested")]
    if open_batches:
        return open_batches[0]
    todo = [s for s in progress["order"] if s not in progress["done"]][:size]
    batch = {"id": f"b{len(progress['batches']) + 1:03d}", "symbols": todo, "ingested": None}
    if todo:
        progress["batches"].append(batch)
        save_progress(root, progress)
    return batch


def ingest(
    root: Path,
    batch_id: str,
    as_of: str,
    payload_paths: list[Path],
    *,
    origin: str = "scan",
    expect: list[str] | None = None,
    close: bool = True,
    replace: bool = False,
) -> dict:
    """Label every symbol in the payloads that is not already done. With
    `close`, symbols the batch expected but no payload returned are marked
    no_data so they are not retried forever."""
    p = _paths(root)
    if p["progress"].exists() or origin == "scan":
        progress = load_progress(root)
    else:
        progress = _seed_progress(root)
    batch = next((b for b in progress["batches"] if b["id"] == batch_id), None)
    if batch is None:
        batch = {"id": batch_id, "symbols": list(expect or []), "ingested": None}
        progress["batches"].append(batch)
    elif expect:
        batch["symbols"] = sorted(set(batch["symbols"]) | set(expect))

    events_path = p["events"] / f"events_{batch_id}.jsonl"
    if replace:
        # Re-label this batch from its payloads (e.g. after a new event field
        # is added). Only this batch's symbols are reset; nothing else moves.
        for s in [s for s, d in progress["done"].items() if d["batch"] == batch_id]:
            del progress["done"][s]
        if events_path.exists():
            events_path.unlink()
    events = _read_jsonl(events_path)
    seen: set[str] = set()
    new_events = 0

    for path in payload_paths:
        for result in _load_payload(path)["results"]:
            symbol = result["symbol"]
            if batch["symbols"] and symbol not in batch["symbols"]:
                continue  # not part of this batch; never label it under the wrong batch
            seen.add(symbol)
            if symbol in progress["done"]:
                continue
            bars, stats = clean_bars(result.get("bars") or [], as_of)
            if not bars:
                progress["done"][symbol] = {"batch": batch_id, "status": "no_data", "origin": origin,
                                            **stats.__dict__}
                continue
            labelled = label_events(symbol, bars, as_of, origin=origin, batch=batch_id)
            events.extend(labelled)
            new_events += len(labelled)
            progress["done"][symbol] = {
                "batch": batch_id, "status": "ok", "origin": origin,
                "first_bar": bars[0].date, "last_bar": bars[-1].date, **stats.__dict__,
            }

    missing = [s for s in batch["symbols"] if s not in seen and s not in progress["done"]]
    if close:
        for s in missing:
            progress["done"][s] = {"batch": batch_id, "status": "no_data", "origin": origin,
                                   "total": 0, "kept": 0,
                                   "dropped_interpolated": 0, "dropped_nonpositive": 0}
        batch["ingested"] = dt.date.today().isoformat()

    _write_jsonl(events_path, events)
    save_progress(root, progress)
    return {"batch": batch_id, "new_events": new_events, "missing": missing, "closed": close}


def _seed_progress(root: Path) -> dict:
    """Seeds may be ingested before the universe exists; start an empty
    progress file and attach the scan order later."""
    return {"snapshot": None, "seed": SEED, "order": [], "done": {}, "batches": []}


def attach_order(root: Path) -> dict:
    """If progress was started by a seed ingest, add the snapshot order now."""
    path = _paths(root)["progress"]
    progress = json.loads(path.read_text())
    if progress["order"]:
        return progress
    snap_path = _latest_snapshot(root)
    snap = json.loads(snap_path.read_text())
    if not snap["complete"]:
        raise SystemExit(f"{snap_path.name} is incomplete; finish the universe first")
    order = list(snap["symbols"])
    random.Random(SEED).shuffle(order)
    progress["snapshot"] = str(snap_path.relative_to(root))
    progress["order"] = order
    save_progress(root, progress)
    return progress


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def report(root: Path) -> dict:
    p = _paths(root)
    progress = json.loads(p["progress"].read_text()) if p["progress"].exists() else {"done": {}, "order": []}
    events = [e for f in sorted(p["events"].glob("events_*.jsonl")) for e in _read_jsonl(f)]

    def count(origin, label):
        return sum(1 for e in events if e["origin"] == origin and e["label"] == label)

    done = progress["done"]
    scan_done = [s for s, d in done.items() if d["origin"] == "scan"]
    scan_ok = [s for s in scan_done if done[s]["status"] == "ok"]
    scan_pos_symbols = {e["symbol"] for e in events if e["origin"] == "scan" and e["label"] == LABEL_POSITIVE}

    out = {
        "universe_size": len(progress.get("order", [])),
        "scan_symbols_processed": len(scan_done),
        "scan_symbols_with_data": len(scan_ok),
        "scan": {lab: count("scan", lab) for lab in (LABEL_POSITIVE, LABEL_CONTROL, LABEL_PENDING)},
        "seed": {lab: count("seed", lab) for lab in (LABEL_POSITIVE, LABEL_CONTROL, LABEL_PENDING)},
        "scan_symbols_with_a_positive": len(scan_pos_symbols),
        "bars_dropped_interpolated": sum(d.get("dropped_interpolated", 0) for d in done.values()),
        "bars_dropped_nonpositive": sum(d.get("dropped_nonpositive", 0) for d in done.values()),
        "positives": sorted(
            (e["symbol"], e["peak_date"], round(e["run_up_pct"], 2), round(e["drawdown_pct"], 2), e["origin"],
             "BAD-PRINT?" if e.get("suspect_bad_print") else
             ("STALE?" if e.get("stale_quote") else ("spike" if e.get("isolated_spike_peak") else "")))
            for e in events if e["label"] == LABEL_POSITIVE
        ),
    }
    total_pos = out["scan"][LABEL_POSITIVE] + out["seed"][LABEL_POSITIVE]
    total_ctl = out["scan"][LABEL_CONTROL] + out["seed"][LABEL_CONTROL]
    out["scan_positives_clean"] = sum(
        1 for e in events if e["origin"] == "scan" and e["label"] == LABEL_POSITIVE
        and not e.get("suspect_bad_print"))
    out["scan_positives_clean_live"] = sum(
        1 for e in events if e["origin"] == "scan" and e["label"] == LABEL_POSITIVE
        and not e.get("suspect_bad_print") and not e.get("stale_quote"))
    out["total"] = {"positives": total_pos, "controls": total_ctl,
                    "pending": out["scan"][LABEL_PENDING] + out["seed"][LABEL_PENDING]}
    out["gate"] = {"positives_needed": 100, "controls_needed": 300,
                   "met": total_pos >= 100 and total_ctl >= 300}
    return out


def _print_report(r: dict) -> None:
    n_ok = r["scan_symbols_with_data"]
    pos = r["scan"][LABEL_POSITIVE]
    print(f"universe: {r['universe_size']} symbols; processed {r['scan_symbols_processed']} "
          f"({n_ok} with data)")
    print(f"scan path: positives {pos}, controls {r['scan'][LABEL_CONTROL]}, "
          f"pending {r['scan'][LABEL_PENDING]}  (N={n_ok} symbols)")
    if n_ok:
        print(f"  symbols with >=1 positive: {r['scan_symbols_with_a_positive']}/{n_ok} "
              f"= {r['scan_symbols_with_a_positive'] / n_ok:.1%}")
    print(f"  of which not flagged as a suspect bad print: {r['scan_positives_clean']}")
    print(f"  of which also not a stale quote: {r['scan_positives_clean_live']}")
    print(f"seed path: positives {r['seed'][LABEL_POSITIVE]}, controls {r['seed'][LABEL_CONTROL]}, "
          f"pending {r['seed'][LABEL_PENDING]}")
    t = r["total"]
    ratio = f"1:{t['controls'] / t['positives']:.1f}" if t["positives"] else "n/a"
    print(f"total: positives {t['positives']}, controls {t['controls']}, pending {t['pending']}, "
          f"positives:controls {ratio}")
    print(f"gate (>=100 positives, >=300 controls): {'MET' if r['gate']['met'] else 'NOT MET'}")
    print(f"bars dropped: interpolated {r['bars_dropped_interpolated']}, "
          f"non-positive {r['bars_dropped_nonpositive']}")
    print("biases: survivors only (delisted names absent); market cap measured today, "
          "not at run start; daily closes only")
    for row in r["positives"]:
        print("  +", *row)


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("universe-add")
    a.add_argument("payloads", nargs="+", type=Path)
    a.add_argument("--date", default=dt.date.today().isoformat())

    b = sub.add_parser("universe-build")
    b.add_argument("--date", default=dt.date.today().isoformat())

    n = sub.add_parser("next-batch")
    n.add_argument("--size", type=int, default=50)

    i = sub.add_parser("ingest")
    i.add_argument("payloads", nargs="+", type=Path)
    i.add_argument("--batch", required=True)
    i.add_argument("--as-of", required=True)
    i.add_argument("--origin", choices=["scan", "seed"], default="scan")
    i.add_argument("--expect", default="")
    i.add_argument("--keep-open", action="store_true")
    i.add_argument("--replace", action="store_true", help="re-label this batch from scratch")

    sub.add_parser("report")

    args = ap.parse_args(argv)
    root = args.root

    if args.cmd == "universe-add":
        for band in universe_add(root, args.payloads, args.date):
            flag = "SATURATED" if band["saturated"] else "ok"
            print(f"[{band['lo']:,} - {band['hi']:,}] total {band['total_items']} rows {band['rows']} {flag}")
    elif args.cmd == "universe-build":
        snap = universe_build(root, args.date)
        print(f"snapshot {snap['date']}: {snap['n_symbols']} symbols, complete={snap['complete']}")
        for lo, hi in snap["gaps"]:
            print(f"  gap [{lo:,} - {hi:,}]")
        for lo, hi, total in snap["saturated"]:
            print(f"  saturated [{lo:,} - {hi:,}] total {total}")
    elif args.cmd == "next-batch":
        if _paths(root)["progress"].exists():
            attach_order(root)
        batch = next_batch(root, args.size)
        print(json.dumps({"batch": batch["id"], "n": len(batch["symbols"])}))
        for k in range(0, len(batch["symbols"]), SYMBOLS_PER_CALL):
            print(json.dumps(batch["symbols"][k:k + SYMBOLS_PER_CALL]))
    elif args.cmd == "ingest":
        expect = [s.strip().upper() for s in args.expect.split(",") if s.strip()]
        print(json.dumps(ingest(root, args.batch, args.as_of, args.payloads,
                                origin=args.origin, expect=expect, close=not args.keep_open,
                                replace=args.replace)))
    elif args.cmd == "report":
        _print_report(report(root))


if __name__ == "__main__":
    main()
