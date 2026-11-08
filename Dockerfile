# pd-defence MCP server (specs/003-mcp-server). Read-only: no brokerage
# connection, no order tools.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PD_HOST=0.0.0.0 PD_PORT=8765 PD_DATA_DIR=/data

WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

# Code only, plus the synthetic fixtures PD_PROVIDER=fixture serves.
# No raw/, data/, results/, research/ or personal data (see .dockerignore).
COPY src/ src/
COPY scripts/ scripts/
COPY server/ server/
COPY web/ web/
COPY community/stories/approved/ community/stories/approved/
COPY tests/fixtures/synthetic/ tests/fixtures/synthetic/

RUN useradd --uid 10001 --no-create-home pd && mkdir -p /data && chown pd /data
USER pd
VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "server.app"]
