#!/usr/bin/env bash
# pd-defence runner for Linux. Read-only: nothing here places orders.
#
#   ./run.sh help                 list commands and options
#
# Market data is fetched by a Claude agent through a brokerage's read-only
# MCP tools; these commands work on the payload files it saves.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${PD_VENV:-$ROOT/.venv}"
PYTHON_BIN="${PD_PYTHON:-python3}"
USE_VENV=1
QUIET=0
PAYLOADS="${PD_PAYLOADS:-}"

die()  { echo "error: $*" >&2; exit 1; }
info() { [[ $QUIET -eq 1 ]] || echo "==> $*" >&2; }

usage() {
  cat <<'EOF'
Usage: ./run.sh [global options] <command> [command options]

Global options
  --python PATH        Python interpreter to use (default: python3, or $PD_PYTHON)
  --venv DIR           virtualenv location (default: ./.venv, or $PD_VENV)
  --no-venv            use the interpreter directly, no virtualenv
  --payloads DIR       directory of saved brokerage historicals payloads
                       (*.txt / *.json; default: $PD_PAYLOADS)
  -q, --quiet          less output
  -h, --help           this help

Setup and checks
  setup                check Python >= 3.11, create the virtualenv, install pytest
  test [all|defence|research] [-- PYTEST_ARGS]
                       run the test suites (default: all)
  ryde                 RYDE regression replay; must print BLOCK
  doctor               show interpreter, versions and data that is present

Layer 1 (defence path)
  l13-report           L1.3 event-set counts with N
  l14-run [--threshold N] [--k K] [--latch N] [--release R]
                       L1.4 walk-forward replay on data/l14 (about a minute)
  l14-tune             L1.5 one-knob sweep (about 17 minutes)

Research track (observe-only)
  bracket              +20%/-10% pump rule over the payloads   (needs --payloads)
  grid                 +$50 target grid, best/worst fill bounds (needs --payloads)
  candles --large F... candle-pattern scan by sector            (needs --payloads)

Agent (no orders)
  check SYMBOL --historicals FILE [--as-of DATE] [--position USD]
        [--account USD] [--transcript FILE...]
                       pre-trade report: VETO / CAUTION / NO FLAGS
  paper --as-of DATE [--strategy KEY]...
                       one end-of-day paper-trading run      (needs --payloads)
  monitor [--as-of DATE] [--positions F] [--orders F] [--transcript F...]
          [--watchlist F] [--account USD]
                       daily digest: holdings (Layer 3 + check) and watchlist
                                                            (needs --payloads)
  score [--horizons 5 20]
                       how past checks played out, by verdict (needs --payloads)

MCP server (specs/003-mcp-server; read-only, no brokerage connection)
  serve [--fixture]    run the server on 127.0.0.1:8765 (env: PD_MCP_TOKEN,
                       TIINGO_API_KEY, PD_SEC_CONTACT; --fixture = offline demo data)
  docker-up            docker compose up -d --build (reads .env)
  scan [--fixture] [--backfill N] [--check-source]
                       Layer 2: load missing sessions, log hits, label outcomes,
                       rebuild the dashboard (env: PD_SCAN_SOURCE, MASSIVE_API_KEY)
  dashboard [--fixture]
                       rebuild the dashboard page from the database
  site [--fixture] [--out DIR]
                       build the public community site (spec 006) into
                       PD_DATA_DIR/site; open DIR/index.html via `site-preview`
  site-preview [DIR]   serve the built site on http://127.0.0.1:8000

Community stories (spec 007; see docs/stories.md)
  stories keygen|pull|list|check|approve|reject|stage|export|purge [...]
                       decrypt, check, approve and export anonymised stories

Examples
  ./run.sh setup && ./run.sh test
  ./run.sh test research -- -k bracket -x
  ./run.sh l14-run --threshold 5
  ./run.sh --payloads ~/rh_payloads bracket
  ./run.sh check HOOD --historicals ~/rh_payloads/hood.json --position 100
  ./run.sh serve --fixture
EOF
}

# ---------------------------------------------------------------- helpers

py() {
  if [[ $USE_VENV -eq 1 && -x "$VENV/bin/python" ]]; then
    "$VENV/bin/python" "$@"
  else
    "$PYTHON_BIN" "$@"
  fi
}

check_python() {
  command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "$PYTHON_BIN not found; install Python 3.11+ (e.g. sudo apt install python3 python3-venv)"
  "$PYTHON_BIN" - <<'EOF' || die "Python 3.11 or newer is required"
import sys
sys.exit(0 if sys.version_info >= (3, 11) else 1)
EOF
}

