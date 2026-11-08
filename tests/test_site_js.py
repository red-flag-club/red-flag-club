"""Runs the assistant's Node tests (web/assistant.test.mjs) when Node exists."""

import shutil
import subprocess

import pytest

pytest.importorskip("duckdb")

from server.site import WEB  # noqa: E402


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_web_node_suites():
    r = subprocess.run(["node", "--test", str(WEB / "assistant.test.mjs"), str(WEB / "stories.test.mjs")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
