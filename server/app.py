"""MCP binding: tools over streamable HTTP, a shared-secret gate, /healthz.

    PD_MCP_TOKEN=... TIINGO_API_KEY=... PD_SEC_CONTACT=you@example.com \
        python3 -m server.app

Auth (research R6): `Authorization: Bearer <token>`, or the URL prefix
`/t/<token>/mcp` for clients that only take a URL. Logs carry tool name,
symbol count, duration and outcome — never positions, orders or tokens.
"""

from __future__ import annotations

import hmac
import json
import logging
import time
from pathlib import Path
from typing import Any

import server
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError as MCPToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from server import tools as T
from server.config import Settings
from server.dashboard import PAGE_NAME, write_page
from server.data import DataService, DataUnavailable
from server.providers import from_settings
from server.sec import EdgarClient
from server.store import Store

log = logging.getLogger("pd-defence")
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True,
                            open_world_hint=True)
INSTRUCTIONS = (
    "pd-defence: read-only pre-trade checks against pump-and-dump exposure in small caps. "
    "Verdicts are VETO / CAUTION / NO FLAGS and are never buy signals. This server has no "
    "brokerage connection and cannot place orders. Use check_ticker before buying a small cap, "
    "was_i_pumped for a past purchase, pump_scan for a list, monitor_digest with positions you "
    "already hold (from the brokerage tools), is_pumping / scan_latest for the market-wide Layer 2 "
    "scan, data_status for cache and quota.")


def _result(out: dict) -> CallToolResult:
    text = out.pop("text")
    return CallToolResult(content=[TextContent(type="text", text=text)],
                          structured_content=json.loads(json.dumps(out, default=str)))


def _call(name: str, n_symbols: int, fn, *args, **kwargs) -> CallToolResult:
    t0 = time.monotonic()
    outcome = "ok"
    try:
        return _result(fn(*args, **kwargs))
    except T.ToolError as e:
        outcome = "refused"
        raise MCPToolError(str(e)) from e
    except DataUnavailable as e:
        outcome = "unavailable"
        raise MCPToolError(f"data unavailable, try later: {e}") from e
    finally:
        log.info("tool=%s symbols=%d outcome=%s ms=%d", name, n_symbols, outcome,
                 (time.monotonic() - t0) * 1000)


def build_mcp(ds: DataService, page_dir: Path | None = None, refresh_job=None) -> MCPServer:
    mcp = MCPServer(name="pd-defence", instructions=INSTRUCTIONS, version=server.__version__)

    @mcp.tool(annotations=READ_ONLY)
    def check_ticker(symbol: str, as_of: str | None = None, position_usd: float = 250.0,
                     account_usd: float = 1000.0, fundamentals: dict[str, Any] | None = None,
                     earnings: list[dict[str, Any]] | None = None, detail: bool = False) -> CallToolResult:
        """Pre-trade check: VETO / CAUTION / NO FLAGS with reasons, using only data dated on or
        before as_of (default: last completed session). fundamentals (float, market_cap, pe_ratio)
        are used only when as_of is the current session. Not a buy signal."""
        return _call("check_ticker", 1, T.check_ticker, ds, symbol, as_of, position_usd, account_usd,
                     fundamentals, earnings, detail)

    @mcp.tool(annotations=READ_ONLY)
    def was_i_pumped(symbol: str, buy_date: str) -> CallToolResult:
        """Did this stock match the pump-and-dump profile on the day it was bought (using only data
        known then), and what happened after (labelled hindsight)."""
        return _call("was_i_pumped", 1, T.was_i_pumped, ds, symbol, buy_date)

    @mcp.tool(annotations=READ_ONLY)
    def pump_scan(symbols: list[str], as_of: str | None = None) -> CallToolResult:
        """Check up to 50 symbols; VETO first, then by 10-session run-up."""
        return _call("pump_scan", len(symbols or []), T.pump_scan, ds, symbols, as_of)

    @mcp.tool(annotations=READ_ONLY)
    def monitor_digest(positions: list[dict[str, Any]], orders: list[dict[str, Any]] | None = None,
                       as_of: str | None = None) -> CallToolResult:
        """Daily rules on positions you pass in ({symbol, quantity, average_cost}; other fields such
        as account numbers are discarded): EXIT RULE, TIME STOP, EARNINGS, ABANDONED, LOSS, VETO.
        Pass get_equity_orders rows as orders for the time stop and abandoned checks. Nothing in
        the request is stored."""
        return _call("monitor_digest", len(positions or []), T.monitor_digest, ds, positions, orders, as_of)

    @mcp.tool(annotations=READ_ONLY)
    def is_pumping(symbol: str) -> CallToolResult:
        """Is this symbol on the Layer 2 scan (today, how many of the last 20 sessions, first and
        last seen), plus its current Layer 1 check. PLAN.md L2.3."""
        return _call("is_pumping", 1, T.is_pumping, ds, symbol)

    @mcp.tool(annotations=READ_ONLY)
    def scan_latest(session: str | None = None, limit: int = 25) -> CallToolResult:
        """Hits from the latest (or a given) scanned session: small caps up >= 50% over 5 or 21
        sessions, VETO first, with the forward check of Layer 1 against outcomes."""
        return _call("scan_latest", 0, T.scan_latest, ds, session, limit)

    @mcp.tool(annotations=READ_ONLY)
    def data_status() -> CallToolResult:
        """Data provider, free-tier usage and cache size."""
        return _call("data_status", 0, T.data_status, ds)

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "version": server.__version__})

    @mcp.custom_route("/dashboard/", methods=["GET"])
    async def dashboard(request: Request) -> Response:
        p = (page_dir or Path(".")) / PAGE_NAME
        if page_dir is None or not p.exists():
            return PlainTextResponse("dashboard not built yet: the scan has not run", status_code=503)
        return HTMLResponse(p.read_text(), headers={"Cache-Control": "no-store",
                                                    "X-Robots-Tag": "noindex, nofollow",
                                                    "Referrer-Policy": "no-referrer"})

    @mcp.custom_route("/jobs/refresh", methods=["POST"])
    async def jobs_refresh(request: Request) -> JSONResponse:
        """Run the Layer 2 refresh now (the CLI uses this while the server
        holds the database). Token-gated like everything but /healthz."""
        if refresh_job is None:
            return JSONResponse({"status": "scan source is off (PD_SCAN_SOURCE)"}, status_code=409)
        import anyio
        return JSONResponse(await anyio.to_thread.run_sync(refresh_job))

    return mcp


