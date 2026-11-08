"""Turn a spec's tasks.md into sub-issues of its spec issue (docs/workflow.md, Tasks phase).

    python3 scripts/spec_issues.py specs/008-community-org --parent 12 [--repo red-flag-club/red-flag-club] [--dry-run]

Reads lines like `- [ ] T004 [P] [US1] Do the thing in src/x.py` and creates
one issue per open task (title `T004: Do the thing in src/x.py`, body with the
spec path and the task line), adds it as a sub-issue of --parent, and adds it
to the board. Tasks already created (an open or closed issue whose title starts
with `T004:` and mentions the spec) are skipped, so it's safe to re-run.

Uses the `gh` CLI, run by a maintainer. New issues start without a phase;
the parent's phase gates the PRs (a PR says `Closes #<task>` and `Refs #<parent>`).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TASK = re.compile(r"^\s*-\s*\[(?P<done>[ xX])\]\s*(?P<id>T\d{3,})\b\s*(?P<text>.+?)\s*$")


def parse_tasks(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = TASK.match(line)
        if m:
            out.append({"id": m["id"], "done": m["done"].lower() == "x", "text": m["text"].strip(), "line": line.strip()})
    return out


def title(task: dict) -> str:
    text = re.sub(r"^(\[[^\]]+\]\s*)+", "", task["text"])        # drop [P] [US1] markers
    return f"{task['id']}: {text}"[:120]


def gh(*args: str, dry: bool = False) -> str:
    if dry:
        print("+ gh " + " ".join(args))
        return ""
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("spec_dir", type=Path)
    ap.add_argument("--parent", type=int, required=True, help="the spec's issue number")
    ap.add_argument("--repo", default="red-flag-club/red-flag-club")
    ap.add_argument("--project", type=int, help="board number (gh project list --owner red-flag-club)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    tasks = [t for t in parse_tasks((a.spec_dir / "tasks.md").read_text()) if not t["done"]]
    existing = set()
    if not a.dry_run:
        rows = json.loads(gh("issue", "list", "--repo", a.repo, "--state", "all", "--limit", "500",
                             "--search", f"in:body {a.spec_dir.as_posix()}", "--json", "title"))
        existing = {r["title"].split(":")[0] for r in rows}
    owner = a.repo.split("/")[0]
    for t in tasks:
        if t["id"] in existing:
            print(f"skip {t['id']} (exists)")
            continue
        body = (f"Task from `{a.spec_dir.as_posix()}/tasks.md` (spec issue #{a.parent}).\n\n"
                f"```\n{t['line']}\n```\n\nA PR for this task says `Closes #<this issue>` and `Refs #{a.parent}`; "
                f"spec-gate checks #{a.parent} is in the Implement phase.")
        url = gh("issue", "create", "--repo", a.repo, "--title", title(t), "--body", body, dry=a.dry_run).strip()
        if a.dry_run:
            continue
        number = int(url.rsplit("/", 1)[1])
        node = json.loads(gh("api", f"repos/{a.repo}/issues/{number}"))["id"]
        gh("api", "-X", "POST", f"repos/{a.repo}/issues/{a.parent}/sub_issues", "-F", f"sub_issue_id={node}")
        if a.project:
            gh("project", "item-add", str(a.project), "--owner", owner, "--url", url)
        print(f"{t['id']} → {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
