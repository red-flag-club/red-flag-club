import datetime as dt

import pytest

from scripts import monitor as M
from scripts import score_checks as S
from src.layer1 import Bar


def _bars(closes, start="2025-01-02"):
    d0 = dt.date.fromisoformat(start)
    return [Bar((d0 + dt.timedelta(days=i)).isoformat(), c * 0.99, c * 1.02, c * 0.97, c, 1e6)
            for i, c in enumerate(closes)]


POSITIONS = {"positions": [{"symbol": "HOOD", "quantity": "2", "average_buy_price": "120.00"}]}


def test_parse_positions_and_orders_tolerate_field_variants():
    assert M.parse_positions(POSITIONS) == [{"symbol": "HOOD", "quantity": 2.0, "average_cost": 120.0, "account": None}]
    orders = M.parse_orders({"orders": [
        {"symbol": "hood", "side": "buy", "state": "filled", "created_at": "2025-03-01T15:00:00Z",
         "last_transaction_at": "2025-03-01T15:00:01Z", "average_price": "100"},
        {"symbol": "HOOD", "side": "sell", "state": "canceled", "created_at": "2025-04-01T15:00:00Z",
         "updated_at": "2025-05-01T00:00:00Z"}]})
    assert orders[0]["symbol"] == "HOOD" and orders[1]["state"] == "cancelled"
    assert orders[1]["closed"] == "2025-05-01"


def test_first_entry_resets_after_a_full_sell():
    o = lambda side, d: {"symbol": "X", "side": side, "state": "filled", "placed": d, "closed": d}
    assert M.first_entry("X", [o("buy", "2025-01-02"), o("sell", "2025-02-01"),
                               o("buy", "2025-03-01"), o("buy", "2025-03-05")]) == "2025-03-01"


def test_holding_below_200_day_raises_exit_rule_and_loss():
    bars = _bars([100.0] * 220 + [80.0] * 10)
    pos = {"symbol": "X", "quantity": 2.0, "average_cost": 100.0}
    r = M.holding_report(pos, bars, [], bars[-1].date)
    assert any(a.startswith("EXIT RULE") for a in r["alerts"])
    assert any(a.startswith("LOSS") for a in r["alerts"])
    assert r["unrealized_pnl"] == -40.0


def test_time_stop_fires_only_for_a_veto_name_after_n_sessions():
    bars = _bars([10.0] * 240 + [10 * 1.08 ** k for k in range(1, 11)])     # pump profile -> VETO
    entry = bars[-6].date
    orders = [{"symbol": "X", "side": "buy", "state": "filled", "placed": entry, "closed": entry}]
    r = M.holding_report({"symbol": "X", "quantity": 1.0, "average_cost": 15.0}, bars, orders, bars[-1].date)
    assert r["check"]["verdict"] == "VETO"
    assert any(a.startswith("TIME STOP") for a in r["alerts"])
    calm = _bars([100.0 * (1 + 0.04 * ((-1) ** i)) for i in range(260)])     # volatile, CAUTION only
    orders = [{"symbol": "Y", "side": "buy", "state": "filled", "placed": calm[-10].date, "closed": calm[-10].date}]
    r = M.holding_report({"symbol": "Y", "quantity": 1.0, "average_cost": 100.0}, calm, orders, calm[-1].date)
    assert r["check"]["verdict"] == "CAUTION"
    assert not any(a.startswith("TIME STOP") for a in r["alerts"])


def test_abandoned_sell_is_reported():
    bars = _bars([100.0 + i * 0.05 for i in range(260)])
    asof = bars[-1].date
    old = (dt.date.fromisoformat(asof) - dt.timedelta(days=40)).isoformat()
    orders = [{"symbol": "X", "side": "buy", "state": "filled", "placed": bars[0].date, "closed": bars[0].date},
              {"symbol": "X", "side": "sell", "state": "cancelled", "placed": bars[10].date, "closed": old}]
    r = M.holding_report({"symbol": "X", "quantity": 1.0, "average_cost": 90.0}, bars, orders, asof)
    assert any(a.startswith("ABANDONED") for a in r["alerts"])


def test_monitor_refuses_bars_after_as_of():
    bars = _bars([10.0] * 40)
    with pytest.raises(M.K.LookaheadError):
        M.holding_report({"symbol": "X", "quantity": 1.0, "average_cost": 10.0}, bars, [], bars[-5].date)


def test_digest_and_log_are_written(tmp_path):
    bars = _bars([100.0 + i * 0.05 for i in range(260)])
    h = M.holding_report({"symbol": "X", "quantity": 1.0, "average_cost": 90.0}, bars, [], bars[-1].date)
    text = M.digest(bars[-1].date, [h], [])
    p = M.write(bars[-1].date, text, [h], [], out=tmp_path)
    assert p.exists() and "no orders were placed" in p.read_text()
    assert (tmp_path / "log.jsonl").read_text().count("\n") == 1


def test_scorecard_uses_only_later_bars_as_outcome():
    bars = _bars([100.0] * 10 + [90.0] * 30)
    checks = [{"symbol": "X", "as_of": bars[9].date, "verdict": "CAUTION"},
              {"symbol": "X", "as_of": bars[-2].date, "verdict": "NO FLAGS"}]
    rows = S.forward_returns(checks, {"X": bars}, (5,))
    assert rows[0]["ret_5"] == pytest.approx(-0.10)
    assert "ret_5" not in rows[1]
    assert "| CAUTION | 1 |" in S.scorecard(rows, (5,))


def test_monitor_never_references_an_order_tool():
    for mod in (M, S):
        src = open(mod.__file__).read()
        for name in ("place_equity_order", "cancel_equity_order", "review_equity_order"):
            assert name not in src


def test_partial_fill_counts_and_bad_average_cost_is_dropped():
    o = M.parse_orders({"orders": [{"symbol": "SPCX", "side": "buy", "state": "partially_filled_rest_cancelled",
                                    "cumulative_quantity": "14", "created_at": "2026-06-11T20:41:54Z",
                                    "last_transaction_at": "2026-06-12T07:15:12Z"}]})
    assert o[0]["state"] == "filled" and M.first_entry("SPCX", o) == "2026-06-12"
    p = M.parse_positions({"positions": [{"symbol": "INKT", "quantity": "0.03796", "average_buy_price": "0.000000"}]}, "123456789")
    assert p[0]["average_cost"] is None and p[0]["account"] == "123456789"
    assert M.mask("123456789") == "••6789"


def test_orders_from_several_calls_are_merged_by_id():
    a = {"orders": [{"id": "1", "symbol": "DJT", "side": "buy", "state": "filled", "created_at": "2025-01-17T00:00:00Z", "last_transaction_at": "2025-01-17T00:00:00Z"}]}
    b = {"orders": [{"id": "1", "symbol": "DJT", "side": "buy", "state": "filled", "created_at": "2025-01-17T00:00:00Z", "last_transaction_at": "2025-01-17T00:00:00Z"},
                    {"id": "2", "symbol": "HOOD", "side": "buy", "state": "filled", "created_at": "2026-10-14T00:00:00Z", "last_transaction_at": "2026-10-14T00:00:00Z"}]}
    assert [o["id"] for o in M.merge_orders([a, b])] == ["1", "2"]
