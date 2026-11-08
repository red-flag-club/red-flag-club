"""Synthetic price fixtures for the public test suite (spec 008, FR-003/FR-004).

    python3 scripts/make_synthetic.py            # writes tests/fixtures/synthetic/

The real test fixtures are cut from brokerage payloads, which are licensed to
the account holder and are not redistributed. These files are **not market
data**: each symbol's path is a handful of keyframes rounded to two
significant figures (the shape publicly reported for these episodes), filled
in between with seeded noise. For RYDE's week in September 2024 the widely
reported levels are used as anchors (08-22 close $8.65, 09-06 close $17.33,
peak $22.49, 09-11 close $13.11, 09-12 open $5.50, low $0.76). The output has the brokerage payload's shape, so the
same parsing code is exercised, including gap-fill bars flagged
`interpolated`, an all-zero pre-listing placeholder and zero-volume bars.

Deterministic: the same script always writes the same bytes.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "synthetic"
SEED = 8                     # spec 008
MAX_GAP_DAYS = 15            # a longer gap between keyframes means "no bars here"

HOLIDAYS = {                 # NYSE full-day closures
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29", "2023-06-19", "2023-07-04",
    "2023-09-04", "2023-11-23", "2023-12-25",
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27", "2024-06-19", "2024-07-04",
    "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19",
    "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25",
}

# (date, close, volume) keyframes, two significant figures.
RYDE = [
    ("2024-03-05", 4.0, 0), ("2024-03-12", 6.5, 520000), ("2024-03-19", 5.3, 68000),
    ("2024-03-26", 4.6, 27000), ("2024-04-03", 2.8, 60000), ("2024-04-10", 2.1, 180000),
    ("2024-04-17", 3.8, 1200000), ("2024-04-24", 3.7, 330000), ("2024-05-01", 3.9, 210000),
    ("2024-05-08", 7.4, 430000), ("2024-05-15", 7.6, 700000), ("2024-05-22", 8.3, 730000),
    ("2024-05-30", 9.2, 790000), ("2024-06-06", 7.9, 2100000), ("2024-06-13", 7.0, 98000),
    ("2024-06-21", 4.8, 96000), ("2024-06-28", 6.1, 150000), ("2024-07-08", 6.4, 370000),
    ("2024-07-15", 7.4, 180000), ("2024-07-22", 6.8, 110000), ("2024-07-29", 6.9, 110000),
    ("2024-08-05", 6.7, 580000), ("2024-08-12", 7.3, 170000), ("2024-08-19", 8.7, 49000), ("2024-08-22", 8.65, 45000),
    ("2024-08-26", 8.4, 42000), ("2024-08-28", 7.4, 63000), ("2024-08-29", 7.0, 27000),
    ("2024-08-30", 7.2, 530000), ("2024-09-03", 7.7, 1100000), ("2024-09-04", 9.1, 2000000),
    ("2024-09-05", 12.0, 1300000), ("2024-09-06", 17.33, 670000), ("2024-09-09", 20.0, 5600000),
    ("2024-09-10", 20.0, 6700000), ("2024-09-11", 13.0, 8600000), ("2024-09-12", 2.1, 27000000),
    ("2024-09-13", 1.9, 8900000), ("2024-09-16", 1.6, 2700000), ("2024-09-17", 1.5, 2800000),
    ("2024-09-24", 1.2, 1900000), ("2024-10-01", 0.72, 1200000), ("2024-10-08", 0.71, 480000),
    ("2024-10-15", 0.7, 740000), ("2024-10-22", 0.67, 480000), ("2024-10-29", 0.59, 720000),
    ("2024-11-05", 0.48, 270000), ("2024-11-12", 0.49, 610000), ("2024-11-19", 0.43, 370000),
    ("2024-11-26", 0.43, 260000), ("2024-11-29", 0.41, 84000),
    ("2024-12-06", 0.38, 150000), ("2024-12-13", 0.34, 120000), ("2024-12-20", 0.31, 140000),
    ("2024-12-23", 0.31, 300000), ("2024-12-27", 0.63, 5000000), ("2025-01-03", 0.55, 900000),
    ("2025-01-10", 0.5, 400000), ("2025-01-17", 0.45, 300000), ("2025-01-29", 0.39, 290000),
    ("2025-02-07", 0.37, 200000), ("2025-02-14", 0.36, 180000),
]
# Publicly reported OHLC for the dump week (open, high, low, close).
RYDE_OHLC = {
    "2024-09-04": (7.3, 9.5, 7.3, 9.1), "2024-09-05": (9.2, 12.8, 8.6, 12.0),
    "2024-09-06": (12.0, 17.44, 11.7, 17.33), "2024-09-09": (16.0, 20.3, 13.5, 20.0),
    "2024-09-10": (19.9, 21.9, 18.5, 20.0), "2024-09-11": (21.54, 22.49, 13.11, 13.11),
    "2024-09-12": (5.5, 5.8, 0.76, 2.1), "2024-09-13": (1.8, 2.2, 1.5, 1.9),
}
RETO = [
    ("2023-04-03", 140000.0, 0), ("2023-04-11", 110000.0, 5), ("2023-04-18", 120000.0, 0),
    ("2023-04-25", 110000.0, 1), ("2023-05-02", 110000.0, 1), ("2023-05-09", 96000.0, 0),
    ("2023-05-16", 94000.0, 15), ("2023-05-23", 78000.0, 2), ("2023-05-31", 57000.0, 1),
    ("2023-06-07", 57000.0, 0), ("2023-06-14", 56000.0, 3), ("2023-06-22", 46000.0, 3),
    ("2023-06-29", 44000.0, 2), ("2023-07-07", 46000.0, 1), ("2023-07-14", 61000.0, 22),
    ("2023-07-21", 70000.0, 38), ("2023-07-28", 90000.0, 30), ("2023-08-01", 98000.0, 10),
    ("2023-08-02", 110000.0, 48), ("2023-08-03", 120000.0, 350), ("2023-08-04", 110000.0, 100),
    ("2023-08-07", 120000.0, 35), ("2023-08-08", 120000.0, 84), ("2023-08-09", 120000.0, 190),
    ("2023-08-10", 120000.0, 72), ("2023-08-11", 140000.0, 45), ("2023-08-14", 160000.0, 37),
    ("2023-08-15", 160000.0, 110), ("2023-08-16", 200000.0, 36), ("2023-08-17", 190000.0, 25),
    ("2023-08-18", 240000.0, 29), ("2023-08-21", 240000.0, 40), ("2023-08-22", 270000.0, 10),
    ("2023-08-23", 270000.0, 110), ("2023-08-24", 46000.0, 540), ("2023-08-25", 44000.0, 260),
    ("2023-08-28", 37000.0, 71), ("2023-08-29", 32000.0, 89), ("2023-08-30", 42000.0, 220),
    ("2023-08-31", 40000.0, 47), ("2023-09-01", 40000.0, 16), ("2023-09-05", 37000.0, 16),
    ("2023-09-06", 39000.0, 22), ("2023-09-07", 38000.0, 6), ("2023-09-08", 25000.0, 80),
    ("2023-09-11", 23000.0, 25), ("2023-09-12", 25000.0, 18), ("2023-09-13", 23000.0, 8),
    ("2023-09-14", 23000.0, 6), ("2023-09-15", 23000.0, 4), ("2023-09-18", 22000.0, 2),
    ("2023-09-19", 22000.0, 2), ("2023-09-20", 23000.0, 4), ("2023-09-25", 24000.0, 4),
    ("2023-10-02", 24000.0, 9), ("2023-10-09", 21000.0, 1), ("2023-10-16", 28000.0, 2),
    ("2023-10-23", 32000.0, 3), ("2023-10-30", 28000.0, 0), ("2023-11-06", 27000.0, 0),
    ("2023-11-13", 26000.0, 1), ("2023-11-20", 25000.0, 3), ("2023-11-28", 24000.0, 1),
    ("2026-05-05", 48.0, 960), ("2026-05-12", 49.0, 750), ("2026-05-19", 45.0, 490),
    ("2026-05-27", 43.0, 720), ("2026-06-03", 47.0, 7500), ("2026-06-10", 59.0, 40000),
    ("2026-06-17", 54.0, 520), ("2026-06-25", 47.0, 350), ("2026-07-02", 54.0, 110),
    ("2026-07-10", 56.0, 1100), ("2026-07-17", 59.0, 660), ("2026-07-24", 55.0, 210),
    ("2026-07-31", 56.0, 310), ("2026-08-07", 59.0, 260), ("2026-08-14", 26.0, 7600),
    ("2026-08-21", 32.0, 10000), ("2026-08-25", 32.0, 2800), ("2026-08-26", 28.0, 10000),
    ("2026-08-27", 28.0, 3700), ("2026-08-28", 26.0, 5200), ("2026-08-31", 27.0, 9600),
    ("2026-09-01", 25.0, 7700), ("2026-09-02", 25.0, 1900), ("2026-09-03", 21.0, 17000),
    ("2026-09-04", 21.0, 1800), ("2026-09-08", 11.0, 91000), ("2026-09-09", 8.4, 50000),
    ("2026-09-10", 8.2, 17000), ("2026-09-11", 7.8, 17000), ("2026-09-14", 7.2, 12000),
    ("2026-09-15", 56.0, 12000000), ("2026-09-16", 37.0, 7500000), ("2026-09-17", 4.2, 17000000),
    ("2026-09-18", 3.7, 8000000), ("2026-09-21", 3.8, 4000000), ("2026-09-22", 3.5, 1700000),
    ("2026-09-23", 3.2, 1900000), ("2026-09-24", 3.3, 8200000), ("2026-09-25", 3.1, 1800000),
    ("2026-09-28", 2.8, 1400000), ("2026-09-29", 1.8, 3700000), ("2026-09-30", 2.3, 21000000),
    ("2026-10-01", 1.9, 1900000), ("2026-10-02", 1.6, 6200000), ("2026-10-05", 1.9, 19000000),
    ("2026-10-06", 1.7, 1900000), ("2026-10-07", 1.6, 1000000),
]
XRPN = [
    ("2026-06-01", 10.0, 32000), ("2026-06-08", 10.0, 94000), ("2026-06-15", 10.0, 43000),
    ("2026-06-23", 10.0, 30000), ("2026-06-30", 10.0, 41000), ("2026-07-08", 10.0, 39000),
    ("2026-07-15", 10.0, 23000), ("2026-07-22", 10.0, 13000), ("2026-07-29", 10.0, 24000),
    ("2026-08-05", 10.0, 13000), ("2026-08-12", 10.0, 40000), ("2026-08-19", 10.0, 26000),
    ("2026-08-26", 11.0, 11000), ("2026-09-02", 11.0, 49000), ("2026-09-10", 11.0, 70000),
    ("2026-09-17", 11.0, 110000), ("2026-09-24", 11.0, 98000), ("2026-10-01", 23.0, 2400000),
    ("2026-10-07", 25.0, 3500000),
]

# SEC filing index entries (form, filed date) for the reference symbols. SEC
# EDGAR filings are public records; these are the forms and dates only.
FILINGS_SOURCE = ROOT / "data" / "l14" / "filings.json"     # private repo only
FILINGS_SYMBOLS = ("RYDE", "RETO", "XRPN", "DJT")


def sessions(start: str, end: str) -> list[str]:
    d, stop, out = dt.date.fromisoformat(start), dt.date.fromisoformat(end), []
    while d <= stop:
        s = d.isoformat()
        if d.weekday() < 5 and s not in HOLIDAYS:
            out.append(s)
        d += dt.timedelta(days=1)
    return out


def _bar(date: str, o: float, h: float, l: float, c: float, v: float, interpolated: bool = False) -> dict:
    b = {"begins_at": f"{date}T00:00:00Z", "open_price": f"{o:.6f}", "close_price": f"{c:.6f}",
         "high_price": f"{h:.6f}", "low_price": f"{l:.6f}", "volume": int(v), "session": "reg"}
    if interpolated:
        b["interpolated"] = True
    return b


def path(keyframes, rng: random.Random, ohlc: dict | None = None) -> list[dict]:
    """Log-linear between keyframes with seeded noise; keyframe days exact."""
    out, prev_c = [], None
    for (d0, c0, v0), (d1, c1, v1) in zip(keyframes, keyframes[1:] + [keyframes[-1]]):
        gap = (dt.date.fromisoformat(d1) - dt.date.fromisoformat(d0)).days
        days = sessions(d0, d1)[:-1] if 0 < gap <= MAX_GAP_DAYS else [d0]
        for i, d in enumerate(days):
            t = i / max(len(days), 1)
            c = math.exp(math.log(c0) + t * (math.log(c1) - math.log(c0)))
            v = math.exp(math.log(v0 + 1) + t * (math.log(v1 + 1) - math.log(v0 + 1))) - 1
            if i:                                   # keyframe days stay exact
                c *= 1 + rng.uniform(-0.02, 0.02)
                v *= rng.uniform(0.7, 1.3)
            c = float(f"{c:.4g}")
            if ohlc and d in ohlc:
                o, h, l, c = ohlc[d]
            else:
                o = c if prev_c is None else float(f"{prev_c * (1 + rng.uniform(-0.015, 0.015)):.4g}")
                h = float(f"{max(o, c) * (1 + rng.uniform(0, 0.03)):.4g}")
                l = float(f"{min(o, c) * (1 - rng.uniform(0, 0.03)):.4g}")
            out.append(_bar(d, o, h, l, c, max(v, 0)))
            prev_c = c
    return out


def historicals() -> dict:
    rng = random.Random(SEED)
    ryde = [_bar(d, 0, 0, 0, 0, 0, interpolated=True) for d in sessions("2024-01-02", "2024-02-28")]
    ryde += [_bar(d, 0, 0, 0, 0, 0) for d in ("2024-02-29", "2024-03-01", "2024-03-04")]   # placeholders
    ryde += path(RYDE, rng, RYDE_OHLC)
    ryde[-len(RYDE_OHLC) - 40]["volume"] = 0                                             # one zero-volume bar
    results = [{"symbol": "RYDE", "interval": "day", "bounds": "regular", "bars": ryde}]
    results.append({"symbol": "RETO", "interval": "day", "bounds": "regular", "bars": path(RETO, rng)})
    results.append({"symbol": "XRPN", "interval": "day", "bounds": "regular", "bars": path(XRPN, rng)})
    return {"data": {"results": results}, "synthetic": True,
            "note": "Synthetic, not market data. See scripts/make_synthetic.py."}


def seed_events(payload: dict, as_of: str = "2026-10-08") -> list[dict]:
    sys.path.insert(0, str(ROOT))
    from src.event_sets import clean_bars, label_events
    rows = []
    for r in payload["data"]["results"]:
        bars, _ = clean_bars(r["bars"], as_of)
        for e in label_events(r["symbol"], bars, as_of, origin="seed", batch="seed"):
            e["synthetic"] = True
            rows.append(e)
    return rows


def scan_band() -> dict:
    """A scanner page in the brokerage's shape, with made-up tickers."""
    rows = []
    for i, sym in enumerate(("AAAA", "BBBB", "CCCC", "DDDD", "EEEE")):
        cap = 9_000_000 - i * 1_500_000
        rows.append({"ticker": sym, "instrument_type": "EQUITY", "columns": {
            "Symbol": sym, "Name": f"Synthetic Company {sym}", "Asset type": "STOCK",
            "Last": f"{11 - i * 1.5:.2f}", "Market cap": f"{cap:.4e}", "Float": str(800_000 - i * 50_000),
            "Shares outstanding": str(900_000 - i * 50_000), "Average volume": str(3_500 + i * 100)}})
    return {"data": {"result": {
        "total_items": 384, "results": rows, "sorted_by": "Last desc",
        "filters_applied": [
            {"filter_type": "Asset type", "filter_type_enum": "FILTER_TYPE_INSTRUMENT_TYPE", "predicate": "=",
             "values": ["STOCK"], "expression": "type"},
            {"filter_type": "Market cap", "filter_type_enum": "FILTER_TYPE_MARKET_CAP", "predicate": "BETWEEN",
             "values": ["0", "10000000"], "expression": "fundamental.marketCap"}]}},
        "synthetic": True}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = historicals()
    (OUT / "historicals.json").write_text(json.dumps(payload, indent=1) + "\n")
    (OUT / "preview_scan_band.json").write_text(json.dumps(scan_band(), indent=1) + "\n")
    (OUT / "events_seed.jsonl").write_text("".join(json.dumps(e) + "\n" for e in seed_events(payload)))
    if FILINGS_SOURCE.exists():
        src = json.loads(FILINGS_SOURCE.read_text())
        fil = {s: src.get(s, []) for s in FILINGS_SYMBOLS}
        (OUT / "filings.json").write_text(json.dumps(fil, indent=1) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
