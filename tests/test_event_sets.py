import json
import pathlib

import pytest

from src.event_sets import (
    LookaheadError,
    clean_bars,
    label_events,
)

from tests.fixture_data import HISTORICALS as FIXTURE


def _raw(symbol: str) -> list[dict]:
    payload = json.loads(FIXTURE.read_text())
    return next(r["bars"] for r in payload["data"]["results"] if r["symbol"] == symbol)


def _bar(date, c, *, o=None, interpolated=None):
    o = c if o is None else o
    raw = {
        "begins_at": f"{date}T00:00:00Z",
        "open_price": str(o), "high_price": str(max(o, c)), "low_price": str(min(o, c)),
        "close_price": str(c), "volume": 1000, "session": "reg",
    }
    if interpolated is not None:
        raw["interpolated"] = interpolated
    return raw


def _series(closes, start_day=1):
    """Consecutive synthetic dates 2024-01-01, 2024-01-02, ... (calendar days are
    fine here: labelling counts bars, not trading days)."""
    import datetime as dt
    d0 = dt.date(2024, 1, start_day)
    return [_bar((d0 + dt.timedelta(days=i)).isoformat(), c) for i, c in enumerate(closes)]


# ---------------------------------------------------------------- hygiene

def test_clean_bars_drops_interpolated_and_counts_them():
    raw = [_bar("2024-01-02", 1.0), _bar("2024-01-03", 1.1, interpolated=True), _bar("2024-01-04", 1.2)]
    bars, stats = clean_bars(raw, as_of="2024-12-31")
    assert [b.date for b in bars] == ["2024-01-02", "2024-01-04"]
    assert (stats.total, stats.kept, stats.dropped_interpolated, stats.dropped_nonpositive) == (3, 2, 1, 0)


def test_clean_bars_drops_zero_price_placeholders_not_flagged_interpolated():
    # RYDE returns all-zero bars on 2024-02-29..03-04 with no `interpolated` flag.
    bars, stats = clean_bars(_raw("RYDE"), as_of="2026-10-08")
    assert stats.dropped_nonpositive == 3
    assert all(min(b.o, b.h, b.l, b.c) > 0 for b in bars)
    assert bars[0].date == "2024-03-05"
    assert stats.kept == stats.total - stats.dropped_interpolated - stats.dropped_nonpositive


def test_clean_bars_sorts_and_rejects_duplicate_dates():
    raw = [_bar("2024-01-03", 1.0), _bar("2024-01-02", 1.0)]
    assert [b.date for b in clean_bars(raw, "2024-12-31")[0]] == ["2024-01-02", "2024-01-03"]
    with pytest.raises(ValueError):
        clean_bars([_bar("2024-01-02", 1.0), _bar("2024-01-02", 2.0)], "2024-12-31")


# ---------------------------------------------------------------- lookahead

def test_clean_bars_refuses_bars_after_as_of():
    raw = [_bar("2024-01-02", 1.0), _bar("2024-01-03", 1.0)]
    with pytest.raises(LookaheadError):
        clean_bars(raw, as_of="2024-01-02")


def test_label_events_refuses_bars_after_as_of():
    bars, _ = clean_bars(_series([1.0] * 5), as_of="2024-12-31")
    with pytest.raises(LookaheadError):
        label_events("X", bars, as_of="2024-01-02", origin="scan", batch="t")


@pytest.mark.parametrize("symbol", ["RYDE", "RETO"])
def test_truncation_never_adds_a_positive(symbol):
    """Cutting the series at any date T can only remove positives, never create one."""
    full_bars, _ = clean_bars(_raw(symbol), as_of="2026-10-08")
    full = {e["peak_date"] for e in label_events(symbol, full_bars, "2026-10-08", origin="scan", batch="t")
            if e["label"] == "positive"}
    for i in range(30, len(full_bars)):
        t = full_bars[i].date
        cut = [b for b in full_bars if b.date <= t]
        got = {e["peak_date"] for e in label_events(symbol, cut, t, origin="scan", batch="t")
               if e["label"] == "positive"}
        assert got <= full, (t, got - full)


# ---------------------------------------------------------------- labels

def test_ryde_september_2024_is_a_positive():
    bars, _ = clean_bars(_raw("RYDE"), as_of="2026-10-08")
    events = label_events("RYDE", bars, "2026-10-08", origin="seed", batch="seed")
    pos = [e for e in events if e["label"] == "positive"]
    assert [e["peak_date"] for e in pos] == ["2024-09-06"]
    assert pos[0]["drawdown_pct"] >= 0.70
    assert pos[0]["origin"] == "seed" and pos[0]["batch"] == "seed"


def test_reto_has_two_positives():
    bars, _ = clean_bars(_raw("RETO"), as_of="2026-10-08")
    pos = [e["peak_date"] for e in label_events("RETO", bars, "2026-10-08", origin="seed", batch="seed")
           if e["label"] == "positive"]
    assert pos == ["2023-08-18", "2026-09-15"]


