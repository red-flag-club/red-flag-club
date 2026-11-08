"""Spec 008: the public/private split and the human-gated pipeline.

Covers the leak gate and allowlist (scripts/public_export.py), spec-gate and
project-sync (public/dotgithub/.github/scripts/), and tasks → issues
(scripts/spec_issues.py). No network.
"""

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load("public_export", ROOT / "scripts" / "public_export.py")
G = _load("spec_gate", ROOT / "public" / "dotgithub" / ".github" / "scripts" / "spec_gate.py")
P = _load("project_sync", ROOT / "public" / "dotgithub" / ".github" / "scripts" / "project_sync.py")
I = _load("spec_issues", ROOT / "scripts" / "spec_issues.py")


# ---------------------------------------------------------------- allowlist

def test_private_material_is_never_in_the_code_allowlist():
    files = ["PLAN.md", "PROGRESS.md", "CLAUDE.md", "README.md", "LICENSE", ".mcp.json",
             "raw/x.txt", "data/events/events_seed.jsonl", "data/l14/filings.json", "results/paper/checks.jsonl",
             "research/check_ticker.py", "research/ride_signal.py", "research/FINDINGS.md", "reports/a.md",
             "research_notes/x/y.md", "docs/daily_monitor_routine.md", "community/stories/x.draft.json",
             "community/stories/approved/owner-x.json", "community/inbox/a.json",
             "tests/private/test_layer3_realdata.py", "tests/fixtures/l13/historicals_ryde_reto_xrpn.json",
             "scripts/leak_patterns.private", "scripts/publish_public.sh", "PUBLIC_REF", "worker/stories/wrangler.toml",
             ".github/workflows/deploy.yml", ".github/workflows/site.yml", "RECONCILE_AND_BUILD_PROMPT.md"]
    assert E.code_files(files) == []


def test_public_code_is_in_the_allowlist():
    files = ["src/layer1.py", "src/check_ticker.py", "server/app.py", "web/index.html", "worker/stories/index.js",
             "scripts/stories.py", "tests/test_layer3.py", "tests/fixtures/synthetic/historicals.json",
             "specs/007-community-stories/spec.md", "docs/workflow.md", "public/code/README.md"]
    assert E.code_files(files) == sorted(files)


def test_the_real_allowlist_has_no_private_file():
    public = E.code_files()
    assert public and not [p for p in public if p.startswith(("raw/", "data/", "research/", "results/", "reports/",
                                                               "research_notes/", "tests/private/", "tests/fixtures/l13/"))]
    assert "scripts/leak_patterns.private" not in public


# ---------------------------------------------------------------- the gate

@pytest.mark.parametrize("text,label", [
    ('{"begins_at": "2024-09-11T00:00:00Z"}', "brokerage payload"),
    ('"interpolated": true', "brokerage payload"),
    ('"account_number": "5QR12345"', "account number"),
    ("write to someone@gmail.com", "email address"),
    ("see raw/mcp-historicals-1.txt", "private path"),
])
def test_gate_catches_each_kind_of_leak(text, label):
    hits = E.scan_text("web/x.js", text)
    assert hits and label in hits[0]


@pytest.mark.parametrize("text", ["noreply@users.noreply.github.com", "you@example.com",
                                  "git@github.com:red-flag-club/x.git", "a normal sentence about RYDE"])
def test_gate_lets_ordinary_text_through(text):
    assert E.scan_text("web/x.js", text) == []


def test_owner_patterns_come_only_from_the_private_file(tmp_path, monkeypatch):
    f = tmp_path / "leak_patterns.private"
    f.write_text("# comment\nowner identity\t(?i)jane\\s+example\n")
    monkeypatch.setattr(E, "PRIVATE_PATTERNS", f)
    assert "owner identity" in E.scan_text("README.md", "by Jane Example")[0]
    monkeypatch.setattr(E, "PRIVATE_PATTERNS", tmp_path / "missing")
    assert E.scan_text("README.md", "by Jane Example") == []


def test_the_gate_source_does_not_contain_owner_specific_patterns():
    src = (ROOT / "scripts" / "public_export.py").read_text()
    private = ROOT / "scripts" / "leak_patterns.private"
    if private.exists():
        for line in private.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                assert line.split("\t", 1)[1] not in src


def test_every_public_readme_says_what_why_and_how():
    for repo in ("code", "stories", "site"):
        text = (ROOT / "public" / repo / "README.md").read_text().lower()
        for word in ("what", "why", "how"):
            assert f"**{word}" in text or f"## {word}" in text or f"{word}:" in text, (repo, word)
    profile = (ROOT / "public" / "dotgithub" / "profile" / "README.md").read_text()
    assert "**What:**" in profile and "**Why:**" in profile and "**How:**" in profile


# ---------------------------------------------------------------- spec-gate

TICKED = "## Hard rules\n- [x] a\n- [x] b\n"


def _labels(table):
    return lambda repo, n: set(table.get((repo, n), ()))


