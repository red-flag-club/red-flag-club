import json
import pathlib

import pytest

from src.event_sets import LookaheadError, clean_bars, label_events
from src.harness import INDEX_HOLE_DAYS, issuers, metrics, point_in_time, replay, Replay
from src.layer1 import structural_score

from tests.fixture_data import HISTORICALS as FIXTURE

# RYDE's filing index as returned by get_sec_filing_index(until=2024-09-06):
# five 6-Ks, the last on 2024-06-21. Later rows stand in for the future.
RYDE_FILINGS = [["2024-03-06", "6-K"], ["2024-03-08", "6-K"], ["2024-03-15", "6-K"],
                ["2024-06-07", "6-K"], ["2024-06-21", "6-K"],
                ["2024-10-15", "6-K"], ["2025-04-30", "20-F"]]


def _ryde_event():
    raw = json.loads(FIXTURE.read_text())
    bars_raw = next(r["bars"] for r in raw["data"]["results"] if r["symbol"] == "RYDE")
    bars, _ = clean_bars(bars_raw, "2026-10-08")
    (pos,) = [e for e in label_events("RYDE", bars, "2026-10-08", origin="seed", batch="seed")
              if e["label"] == "positive"]
    return pos, bars[0].date


# ---------------------------------------------------------------- point in time

def test_point_in_time_ignores_later_filings_and_results():
    early = point_in_time("2024-09-06", RYDE_FILINGS[:5], [], "2024-03-05")
    late = point_in_time("2024-09-06", RYDE_FILINGS, [["2024-12-31", -5.0]], "2024-03-05")
    assert early == late


def test_ryde_point_in_time_matches_the_reference_case():
    pit = point_in_time("2024-09-06", RYDE_FILINGS, [], "2024-03-05")
    assert pit.foreign is True                  # 6-K only
    assert pit.recent_listing is True           # first bar six months earlier
    assert pit.stale_disclosure is True and pit.days_since_last_filing == 77
    assert pit.small_float is None and pit.small_cap is None and pit.unprofitable is None


def test_first_bar_after_as_of_is_lookahead():
    with pytest.raises(LookaheadError):
        point_in_time("2024-01-01", [], [], "2024-03-05")


def test_old_last_filing_is_a_coverage_hole_not_silence():
    # JAGX: nothing in the index between 2021 and 2026-09 though it filed quarterly.
    pit = point_in_time("2026-06-01", [["2021-03-01", "10-K"]], [], "2022-01-03")
    assert pit.stale_disclosure is None
    pit = point_in_time("2021-03-31", [["2021-03-01", "10-K"]], [], None)
    assert pit.stale_disclosure is False and INDEX_HOLE_DAYS > 30


def test_annual_result_is_public_only_after_the_lag():
    annuals = [["2023-12-31", -1e6]]
    assert point_in_time("2024-03-31", [], annuals, None).unprofitable is None
    assert point_in_time("2024-05-01", [], annuals, None).unprofitable is True


def test_listing_age_is_unknown_when_data_starts_too_late_to_tell():
    assert point_in_time("2022-06-01", [], [], "2022-01-03").recent_listing is None
    assert point_in_time("2023-12-01", [], [], "2022-01-03").recent_listing is False
    assert point_in_time("2022-06-01", [], [], "2022-04-22").recent_listing is True


def test_unknowns_bound_the_score_from_both_sides():
    pit = point_in_time("2024-09-06", RYDE_FILINGS, [], "2024-03-05")
    lo, hi = issuers("RYDE", pit)
    assert structural_score(lo)[0] == 3         # the three known red flags
    assert structural_score(hi)[0] == 6         # plus float, cap, income unknown


# ---------------------------------------------------------------- replay

def test_ryde_blocks_before_its_peak_on_the_hi_bound():
    event, first_bar = _ryde_event()
    r = replay(event, RYDE_FILINGS, [], first_bar)
    assert r.first_block_hi is not None and r.first_block_hi >= 0
    assert r.first_block_lo is None             # 3/6 known flags is WARN, not BLOCK
    assert r.first_pump is not None


def test_no_lookahead_truncating_bars_cannot_add_a_block():
    event, first_bar = _ryde_event()
    full = replay(event, RYDE_FILINGS, [], first_bar)
    dates = [b[0] for b in event["bars"]]
    peak = dates.index(event["peak_date"])
    cut = dict(event, bars=event["bars"][: peak + 1])   # drop everything after the peak
    assert replay(event, RYDE_FILINGS, [], first_bar) == full
    assert replay(cut, RYDE_FILINGS, [], first_bar) == full


def test_no_lookahead_filings_and_results_after_the_peak_cannot_change_a_replay():
    event, first_bar = _ryde_event()
    base = replay(event, RYDE_FILINGS[:5], [], first_bar)
    later = [["2024-09-07", "10-K"], ["2025-04-30", "20-F"]]
    assert replay(event, RYDE_FILINGS[:5] + later, [["2025-12-31", 1e9]], first_bar) == base


# ---------------------------------------------------------------- metrics

def _r(label, first_hi, n_hi=1):
    return Replay("X|a|b", label, 10, None, first_hi, first_hi, 0, n_hi if first_hi is not None else 0, ())


def test_metrics_count_recall_lead_and_fp_with_n():
    pos = [_r("positive", 3), _r("positive", 0), _r("positive", None), _r("positive", 5)]
    ctl = [_r("control", 1), _r("control", None), _r("control", None), _r("control", None)]
    m = metrics(pos, ctl, "hi", control_weight=2.0)
    assert (m["n_positives"], m["recall"], m["recall_lead_ge_2"], m["median_lead"]) == (4, 0.75, 0.5, 3)
    assert (m["n_controls"], m["fp_rate"]) == (4, 0.25)
    assert m["latch_precision"] == round(3 / (3 + 2), 3)


# ---------------------------------------------------------------- tuning rule

def test_tuning_never_trades_recall_for_precision_when_the_gate_is_out_of_reach():
    import scripts.l14 as cli
    row = lambda rec, fp: {"recall": rec, "median_lead": 2, "fp_rate": fp}
    rows = [(4, row(0.78, 0.78)), (6, row(0.23, 0.19))]
    assert cli.choose(rows, 4) == (4, "gate not met at any value; kept")
    rows.append((5, row(0.86, 0.30)))
    assert cli.choose(rows, 4)[0] == 5
