"""MCP server tools on offline fixtures (specs/003, T011/T013/T015/T017).

RYDE bars are the real L1.3 seed event (data/events/events_seed.jsonl) and
its real SEC filing index (data/l14/filings.json). Everything else is
synthetic and says so.
"""

import datetime as dt

import pytest

pytest.importorskip("duckdb")

from server import tools as T  # noqa: E402
from server.data import last_session  # noqa: E402
from server.sec import seed_filings  # noqa: E402
from tests.server_fixtures import NOW, make_ds, series  # noqa: E402

TODAY = last_session(NOW)


def _pump(start="2025-06-02", n=290):
    """Flat for n-10 sessions, then +8%/session for 10 (+116%): a pump profile."""
    return series([10.0] * (n - 10) + [10 * 1.08 ** k for k in range(1, 11)], start)


def _ending_today(closes):
    """Synthetic series whose last bar is the last session."""
    rows = series(closes, "2024-01-01")
    out, d = [], dt.date.fromisoformat(TODAY)
    for r in reversed(rows):
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
        out.append({**r, "date": d.isoformat()})
        d -= dt.timedelta(days=1)
    return list(reversed(out))


# ------------------------------------------------------------------ US1

def test_ryde_is_vetoed_on_its_reference_date():
    ds, _ = make_ds()
    r = T.check_ticker(ds, "RYDE", "2024-09-06")
    assert r["verdict"] == "VETO"
    assert any("pump profile" in v for v in r["vetoes"])
    assert r["data"]["last_date"] == "2024-09-06" and r["data"]["sec"] == "ok"
    assert "6-K" in str(r["summary"]["structural_score"]) or r["summary"]["last_sec_filing"] <= "2024-09-06"


def test_large_domestic_filer_with_current_fundamentals_is_not_a_structural_veto():
    """DJT-like (synthetic): ~130M float, $9B cap, ten 8-Ks in seven weeks,
    no run-up. Must not VETO on structure (CLAUDE.md reference case)."""
    closes = [30 + 0.02 * i for i in range(300)]
    filed = [(dt.date.fromisoformat(TODAY) - dt.timedelta(days=5 * k)).isoformat() for k in range(10)]
    ds, _ = make_ds({"DJTX": _ending_today(closes)},
                    {"DJTX": [{"form": "8-K", "filed": d} for d in filed]})
    r = T.check_ticker(ds, "DJTX", fundamentals={"float": "130000000", "market_cap": "9000000000",
                                                  "pe_ratio": "-50"})
    assert r["data"]["fundamentals"] == "caller-supplied, current"
    assert not any("structural" in v for v in r["vetoes"])
    assert not any("could reach the veto" in c for c in r["cautions"])


def test_fundamentals_are_ignored_for_a_past_date():
    ds, _ = make_ds()
    r = T.check_ticker(ds, "RYDE", "2024-09-06", fundamentals={"float": "110000000", "market_cap": "9e9"})
    assert r["data"]["fundamentals"].startswith("ignored")
    assert "float" in r["summary"]["structural_unknown"]


def test_unknown_symbol_is_no_data_not_no_flags():
    ds, _ = make_ds()
    r = T.check_ticker(ds, "ZZZZ", "2026-10-01")
    assert r["verdict"] == "NO DATA"


def test_answers_are_compact_and_never_recommend_buying():
    ds, _ = make_ds({"FLAT": series([20.0 + 0.01 * i for i in range(300)], "2025-06-02")})
    for sym, day in (("RYDE", "2024-09-06"), ("FLAT", "2026-07-01")):
        text = T.check_ticker(ds, sym, day)["text"]
        assert len(text) < 2500                                         # SC-002
        cleaned = text.lower().replace("not a buy signal", "").replace("before buying", "")
        assert "buy" not in cleaned and "target" not in cleaned


def test_invalid_symbol_and_future_date_are_refused():
    ds, _ = make_ds()
    with pytest.raises(T.ToolError):
        T.check_ticker(ds, "../etc", "2026-10-01")
    with pytest.raises(T.ToolError):
        T.check_ticker(ds, "RYDE", "2027-01-01")


def test_verdicts_are_logged_without_personal_data():
    ds, _ = make_ds()
    T.check_ticker(ds, "RYDE", "2024-09-06")
    assert ds.store._q("SELECT tool, symbol, verdict FROM checks") == [("check_ticker", "RYDE", "VETO")]


# ------------------------------------------------------------------ US2

def test_was_i_pumped_ryde_and_hindsight_is_separate():
    ds, _ = make_ds()
    r = T.was_i_pumped(ds, "RYDE", "2024-09-09")
    assert r["at_the_time"]["verdict"] == "VETO"
    assert r["hindsight"]["ret_20"] < -0.5 and r["hindsight"]["max_drawdown_from_buy"] < -0.9
    assert "HINDSIGHT (not used for the verdict)" in r["text"]


