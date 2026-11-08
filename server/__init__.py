"""pd-defence MCP server (specs/003-mcp-server).

Read-only. It has no brokerage connection, places no orders and stores no
account data. Verdicts come from the existing defence-path and check code,
which is imported, not copied.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Same import set-up as scripts/monitor.py: src/check_ticker.py imports
# `layer1` as a top-level module, so src/ goes on sys.path too.
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

__version__ = "0.1.0"
