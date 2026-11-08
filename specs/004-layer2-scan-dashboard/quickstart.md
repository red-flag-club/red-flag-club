# Quickstart: Layer 2 Scan Log and Dashboard

## 1. Offline

```bash
./run.sh test -- -k "scan or dashboard"
./run.sh serve --fixture          # in another shell:
./run.sh scan --fixture           # scans the fixture sessions, builds the page
open http://127.0.0.1:8765/dashboard/
```

Expected: the synthetic pump and RYDE appear as VETO hits; the validation table
shows N.

## 2. Verify the free market source (once)

```bash
MASSIVE_API_KEY=... ./run.sh scan --check-source
```

`ok: N symbols for <date>` → set `PD_SCAN_SOURCE=massive` in `.env`.
`403 / not on your plan` → use `PD_SCAN_SOURCE=payload` (see
`docs/mcp_server.md`).

## 3. In the container

Set `MASSIVE_API_KEY`, `PD_SCAN_SOURCE=massive`, `PD_SCHEDULE=on` in `.env`,
`docker compose up -d`. First run backfills ~14 months (about an hour at 5
calls/min, resumable). Then bookmark
`https://pd.<your-domain>/t/<PD_MCP_TOKEN>/dashboard/`.