def test_unresolved_run_is_pending_not_control():
    # XRPN peaked 2026-10-01 with only a few sessions of data after it.
    bars, _ = clean_bars(_raw("XRPN"), as_of="2026-10-08")
    events = label_events("XRPN", bars, "2026-10-08", origin="scan", batch="t")
    last = events[-1]
    assert last["peak_date"] == "2026-10-01"
    assert last["label"] == "pending"
    assert last["sessions_after_peak"] < 20


def test_resolved_run_without_collapse_is_control():
    closes = [10.0] * 5 + [12, 15, 20, 21] + [20.0] * 25
    bars, _ = clean_bars(_series(closes), "2024-12-31")
    (e,) = label_events("X", bars, "2024-12-31", origin="scan", batch="t")
    assert e["label"] == "control"
    assert e["sessions_after_peak"] == 20


def test_collapse_already_happened_is_positive_even_if_window_incomplete():
    closes = [10.0] * 5 + [15, 25, 5]
    bars, _ = clean_bars(_series(closes), "2024-12-31")
    (e,) = label_events("X", bars, "2024-12-31", origin="scan", batch="t")
    assert e["label"] == "positive"


def test_event_window_spans_pre_ramp_to_end_of_trough_window():
    closes = [10.0] * 100 + [12, 15, 21] + [20.0] * 40
    bars, _ = clean_bars(_series(closes), "2024-12-31")
    (e,) = label_events("X", bars, "2024-12-31", origin="scan", batch="t")
    dates = [b[0] for b in e["bars"]]
    start_idx = next(i for i, b in enumerate(bars) if b.date == e["ramp_start_date"])
    peak_idx = next(i for i, b in enumerate(bars) if b.date == e["peak_date"])
    assert dates[0] == bars[start_idx - 60].date
    assert dates[-1] == bars[peak_idx + 20].date
    assert all(len(b) == 6 for b in e["bars"])


def test_single_bad_print_is_flagged_not_dropped():
    # REED 2023-01-25 shape: flat ~25, one bar at 1123.5, then back to ~22.
    closes = [25.0] * 15 + [1123.5, 22.47] + [22.0] * 25
    bars, _ = clean_bars(_series(closes), "2024-12-31")
    events = label_events("X", bars, "2024-12-31", origin="scan", batch="t")
    assert len(events) == 1
    assert events[0]["label"] == "positive"          # definition unchanged
    assert events[0]["isolated_spike_peak"] is True  # but flagged
    assert events[0]["suspect_bad_print"] is False   # synthetic volume is flat, not low


def test_low_volume_spike_is_a_suspect_bad_print_high_volume_spike_is_not():
    closes = [25.0] * 25 + [1123.5, 22.47] + [22.0] * 25
    low = _series(closes)
    for b in low:
        b["volume"] = 4000
    low[25]["volume"] = 196                       # REED-like: spike on no volume
    bars, _ = clean_bars(low, "2024-12-31")
    (e,) = label_events("X", bars, "2024-12-31", origin="scan", batch="t")
    assert e["suspect_bad_print"] is True

    high = _series(closes)
    for b in high:
        b["volume"] = 4000
    high[25]["volume"] = 27_949_319               # JAGX-like: a real one-day pump
    bars, _ = clean_bars(high, "2024-12-31")
    (e,) = label_events("X", bars, "2024-12-31", origin="scan", batch="t")
    assert e["isolated_spike_peak"] is True and e["suspect_bad_print"] is False


def test_real_ramp_is_not_flagged_as_spike():
    bars, _ = clean_bars(_raw("RYDE"), as_of="2026-10-08")
    (pos,) = [e for e in label_events("RYDE", bars, "2026-10-08", origin="seed", batch="seed")
              if e["label"] == "positive"]
    assert pos["isolated_spike_peak"] is False


def test_zero_volume_spike_is_suspect_even_when_the_stock_rarely_trades():
    # VCIG 2023-05-02 shape: the spike bar and most prior bars traded 0 shares.
    closes = [10.0] * 25 + [70.0, 14.0] + [10.0] * 25
    raw = _series(closes)
    for b in raw:
        b["volume"] = 0
    bars, _ = clean_bars(raw, "2024-12-31")
    (e,) = label_events("X", bars, "2024-12-31", origin="scan", batch="t")
    assert e["suspect_bad_print"] is True


def test_ghost_quote_is_flagged_stale_not_relabelled():
    # ELOX 2024-11 shape: flat bars flipping between two price levels 100x apart.
    closes = [0.0011] * 20 + [0.000011] * 3 + [0.0011] * 3 + [0.000011] * 25
    bars, _ = clean_bars(_series(closes), "2024-12-31")
    events = label_events("X", bars, "2024-12-31", origin="scan", batch="t")
    pos = [e for e in events if e["label"] == "positive"]
    assert pos                                       # definition unchanged
    assert all(e["stale_quote"] is True and e["flat_bar_share"] == 1.0 for e in pos)


def test_real_ramp_is_not_a_stale_quote():
    bars, _ = clean_bars(_raw("RYDE"), as_of="2026-10-08")
    (pos,) = [e for e in label_events("RYDE", bars, "2026-10-08", origin="seed", batch="seed")
              if e["label"] == "positive"]
    assert pos["stale_quote"] is False and pos["flat_bar_share"] < 0.1
