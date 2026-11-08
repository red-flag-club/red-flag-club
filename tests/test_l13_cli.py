import importlib.util
import json
import pathlib

import pytest

from tests.fixture_data import FIRST_BAND_SYMBOL, HISTORICALS, SCAN_BAND

HERE = pathlib.Path(__file__).parent

_spec = importlib.util.spec_from_file_location("l13", HERE.parent / "scripts" / "l13.py")
l13 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(l13)


def _scan_payload(tmp, name, lo, hi, tickers, total=None):
    rows = [{"ticker": t, "columns": {"Market cap": str(lo + 1), "Float": "1000", "Name": t}} for t in tickers]
    payload = {"data": {"result": {
        "total_items": len(tickers) if total is None else total,
        "results": rows,
        "filters_applied": [
            {"filter_type_enum": "FILTER_TYPE_INSTRUMENT_TYPE", "predicate": "=", "values": ["STOCK"]},
            {"filter_type_enum": "FILTER_TYPE_MARKET_CAP", "predicate": "BETWEEN", "values": [str(lo), str(hi)]},
        ],
    }}}
    path = tmp / name
    path.write_text(json.dumps(payload))
    return path


def _hist_payload(tmp, name, symbols, fixture_symbols=("RYDE", "RETO", "XRPN")):
    real = json.loads(HISTORICALS.read_text())["data"]["results"]
    by_sym = {r["symbol"]: r for r in real}
    results = []
    for s in symbols:
        src = by_sym.get(s) or by_sym["XRPN"]
        results.append({**src, "symbol": s})
    path = tmp / name
    path.write_text(json.dumps({"data": {"results": results}}))
    return path


# ---------------------------------------------------------------- universe

def test_parse_band_reads_bounds_from_echoed_filter():
    payload = json.loads(SCAN_BAND.read_text())["data"]
    band = l13.parse_band(payload, "2026-10-08")
    assert (band["lo"], band["hi"]) == (0, 10_000_000)
    assert band["total_items"] == 384 and band["saturated"] is True
    assert band["tickers"][0]["symbol"] == FIRST_BAND_SYMBOL


def test_universe_add_replaces_same_bounds_and_build_dedupes(tmp_path):
    l13.universe_add(tmp_path, [_scan_payload(tmp_path, "a", 0, 250_000_000, ["AAA", "BBB"], total=999)], "d")
    l13.universe_add(tmp_path, [_scan_payload(tmp_path, "b", 0, 250_000_000, ["AAA", "CCC"])], "d")
    l13.universe_add(tmp_path, [_scan_payload(tmp_path, "c", 250_000_000, 500_000_000, ["CCC", "DDD"])], "d")
    snap = l13.universe_build(tmp_path, "2026-10-08")
    assert snap["complete"] is True
    assert snap["symbols"] == ["AAA", "CCC", "DDD"]
    assert len(snap["bands"]) == 2


def test_saturated_band_leaves_a_gap_until_split(tmp_path):
    l13.universe_add(tmp_path, [_scan_payload(tmp_path, "a", 0, 10, ["A"], total=300)], "d")
    l13.universe_add(tmp_path, [_scan_payload(tmp_path, "b", 10, 500_000_000, ["B"])], "d")
    snap = l13.universe_build(tmp_path, "x")
    assert snap["complete"] is False
    assert snap["gaps"] == [(0, 10)]
    l13.universe_add(tmp_path, [_scan_payload(tmp_path, "c", 0, 5, ["A"]), _scan_payload(tmp_path, "d", 5, 10, ["C"])], "d")
    assert l13.universe_build(tmp_path, "x")["complete"] is True


def test_coverage_gaps_middle_and_tail():
    bands = [{"lo": 0, "hi": 10, "saturated": False}, {"lo": 20, "hi": 30, "saturated": False}]
    assert l13.coverage_gaps(bands, 0, 40) == [(10, 20), (30, 40)]


# ---------------------------------------------------------------- batches

