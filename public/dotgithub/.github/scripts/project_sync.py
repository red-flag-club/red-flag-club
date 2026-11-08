"""project-sync: copy each board item's Phase onto its issue as a phase:* label.

The organisation project "Red Flag Club: spec pipeline" is where maintainers
move work through the review gates (docs/workflow.md). GitHub Actions can't
read an organisation project with the default token, and a contributor's pull
request can't see secrets, so spec-gate reads labels instead; this job keeps
the labels equal to the board. Labels need triage access to set, so only the
board (moved by maintainers) decides a phase.

Env: PROJECT_TOKEN (a GitHub App installation token or a maintainer's
fine-grained token: organisation Projects read, repository Issues write),
ORG (default red-flag-club), PROJECT_NUMBER, DRY_RUN=1 to print only.
Stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
PHASES = {"inbox", "specify", "plan", "tasks", "implement", "review"}   # Done/Won't do/Blocked: no label

QUERY = """
query($org: String!, $number: Int!, $after: String) {
  organization(login: $org) {
    projectV2(number: $number) {
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          phase: fieldValueByName(name: "Phase") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
          content {
            ... on Issue { number repository { nameWithOwner } labels(first: 50) { nodes { name } } }
            ... on PullRequest { number repository { nameWithOwner } labels(first: 50) { nodes { name } } }
          }
        }
      }
    }
  }
}"""


def slug(phase_name: str | None) -> str | None:
    s = (phase_name or "").strip().lower().replace("'", "").replace(" ", "-")
    return s if s in PHASES else None


def plan(items: list[dict]) -> list[tuple[str, int, list[str], str | None]]:
    """(repo, number, labels to remove, label to add) for items out of sync."""
    out = []
    for it in items:
        c = it.get("content") or {}
        if "number" not in c:
            continue                                 # draft items have no issue
        have = {l["name"] for l in c["labels"]["nodes"] if l["name"].startswith("phase:")}
        p = slug((it.get("phase") or {}).get("name"))
        want = {f"phase:{p}"} if p else set()
        if have != want:
            out.append((c["repository"]["nameWithOwner"], c["number"], sorted(have - want),
                        next(iter(want - have), None)))
    return out


def _call(method: str, url: str, token: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def fetch(token: str, org: str, number: int) -> list[dict]:
    items, after = [], None
    while True:
        r = _call("POST", f"{API}/graphql", token,
                  {"query": QUERY, "variables": {"org": org, "number": number, "after": after}})
        if r.get("errors"):
            raise SystemExit(f"GraphQL error: {r['errors']}")
        page = r["data"]["organization"]["projectV2"]["items"]
        items += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return items
        after = page["pageInfo"]["endCursor"]


def main() -> int:
    token, org = os.environ["PROJECT_TOKEN"], os.environ.get("ORG", "red-flag-club")
    changes = plan(fetch(token, org, int(os.environ["PROJECT_NUMBER"])))
    for repo, n, remove, add in changes:
        print(f"{repo}#{n}: -{remove or '[]'} +{add or '-'}")
        if os.environ.get("DRY_RUN") == "1":
            continue
        for label in remove:
            _call("DELETE", f"{API}/repos/{repo}/issues/{n}/labels/{urllib.parse.quote(label)}", token)
        if add:
            _call("POST", f"{API}/repos/{repo}/issues/{n}/labels", token, {"labels": [add]})
    print(f"project-sync: {len(changes)} item(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