class TokenGate:
    """ASGI middleware: every path but /healthz needs the token. With no
    token configured (loopback only, enforced by Settings.validate) it is a
    pass-through."""

    OPEN = ("/healthz",)

    def __init__(self, app, token: str | None):
        self.app, self.token = app, token

    def _ok(self, presented: str | None) -> bool:
        return bool(presented) and hmac.compare_digest(presented.encode(), self.token.encode())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.token or scope["path"] in self.OPEN:
            return await self.app(scope, receive, send)
        path = scope["path"]
        if path.startswith("/t/"):
            _, _, rest = path.partition("/t/")
            presented, _, tail = rest.partition("/")
            if self._ok(presented):
                scope = {**scope, "path": "/" + tail, "raw_path": ("/" + tail).encode()}
                return await self.app(scope, receive, send)
        else:
            auth = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
            if auth[:7].lower() == "bearer " and self._ok(auth[7:].strip()):
                return await self.app(scope, receive, send)
        await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)


def refresh_job(settings: Settings, ds: DataService):
    src = market_source(settings)
    if src is None:
        return None
    from server.scan import refresh
    return lambda: refresh(ds.store, ds, src, on_done=lambda: after_refresh(settings, ds))


def after_refresh(settings: Settings, ds: DataService) -> None:
    """Rebuild the private dashboard and the public site's files (spec 006).
    Publishing the site is a separate, opt-in workflow."""
    write_page(ds.store, settings.data_dir)
    from server.site import build_site
    build_site(ds.store, ds, settings.site_dir, **site_options(settings))


def site_options(settings: Settings) -> dict:
    return {"prices": settings.site_prices, "discussions_url": settings.site_discussions,
            "site_url": settings.site_url, "stories_submit_url": settings.stories_submit_url,
            "turnstile_sitekey": settings.turnstile_sitekey}


def build_app(settings: Settings, ds: DataService, job=None):
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*", "127.0.0.1", "localhost"]
    origins = ["http://127.0.0.1:*", "http://localhost:*"]
    for h in settings.allowed_hosts:
        hosts += [h, f"{h}:*"]
        origins += [f"https://{h}"]
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                                    allowed_origins=origins)
    app = build_mcp(ds, settings.data_dir, job).streamable_http_app(stateless_http=True, json_response=True,
                                            transport_security=sec, host=settings.host)
    return TokenGate(app, settings.token)


def market_source(settings: Settings):
    from server import market
    return market.from_settings(settings)


def data_service(settings: Settings) -> DataService:
    store = Store(settings.db_path)
    sec = EdgarClient(settings.sec_contact) if settings.sec_contact else None
    if settings.provider == "fixture":
        from server.sec import FixtureSec, seed_filings
        sec = FixtureSec(seed_filings())
    return DataService(store, from_settings(settings), sec, today_ttl_min=settings.today_ttl_min)


def main() -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env().validate()
    ds = data_service(settings)
    job = refresh_job(settings, ds)
    app = build_app(settings, ds, job)
    write_page(ds.store, settings.data_dir)             # a page exists from the first request
    if settings.schedule and job is not None:
        from server.schedule import start_thread
        start_thread(job, settings.scan_times)
    log.info("pd-defence %s: provider=%s scan=%s schedule=%s host=%s port=%d auth=%s", server.__version__,
             settings.provider, settings.scan_source, settings.scan_times if settings.schedule else "off",
             settings.host, settings.port, "token" if settings.token else "loopback-only")
    # access_log off: uvicorn's access log would print /t/<token>/ paths.
    uvicorn.run(app, host=settings.host, port=settings.port, access_log=False, proxy_headers=True)


if __name__ == "__main__":
    main()