payload_files() {
  [[ -n "$PAYLOADS" ]] || die "this command needs --payloads DIR (or PD_PAYLOADS)"
  [[ -d "$PAYLOADS" ]] || die "payload directory not found: $PAYLOADS"
  mapfile -t FILES < <(find "$PAYLOADS" -maxdepth 1 -type f \( -name '*.txt' -o -name '*.json' \) | sort)
  [[ ${#FILES[@]} -gt 0 ]] || die "no *.txt or *.json payloads in $PAYLOADS"
  info "${#FILES[@]} payload files from $PAYLOADS"
}

# ---------------------------------------------------------------- commands

cmd_setup() {
  check_python
  if [[ $USE_VENV -eq 1 ]]; then
    if [[ ! -x "$VENV/bin/python" ]]; then
      info "creating virtualenv at $VENV"
      "$PYTHON_BIN" -m venv "$VENV" || die "venv failed; on Debian/Ubuntu: sudo apt install python3-venv"
    fi
    info "installing pytest and the MCP server requirements"
    "$VENV/bin/python" -m pip install -q --upgrade pip pytest
    "$VENV/bin/python" -m pip install -q -r "$ROOT/server/requirements.txt"
  else
    py -c "import pytest" 2>/dev/null || die "pytest missing: $PYTHON_BIN -m pip install pytest"
  fi
  info "ready: $(py --version)"
}

cmd_test() {
  local which="all"
  if [[ $# -gt 0 && "$1" != "--" ]]; then which="$1"; shift; fi
  [[ "${1:-}" == "--" ]] && shift
  case "$which" in
    all)      (cd "$ROOT" && py -m pytest -q "$@") ;;
    defence)  (cd "$ROOT" && py -m pytest -q tests "$@") ;;
    research) (cd "$ROOT" && py -m pytest -q research "$@") ;;
    *) die "test: expected all, defence or research, got '$which'" ;;
  esac
}

cmd_doctor() {
  echo "interpreter : $(py -c 'import sys; print(sys.executable)')"
  echo "version     : $(py --version 2>&1)"
  echo "pytest      : $(py -c 'import pytest; print(pytest.__version__)' 2>/dev/null || echo missing)"
  echo "mcp/duckdb  : $(py -c 'import mcp, duckdb; print("ok, duckdb", duckdb.__version__)' 2>/dev/null || echo 'missing (server tests skip)')"
  echo "venv        : $([[ $USE_VENV -eq 1 && -x "$VENV/bin/python" ]] && echo "$VENV" || echo 'not used')"
  echo "payloads    : ${PAYLOADS:-unset}"
  for d in data/events data/l13 data/l14 results; do
    printf '%-12s: %s files\n' "$d" "$(find "$ROOT/$d" -type f 2>/dev/null | wc -l)"
  done
}

cmd_check() {
  [[ $# -ge 1 ]] || die "check: SYMBOL required"
  local sym="$1"; shift
  local asof; asof="$(date +%F)"
  local args=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --as-of) asof="$2"; shift 2 ;;
      *) args+=("$1"); shift ;;
    esac
  done
  (cd "$ROOT" && py src/check_ticker.py "$sym" --as-of "$asof" "${args[@]}")
}

cmd_serve() {
  if [[ "${1:-}" == "--fixture" ]]; then export PD_PROVIDER=fixture; fi
  py -c "import mcp, duckdb" 2>/dev/null || die "server requirements missing: ./run.sh setup (or pip install -r server/requirements.txt)"
  (cd "$ROOT" && py -m server.app)
}

cmd_monitor() {
  local asof; asof="$(date +%F)"
  local args=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --as-of) asof="$2"; shift 2 ;;
      *) args+=("$1"); shift ;;
    esac
  done
  (cd "$ROOT" && py scripts/monitor.py --as-of "$asof" --historicals "${FILES[@]}" "${args[@]}")
}

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --python)   PYTHON_BIN="$2"; shift 2 ;;
      --venv)     VENV="$2"; shift 2 ;;
      --no-venv)  USE_VENV=0; shift ;;
      --payloads) PAYLOADS="$2"; shift 2 ;;
      -q|--quiet) QUIET=1; shift ;;
      -h|--help|help) usage; exit 0 ;;
      -*) die "unknown option $1 (see ./run.sh help)" ;;
      *) break ;;
    esac
  done
  [[ $# -gt 0 ]] || { usage; exit 1; }
  local cmd="$1"; shift
  [[ "$cmd" == "setup" ]] || check_python
  case "$cmd" in
    setup)      cmd_setup ;;
    test)       cmd_test "$@" ;;
    doctor)     cmd_doctor ;;
    ryde)       (cd "$ROOT" && py src/layer1.py "$@") ;;
    l13-report) (cd "$ROOT" && py scripts/l13.py report "$@") ;;
    l14-run)    (cd "$ROOT" && py scripts/l14.py run "$@") ;;
    l14-tune)   (cd "$ROOT" && py scripts/l14.py tune "$@") ;;
    bracket)    payload_files; (cd "$ROOT" && py research/run_bracket.py "${FILES[@]}") ;;
    grid)       payload_files; (cd "$ROOT" && py research/run_grid.py "${FILES[@]}") ;;
    candles)    payload_files; (cd "$ROOT" && py research/run_candles.py "${FILES[@]}" "$@") ;;
    paper)      payload_files; (cd "$ROOT" && py research/paper_agent.py "$@" "${FILES[@]}") ;;
    check)      cmd_check "$@" ;;
    monitor)    payload_files; cmd_monitor "$@" ;;
    serve)      cmd_serve "$@" ;;
    scan)       (cd "$ROOT" && py -m server.jobs scan "$@") ;;
    dashboard)  (cd "$ROOT" && py -m server.jobs dashboard "$@") ;;
    site)       (cd "$ROOT" && py -m server.jobs site "$@") ;;
    stories)    (cd "$ROOT" && py scripts/stories.py "$@") ;;
    site-preview) (cd "${1:-$ROOT/data/server/site}" && py -m http.server 8000 --bind 127.0.0.1) ;;
    docker-up)  (cd "$ROOT" && [[ -f .env ]] || die "copy .env.example to .env and fill it in"; cd "$ROOT" && docker compose up -d --build) ;;
    score)      payload_files; (cd "$ROOT" && py scripts/score_checks.py --historicals "${FILES[@]}" "$@") ;;
    *) die "unknown command '$cmd' (see ./run.sh help)" ;;
  esac
}

main "$@"