def test_code_pr_needs_its_issue_in_implement():
    body = "Closes #5\n\n" + TICKED
    assert G.decide(body, ["src/layer1.py"], _labels({("o/r", 5): {"phase:implement"}}), "o/r") == []
    problems = G.decide(body, ["src/layer1.py"], _labels({("o/r", 5): {"phase:plan"}}), "o/r")
    assert problems and "phase:implement" in problems[0] and "phase:plan" in problems[0]


def test_spec_pr_is_allowed_from_specify_on():
    body = "Refs #7\n" + TICKED
    files = ["specs/009-x/spec.md", "docs/workflow.md"]
    assert G.decide(body, files, _labels({("o/r", 7): {"phase:specify"}}), "o/r") == []
    assert G.decide(body, files, _labels({("o/r", 7): {"phase:inbox"}}), "o/r")


def test_no_linked_issue_is_refused():
    assert "link the approved issue" in G.decide(TICKED, ["web/app.js"], _labels({}), "o/r")[0]


def test_cross_repo_issue_links_are_read_from_that_repo():
    body = "Fixes red-flag-club/stories#3\n" + TICKED
    ok = _labels({("red-flag-club/stories", 3): {"phase:implement"}})
    assert G.decide(body, ["scripts/stories.py"], ok, "red-flag-club/red-flag-club") == []


def test_unticked_hard_rules_are_refused():
    body = "Closes #5\n## Hard rules\n- [x] a\n- [ ] b\n## Notes\n- [ ] not a rule\n"
    problems = G.decide(body, ["src/x.py"], _labels({("o/r", 5): {"phase:implement"}}), "o/r")
    assert problems == ["1 of 2 hard-rule boxes are unticked"]


def test_missing_checklist_is_refused():
    problems = G.decide("Closes #5", ["src/x.py"], _labels({("o/r", 5): {"phase:implement"}}), "o/r")
    assert "missing the '## Hard rules' checklist" in problems[0]


def test_the_pr_template_passes_its_own_gate_once_ticked():
    tpl = (ROOT / "public" / "dotgithub" / ".github" / "pull_request_template.md").read_text()
    ticked, total = G.hard_rule_boxes(tpl)
    assert total == 8 and ticked == 0
    filled = tpl.replace("- [ ]", "- [x]").replace("Closes #", "Closes #9")
    assert G.decide(filled, ["src/x.py"], _labels({("o/r", 9): {"phase:implement"}}), "o/r") == []


# ---------------------------------------------------------------- project-sync

def _item(phase, labels, n=1, repo="red-flag-club/red-flag-club"):
    return {"phase": {"name": phase} if phase else None,
            "content": {"number": n, "repository": {"nameWithOwner": repo},
                        "labels": {"nodes": [{"name": l} for l in labels]}}}


def test_sync_sets_the_board_phase_and_removes_the_old_one():
    assert P.plan([_item("Implement", ["phase:plan", "type:feature"])]) == \
        [("red-flag-club/red-flag-club", 1, ["phase:plan"], "phase:implement")]


def test_sync_leaves_items_in_step_alone_and_clears_finished_ones():
    assert P.plan([_item("Tasks", ["phase:tasks"])]) == []
    assert P.plan([_item("Done", ["phase:review"])]) == [("red-flag-club/red-flag-club", 1, ["phase:review"], None)]
    assert P.plan([_item("Won't do", [])]) == []
    assert P.plan([{"phase": {"name": "Plan"}, "content": {}}]) == []          # a draft card


def test_only_the_board_phases_become_labels():
    labels = {l["name"] for l in __import__("json").loads((ROOT / "public" / "dotgithub" / "labels.json").read_text())}
    assert {f"phase:{p}" for p in P.PHASES} <= labels


def test_seed_issues_say_what_why_how_and_use_known_labels():
    import json
    labels = {l["name"] for l in json.loads((ROOT / "public" / "dotgithub" / "labels.json").read_text())}
    issues = json.loads((ROOT / "public" / "seed_issues.json").read_text())
    assert issues
    for i in issues:
        assert i["what"] and i["why"] and i["how"], i["title"]
        assert set(i["labels"]) <= labels, i["title"]
        assert not any(l.startswith("phase:") for l in i["labels"])      # the script adds phase:inbox


# ---------------------------------------------------------------- tasks → issues

def test_tasks_md_lines_become_issue_titles():
    text = "## Phase 1\n- [ ] T001 [P] [US1] Move check_ticker into src/\n- [x] T002 Done already\nnot a task\n"
    tasks = I.parse_tasks(text)
    assert [(t["id"], t["done"]) for t in tasks] == [("T001", False), ("T002", True)]
    assert I.title(tasks[0]) == "T001: Move check_ticker into src/"


def test_stories_repo_build_has_the_site_data_and_readable_copies(tmp_path):
    E.build("stories", tmp_path)
    import json
    data = json.loads((tmp_path / "data" / "stories.json").read_text())
    assert data["count"] == len(list(tmp_path.glob("stories/*.md")))
    assert (tmp_path / "LICENSE").exists() and "CC BY-NC-ND" in (tmp_path / "LICENSE").read_text()
    assert E.scan_tree(tmp_path) == []