def _universe(tmp_path, symbols):
    l13.universe_add(tmp_path, [_scan_payload(tmp_path, "u", 0, 500_000_000, symbols)], "d")
    l13.universe_build(tmp_path, "2026-10-08")


def test_incomplete_universe_blocks_batches(tmp_path):
    l13.universe_add(tmp_path, [_scan_payload(tmp_path, "u", 0, 10, ["A"])], "d")
    l13.universe_build(tmp_path, "2026-10-08")
    with pytest.raises(SystemExit):
        l13.next_batch(tmp_path, 5)


def test_order_is_seeded_and_next_batch_resumes_open_batch(tmp_path):
    syms = [f"S{i:02d}" for i in range(30)]
    _universe(tmp_path, syms)
    b1 = l13.next_batch(tmp_path, 12)
    assert b1["id"] == "b001" and len(b1["symbols"]) == 12
    assert l13.next_batch(tmp_path, 12) == b1  # still open -> same batch

    other = tmp_path / "other"
    other.mkdir()
    _universe(other, syms)
    assert l13.next_batch(other, 12)["symbols"] == b1["symbols"]  # same seed, same order


def test_ingest_labels_marks_missing_no_data_and_is_idempotent(tmp_path):
    _universe(tmp_path, ["RYDE", "RETO", "ZZZZ"])
    batch = l13.next_batch(tmp_path, 3)
    payload = _hist_payload(tmp_path, "h", ["RYDE", "RETO"])

    out = l13.ingest(tmp_path, batch["id"], "2026-10-08", [payload])
    assert out["missing"] == ["ZZZZ"] and out["new_events"] > 0

    progress = json.loads((tmp_path / "data/l13/progress.json").read_text())
    assert progress["done"]["ZZZZ"]["status"] == "no_data"
    assert progress["done"]["RYDE"]["dropped_nonpositive"] == 3

    again = l13.ingest(tmp_path, batch["id"], "2026-10-08", [payload])
    assert again["new_events"] == 0

    nxt = l13.next_batch(tmp_path, 3)
    assert nxt["symbols"] == [] and nxt["id"] == "b002"

    r = l13.report(tmp_path)
    assert r["scan"]["positive"] == 3  # RYDE 2024-09, RETO 2023-08 and 2026-09
    assert r["scan_symbols_processed"] == 3 and r["scan_symbols_with_data"] == 2
    assert r["gate"]["met"] is False


def test_seed_before_universe_then_scan_skips_seed_symbols(tmp_path):
    seed = _hist_payload(tmp_path, "s", ["RYDE", "XRPN"])  # payload carries an extra symbol
    l13.ingest(tmp_path, "seed", "2026-10-08", [seed], origin="seed", expect=["RYDE"])
    assert "XRPN" not in json.loads((tmp_path / "data/l13/progress.json").read_text())["done"]
    _universe(tmp_path, ["RYDE", "XRPN"])
    l13.attach_order(tmp_path)
    batch = l13.next_batch(tmp_path, 5)
    assert batch["symbols"] == ["XRPN"]

    r = l13.report(tmp_path)
    assert r["seed"]["positive"] == 1 and r["scan"]["positive"] == 0


def test_replace_relabels_one_batch_only(tmp_path):
    _universe(tmp_path, ["RYDE", "RETO"])
    seed = _hist_payload(tmp_path, "s", ["RETO"])
    l13.ingest(tmp_path, "seed", "2026-10-08", [seed], origin="seed", expect=["RETO"])
    l13.attach_order(tmp_path)
    b = l13.next_batch(tmp_path, 5)
    payload = _hist_payload(tmp_path, "h", ["RYDE"])
    l13.ingest(tmp_path, b["id"], "2026-10-08", [payload])
    before = l13.report(tmp_path)
    out = l13.ingest(tmp_path, b["id"], "2026-10-08", [payload], replace=True)
    assert out["new_events"] > 0
    assert l13.report(tmp_path) == before
