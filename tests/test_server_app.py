"""MCP server HTTP layer: token gate, health, config refusals, read-only
surface (specs/003, T019)."""

import pathlib
import re

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("mcp")

from starlette.testclient import TestClient  # noqa: E402

from server.app import build_app  # noqa: E402
from server.config import ConfigError, Settings  # noqa: E402
from tests.server_fixtures import make_ds  # noqa: E402

TOKEN = "t" * 40
H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


def _call(name, **arguments):
    return {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


@pytest.fixture()
def client():
    ds, _ = make_ds()
    app = build_app(Settings(token=TOKEN, host="0.0.0.0", provider="fixture",
                             allowed_hosts=("pd.example.com",)), ds)
    with TestClient(app, base_url="http://localhost:8765") as c:
        yield c


def test_health_is_open_and_says_nothing_else(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and set(r.json()) == {"status", "version"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN},
                                     {"Authorization": "Basic " + TOKEN}])
def test_requests_without_the_token_are_rejected(client, headers):
    assert client.post("/mcp", json=LIST, headers={**H, **headers}).status_code == 401


def test_wrong_path_token_is_rejected(client):
    assert client.post("/t/wrong/mcp", json=LIST, headers=H).status_code == 401


def test_bearer_and_path_token_both_reach_the_tools(client):
    a = client.post("/mcp", json=LIST, headers={**H, "Authorization": f"Bearer {TOKEN}"})
    b = client.post(f"/t/{TOKEN}/mcp", json=LIST, headers=H)
    for r in (a, b):
        assert r.status_code == 200
        names = {t["name"] for t in r.json()["result"]["tools"]}
        assert names == {"check_ticker", "was_i_pumped", "pump_scan", "monitor_digest", "data_status",
                         "is_pumping", "scan_latest"}
        assert all(t["annotations"]["readOnlyHint"] for t in r.json()["result"]["tools"])


def test_tool_call_returns_text_and_structured_verdict(client):
    r = client.post(f"/t/{TOKEN}/mcp", json=_call("check_ticker", symbol="RYDE", as_of="2024-09-06"), headers=H)
    res = r.json()["result"]
    assert "VETO" in res["content"][0]["text"]
    assert res["structuredContent"]["verdict"] == "VETO"


def test_refusal_is_an_error_result(client):
    r = client.post(f"/t/{TOKEN}/mcp", json=_call("check_ticker", symbol="RYDE", as_of="2099-01-01"), headers=H)
    assert r.json()["result"]["isError"] is True


def test_unknown_host_header_is_rejected(client):
    r = client.post("/mcp", json=LIST, headers={**H, "Authorization": f"Bearer {TOKEN}", "Host": "evil.example"})
    assert r.status_code in (400, 403, 421)


def test_tunnel_host_is_allowed(client):
    r = client.post("/mcp", json=LIST, headers={**H, "Authorization": f"Bearer {TOKEN}", "Host": "pd.example.com"})
    assert r.status_code == 200


def test_refuses_to_listen_publicly_without_a_token():
    with pytest.raises(ConfigError):
        Settings(host="0.0.0.0", provider="fixture").validate()
    with pytest.raises(ConfigError):
        Settings(host="0.0.0.0", token="short", provider="fixture").validate()
    Settings(host="127.0.0.1", provider="fixture").validate()          # loopback-only is allowed
    with pytest.raises(ConfigError):
        Settings(token=TOKEN, provider="tiingo").validate()           # no key


def test_server_code_never_names_an_order_or_write_tool():
    """SC-006: the server has no brokerage client and no write tool names."""
    banned = re.compile(r"place_\w*order|cancel_\w*order|review_\w*order|create_alert|create_watchlist|"
                        r"add_to_watchlist|update_watchlist|exercise_option|create_scan")
    root = pathlib.Path(__file__).resolve().parent.parent / "server"
    for f in root.glob("*.py"):
        assert not banned.search(f.read_text()), f