@pytest.mark.parametrize("sym,day,rows", [
    ("RYDE", "2024-09-09", None),
    ("SYN", "2025-07-01", {"SYN": _pump("2024-08-01", 400)}),
])
def test_was_i_pumped_verdict_is_identical_without_later_data(sym, day, rows):
    """SC-005 truncation test: removing every bar after the buy date cannot
    change what the server said about that date."""
    full, _ = make_ds(rows)
    truncated_rows = {s: [r for r in v if r["date"] <= day] for s, v in (full.provider.rows.items())}
    cut, _ = make_ds(truncated_rows, seed=False, filings=seed_filings())
    a = T.was_i_pumped(full, sym, day)["at_the_time"]
    b = T.was_i_pumped(cut, sym, day)["at_the_time"]
    assert a == b


def test_horizons_not_yet_elapsed_say_not_yet():
    rows = _ending_today([10.0] * 300)
    ds, _ = make_ds({"NEW": rows})
    r = T.was_i_pumped(ds, "NEW", rows[-3]["date"])
    assert r["hindsight"]["ret_5"] == "not yet" and r["hindsight"]["sessions_since"] == 2


def test_buy_date_before_any_data_is_refused():
    ds, _ = make_ds()
    with pytest.raises(T.ToolError):
        T.was_i_pumped(ds, "RYDE", "2020-01-02")


# ------------------------------------------------------------------ US3

def test_pump_scan_puts_vetoes_first_and_lists_missing_symbols():
    ds, _ = make_ds({"PUMP": _pump(), "CALM": series([20.0] * 290, "2025-06-02")})
    r = T.pump_scan(ds, ["calm", "ZZZZ", "PUMP"], as_of=_pump()[-1]["date"])
    assert [x["symbol"] for x in r["rows"]][0] == "PUMP" and r["rows"][0]["verdict"] == "VETO"
    assert r["rows"][0]["run_up_10"] > 1.0
    assert {"symbol": "ZZZZ", "verdict": "NO DATA", "reason": "no bars"} in r["rows"]


def test_pump_scan_refuses_more_than_fifty_symbols():
    ds, _ = make_ds()
    with pytest.raises(T.ToolError):
        T.pump_scan(ds, [f"S{i}" for i in range(51)])


# ------------------------------------------------------------------ US4

def test_monitor_digest_alerts_and_discards_account_numbers(tmp_path):
    rows = _ending_today([100.0] * 260 + [80.0] * 10)
    ds, _ = make_ds({"HOLD": rows}, path=tmp_path / "pd.duckdb")
    r = T.monitor_digest(ds, [{"symbol": "HOLD", "quantity": "2", "average_buy_price": "100",
                               "account_number": "987654321"}])
    alerts = r["holdings"][0]["alerts"]
    assert any(a.startswith("EXIT RULE") for a in alerts) and any(a.startswith("LOSS") for a in alerts)
    assert "no orders were placed" in r["note"].lower()
    assert "987654321" not in str(r) and "6789" not in str(r)
    ds.store.close()
    assert b"987654321" not in (tmp_path / "pd.duckdb").read_bytes()
    assert b"HOLD" in (tmp_path / "pd.duckdb").read_bytes()          # market data is cached, positions are not


def test_monitor_digest_does_not_log_holdings_as_checks():
    rows = _ending_today([100.0] * 270)
    ds, _ = make_ds({"HOLD": rows})
    T.monitor_digest(ds, [{"symbol": "HOLD", "quantity": 1, "average_cost": 90}])
    assert ds.store._q("SELECT count(*) FROM checks")[0][0] == 0


def test_monitor_time_stop_uses_passed_orders():
    rows = _ending_today([10.0] * 280 + [10 * 1.08 ** k for k in range(1, 11)])
    entry = rows[-6]["date"]
    ds, _ = make_ds({"PMP": rows})
    r = T.monitor_digest(ds, [{"symbol": "PMP", "quantity": 1, "average_cost": 15}],
                         orders=[{"id": "1", "symbol": "PMP", "side": "buy", "state": "filled",
                                  "created_at": entry + "T15:00:00Z", "last_transaction_at": entry + "T15:00:01Z"}])
    assert any(a.startswith("TIME STOP") for a in r["holdings"][0]["alerts"])


# ------------------------------------------------------------------ all

def test_data_status_reports_usage():
    ds, _ = make_ds()
    T.check_ticker(ds, "RYDE", "2024-09-06")
    s = T.data_status(ds)
    # a 2024 question is answered from memory and not stored (spec 005)
    assert s["provider"] == "fixture" and s["symbols_cached"] == 0 and s["calls_last_hour"] >= 1
    assert "retention:" in s["text"] and "not stored" in s["text"]
