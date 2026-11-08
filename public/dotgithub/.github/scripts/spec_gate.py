"""spec-gate: a pull request may only change what its issue's phase allows.

Run by the reusable workflow .github/workflows/spec-gate.yml in every
Red Flag Club repo (docs/workflow.md in red-flag-club/red-flag-club).

Rules:
  1. The PR body links an issue: "Closes #12", "Fixes #12", "Refs #12" or
     "owner/repo#12" (any of these keywords, case-insensitive).
  2. If every changed file is under specs/ or docs/ (or is a Markdown file),
     the issue must be in phase specify, plan, tasks, implement or review.
     Otherwise it must be in implement or review. Issues labelled
     size:trivial are allowed in implement without a spec.
  3. Every box under the PR template's "## Hard rules" heading is ticked.

Labels are the source of truth because only people with triage access can set
them; the board sync (project_sync.py) writes them from the project's Phase.

Stdlib only. Needs GITHUB_TOKEN (read), GITHUB_EVENT_PATH, GITHUB_REPOSITORY.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
LINK = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\s*:?\s+"
                  r"(?:(?P<repo>[\w.-]+/[\w.-]+))?#(?P<num>\d+)")
DOC_PHASES = {"phase:specify", "phase:plan", "phase:tasks", "phase:implement", "phase:review"}
CODE_PHASES = {"phase:implement", "phase:review"}


def linked_issues(body: str, default_repo: str) -> list[tuple[str, int]]:
    return [(m.group("repo") or default_repo, int(m.group("num"))) for m in LINK.finditer(body or "")]


def is_doc(path: str) -> bool:
    return path.startswith(("specs/", "docs/", ".specify/")) or path.endswith(".md")


def hard_rule_boxes(body: str) -> tuple[int, int]:
    """(ticked, total) checkboxes under '## Hard rules'."""
    m = re.search(r"(?ims)^##\s*hard rules\s*$(.*?)(?=^##\s|\Z)", body or "")
    if not m:
        return 0, 0
    boxes = re.findall(r"^\s*[-*]\s*\[( |x|X)\]", m.group(1), re.M)
    return sum(b.lower() == "x" for b in boxes), len(boxes)


def decide(body: str, files: list[str], labels_of, repo: str) -> list[str]:
    """Problems with this PR (empty list = pass). labels_of(repo, n) -> set[str]."""
    problems = []
    issues = linked_issues(body, repo)
    if not issues:
        return ["link the approved issue in the PR body, e.g. 'Closes #12' (docs/workflow.md)"]
    docs_only = bool(files) and all(is_doc(f) for f in files)
    need = DOC_PHASES if docs_only else CODE_PHASES
    ok = False
    seen = []
    for r, n in issues:
        labels = labels_of(r, n)
        phase = sorted(l for l in labels if l.startswith("phase:")) or ["(no phase)"]
        seen.append(f"{r}#{n}: {', '.join(phase)}")
        if labels & need or ("size:trivial" in labels and "phase:implement" in labels):
            ok = True
    if not ok:
        kind = "a docs/spec change" if docs_only else "a code change"
        problems.append(f"{kind} needs its issue in {' or '.join(sorted(need))}; found {'; '.join(seen)}. "
                        f"A maintainer moves it on the board after review.")
    ticked, total = hard_rule_boxes(body)
    if total == 0:
        problems.append("the PR body is missing the '## Hard rules' checklist from the template")
    elif ticked < total:
        problems.append(f"{total - ticked} of {total} hard-rule boxes are unticked")
    return problems


def _get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                               "Accept": "application/vnd.github+json",
                                               "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> int:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    event = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
    pr = event["pull_request"]
    files, page = [], 1
    while True:
        batch = _get(f"{API}/repos/{repo}/pulls/{pr['number']}/files?per_page=100&page={page}", token)
        files += [f["filename"] for f in batch]
        if len(batch) < 100:
            break
        page += 1

    def labels_of(r: str, n: int) -> set[str]:
        try:
            return {l["name"] for l in _get(f"{API}/repos/{r}/issues/{n}", token).get("labels", [])}
        except Exception as e:                       # noqa: BLE001 - report, don't crash
            print(f"could not read {r}#{n}: {e}")
            return set()

    problems = decide(pr.get("body") or "", files, labels_of, repo)
    if problems:
        print("spec-gate: blocked")
        for p in problems:
            print(f"::error::{p}")
        return 1
    print(f"spec-gate: ok ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
