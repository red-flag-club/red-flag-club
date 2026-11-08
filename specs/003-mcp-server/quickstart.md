# Quickstart: pd-defence MCP Server

Full runbook (cloudflared, runner, clients): `docs/mcp_server.md`.

## 1. Offline tests (no keys, no network)

```bash
./run.sh setup && ./run.sh test
python3 -m pytest -q tests -k server
```

Expected: all pass, including RYDE → VETO as of 2024-09-06 through
`check_ticker`, `was_i_pumped` truncation, auth rejection, and the
no-order-tool grep.

## 2. Local run against fixtures

```bash
./run.sh serve --fixture      # loopback only, no token needed
curl -s localhost:8765/healthz
```

Expected: `{"status":"ok",...}`. With no token set the server only listens on 127.0.0.1; set `PD_MCP_TOKEN` and every /mcp call without it returns 401.

## 3. Container on the laptop

```bash
cp .env.example .env      # fill PD_MCP_TOKEN, TIINGO_API_KEY, PD_SEC_CONTACT
docker compose up -d --build
curl -s localhost:8765/healthz
```

Expected: healthy within 30 s; `docker compose restart` keeps `data_status`
counts (volume persists).

## 4. Through the tunnel

Add an ingress rule in the existing cloudflared config:
`hostname: pd.<your-domain>` → `service: http://localhost:8765`, and set
`PD_ALLOWED_HOSTS=pd.<your-domain>`.

```bash
claude mcp add --transport http pd-defence https://pd.<your-domain>/mcp \
  --header "Authorization: Bearer $PD_MCP_TOKEN"
```

Expected: `check_ticker RYDE as_of 2024-09-06` → VETO.

## 5. Deploy

Register a self-hosted runner on the laptop with label `pd-defence`; add repo
secrets `PD_MCP_TOKEN`, `TIINGO_API_KEY`, `PD_SEC_CONTACT`, `PD_ALLOWED_HOSTS`.
Merge to `main` → `deploy.yml` tests, rebuilds, health-checks, rolls back on
failure.
