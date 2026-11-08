"""Tests for L1.2 (src/collapse_events.py)."""

from dataclasses import dataclass

from src.collapse_events import find_runs


@dataclass(frozen=True)
class _Bar:
    """Minimal PricedBar: just date + close. Deliberately not layer1.Bar,
    to prove the label doesn't need OHLCV, just closing price."""
    date: str
    c: float


def _series(closes: list[float]) -> list[_Bar]:
    return [_Bar(date=f"2024-01-{i + 1:02d}", c=c) for i, c in enumerate(closes)]


def test_ramp_then_deep_drawdown_is_labelled_collapsed():
    # 10 -> 21 (+110%) by session 3, then down to 5 (-76% from peak) by
    # session 15 (12 sessions after the peak, within the 20-session limit).
    bars = _series([10, 12, 15, 21, 19, 18, 17, 16, 15, 14, 13, 12, 10, 8, 6, 5])

    runs = find_runs("TEST", bars)

    assert len(runs) == 1
    run = runs[0]
    assert run.ramp_start_date == "2024-01-01"
    assert run.peak_date == "2024-01-04"
    assert run.peak_price == 21.0
    assert run.run_up_pct == 1.1
    assert run.trough_date == "2024-01-16"
    assert run.trough_price == 5.0
    assert run.drawdown_pct == 1 - 5 / 21
    assert run.collapsed is True


def test_ramp_without_deep_drawdown_is_a_control():
    # Same ramp (10 -> 21), but the pullback only reaches 15 (-29% from
    # peak) - a biotech-readout-shaped run, not a collapse.
    bars = _series([10, 12, 15, 21, 19, 18, 17, 16, 15, 16, 17, 18, 19, 20])

    runs = find_runs("TEST", bars)

    assert len(runs) == 1
    run = runs[0]
    assert run.peak_price == 21.0
    assert run.trough_price == 15.0
    assert run.drawdown_pct == 1 - 15 / 21
    assert run.collapsed is False


def test_run_up_under_100_percent_is_not_a_qualifying_run():
    # 10 -> 15 is only +50%.
    bars = _series([10, 11, 12, 13, 14, 15])

    assert find_runs("TEST", bars) == []


def test_run_up_over_more_than_10_sessions_does_not_qualify():
    # Doubles eventually, but only after 12 sessions - outside the
    # <= 10-session ramp window, so no run should be reported.
    bars = _series([10, 10.5, 11, 11.5, 12, 12.5, 13, 14, 15, 16, 18, 20, 21])

    assert find_runs("TEST", bars) == []


def test_peak_near_end_of_series_has_no_trough_data_yet():
    # The ramp completes on the very last bar available - there is no
    # subsequent data to search for a trough, so the run is reported
    # un-collapsed rather than the function guessing or crashing.
    bars = _series([10, 12, 15, 21])

    runs = find_runs("TEST", bars)

    assert len(runs) == 1
    run = runs[0]
    assert run.peak_price == 21.0
    assert run.trough_date is None
    assert run.trough_price is None
    assert run.drawdown_pct is None
    assert run.collapsed is False


def test_two_independent_runs_are_both_reported_once_each():
    ramp_and_collapse = [10, 12, 15, 21, 19, 17, 15, 12, 10, 8, 6, 5]
    # Long enough that the first run's 20-session trough search (which
    # starts right after its own peak) can't reach into the second ramp.
    flat = [5] * 15
    second_ramp_and_collapse = [5, 6, 8, 11, 10, 9, 8, 6, 4, 2, 1.4]
    bars = _series(ramp_and_collapse + flat + second_ramp_and_collapse)

    runs = find_runs("TEST", bars)

    assert len(runs) == 2
    assert runs[0].collapsed is True
    assert runs[1].collapsed is True
    assert runs[0].peak_date != runs[1].peak_date
