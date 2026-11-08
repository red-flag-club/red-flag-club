"""Layer 3 rules on synthetic data (spec 008: the public version).

The RYDE path is synthetic (scripts/make_synthetic.py) but anchored to the
publicly reported levels of September 2024: 09-11 closed at $13.11 after a
$22.49 high, and 09-12 opened at $5.50. The position and orders are made up.
The private repo runs the same checks on the real data.
"""

import json
import pathlib

import pytest

from src.event_sets import clean_bars
from src.layer3 import Order, abandoned, ladder, liquidate, time_stop_date

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "synthetic" / "historicals.json"
SHARES = 1_000                       # a made-up position


def _ryde_bars():
    raw = json.loads(FIXTURE.read_text())
    bars_raw = next(r["bars"] for r in raw["data"]["results"] if r["symbol"] == "RYDE")
    bars, _ = clean_bars(bars_raw, "2026-10-08")
    return bars


# ---------------------------------------------------------------- L3.1

def test_time_stop_counts_sessions_from_the_first_entry():
    sessions = [b.date for b in _ryde_bars()]
    assert time_stop_date("2024-09-09", sessions) == "2024-09-11"
    assert time_stop_date("2024-09-06", sessions, n=2) == "2024-09-10"   # weekend skipped
    assert time_stop_date(sessions[-1], sessions) is None


def test_time_stop_rejects_a_non_session_entry_date():
    with pytest.raises(ValueError):
        time_stop_date("2024-09-07", [b.date for b in _ryde_bars()])     # a Saturday


def test_selling_at_the_time_stop_beats_holding_through_the_gap():
    bars = _ryde_bars()
    close_0911 = liquidate(bars, "2024-09-11", SHARES, at="close")
    open_0912 = liquidate(bars, "2024-09-12", SHARES, at="open")
    assert close_0911.price == 13.11 and open_0912.price == 5.5
    assert round(close_0911.proceeds) == 13_110 and round(open_0912.proceeds) == 5_500
    # One more night held cost more than half of what was left.
    assert open_0912.proceeds < 0.5 * close_0911.proceeds


def test_gap_fills_at_the_open_not_at_any_stop_level():
    f = liquidate(_ryde_bars(), "2024-09-12", 100, at="open")
    assert f.price == 5.5                       # 09-11 closed at 13.11


# ---------------------------------------------------------------- L3.2

def test_ladder_sells_two_thirds_on_limits_and_leaves_the_rest_to_the_time_stop():
    rungs = ladder(10.0, 999)
    assert [(r.limit_price, r.shares) for r in rungs] == [(12.5, 333), (15.0, 333), (0.0, 333)]
    assert sum(r.shares for r in rungs) == 999


def test_ladder_never_produces_a_buy_or_more_shares_than_held():
    for shares in (1, 2, 3, 7, 100):
        rungs = ladder(5.0, shares)
        assert sum(r.shares for r in rungs) == shares
        assert all(r.shares > 0 for r in rungs)


# ---------------------------------------------------------------- L3.4

XYZ = [                              # made-up order history
    Order("2025-02-03", "buy", "filled", "2025-02-03"),
    Order("2025-02-10", "sell", "cancelled", "2025-05-01"),
]


def test_abandoned_fires_30_days_after_the_last_exit_order_died():
    assert abandoned(XYZ, "2025-05-30") is None
    flag = abandoned(XYZ, "2025-05-31")
    assert flag and flag["flag"] == "ABANDONED" and flag["days"] == 30


def test_abandoned_ignores_a_cancellation_not_yet_known():
    assert abandoned(XYZ, "2025-04-15") is None             # the sell was still resting
    assert abandoned(XYZ, "2025-03-01") is None


def test_a_replacement_order_clears_the_flag():
    assert abandoned(XYZ + [Order("2025-05-10", "sell", "open")], "2025-06-30") is None


def test_orders_placed_after_as_of_are_ignored():
    assert abandoned(XYZ + [Order("2025-06-15", "sell", "open")], "2025-06-02")["flag"] == "ABANDONED"
