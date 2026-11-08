"""Build and check what Red Flag Club publishes (spec 008).

    python3 scripts/public_export.py check               # leak gate on the public file set
    python3 scripts/public_export.py build --out DIR     # write the public code repo tree
    python3 scripts/public_export.py build --repo stories --out DIR
    python3 scripts/public_export.py list                # files that would be published

Four public repos are built from this private one:

    code       red-flag-club/red-flag-club             allowlisted code + public/code overlay
    site       red-flag-club/red-flag-club.github.io   public/site overlay (the bot adds the built site)
    stories    red-flag-club/stories                   public/stories overlay + approved stories
    dotgithub  red-flag-club/.github                   org-wide issue forms, PR template, spec-gate, board sync

It works by **allowlist**: a tracked file is public only if a rule below names
it. Files that need a different public version (README, CLAUDE.md, LICENSE,
.github/) live under public/<repo>/ and are copied over the top. The gate then
scans every output file for things that must never be public: brokerage
payloads, the owner's identity, loss, position, account numbers, emails. It
runs here before every export and in the public repo's CI on every pull
request (public/code/.github/workflows/ci.yml runs `check --tree .`).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 1_000_000

# ------------------------------------------------------------------ allowlist
CODE_INCLUDE = [
    "src/*.py",
    "server/*",
    "web/*",
    "worker/stories/*",
    "scripts/stories.py", "scripts/monitor.py", "scripts/score_checks.py", "scripts/l13.py",
    "scripts/l14.py", "scripts/make_synthetic.py", "scripts/public_export.py", "scripts/org_setup.sh",
    "scripts/spec_issues.py",
    "tests/*.py", "tests/fixtures/synthetic/*",
    "specs/*", ".specify/*", ".claude/skills/*",
    "docs/mcp_server.md", "docs/site.md", "docs/stories.md", "docs/workflow.md", "docs/methodology.md",
    "Dockerfile", "docker-compose.yml", ".dockerignore", ".env.example", "run.sh", "conftest.py", ".gitignore",
    "public/*",               # the overlays themselves, so contributors can see what each repo gets
]
CODE_EXCLUDE = [
    "worker/stories/wrangler.toml",
    "tests/private/*",
    "tests/fixtures/l13/*",
    "tests/test_*_realdata.py",
]
OVERLAY = {"code": "public/code", "site": "public/site", "stories": "public/stories", "dotgithub": "public/dotgithub"}

# ------------------------------------------------------------------ the gate
# (label, regex). Every hit fails the check unless the file is listed in
# GATE_ALLOW for that label. Owner-specific patterns (name, username, exact
# loss, position, cost basis) are NOT here: they are read from
# scripts/leak_patterns.private, which exists only in the private repo,
# because writing them in a public file would publish them.
FORBIDDEN = [
    ("email address", re.compile(r"[\w.+-]+@(?!(?:users\.)?noreply\.github\.com|example\.(?:com|org)|anthropic\.com"
                                 r"|github\.com)[\w-]+\.[\w.-]+")),
    ("brokerage payload", re.compile(r'"begins_at"\s*:|"interpolated"\s*:\s*true|"instrument_id"\s*:')),
    ("account number", re.compile(r'"account_number"\s*:\s*"[0-9A-Z]{4,}"')),
    ("private path", re.compile(r"\b(?:raw|research_notes|reports)/[\w.-]+\.(?:txt|json|md)\b|data/events/events_b\d")),
]
PRIVATE_PATTERNS = ROOT / "scripts" / "leak_patterns.private"


def private_patterns() -> list[tuple[str, re.Pattern]]:
    """`label<TAB>regex` lines; blank lines and # comments ignored."""
    if not PRIVATE_PATTERNS.exists():
        return []
    out = []
    for line in PRIVATE_PATTERNS.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            label, rx = line.split("\t", 1)
            out.append((label, re.compile(rx)))
    return out


GATE_ALLOW = {
    # The synthetic fixtures imitate the payload shape on purpose; the
    # parsers and their tests must name the keys they read.
    "brokerage payload": ["tests/fixtures/synthetic/*", "scripts/make_synthetic.py", "src/*.py", "scripts/l13.py",
                          "scripts/l14.py", "tests/*.py"],
    # The gate's own tests plant one example of each leak on purpose.
    "email address": ["tests/test_governance.py"],
    # test_server_tools proves account numbers passed in are discarded; the values are made up.
    "account number": ["tests/test_server_tools.py", "tests/test_governance.py"],
    "private path": ["specs/001-l13-event-sets/*", "specs/002-l14-walk-forward/*", "scripts/l13.py",
                     "scripts/l14.py", "tests/test_governance.py"],
}


def real_data_fingerprints() -> set[str]:
    """Exact volumes from the private brokerage fixtures (private repo only).
    A public file containing several of them is carrying real market data.
    Round thousands are skipped: they turn up by coincidence."""
    nums: set[str] = set()
    p = ROOT / "tests" / "fixtures" / "l13" / "historicals_ryde_reto_xrpn.json"
    if p.exists():
        for r in json.loads(p.read_text())["data"]["results"]:
            nums |= {str(int(b["volume"])) for b in r["bars"] if int(b["volume"] or 0) >= 10_000}
    p = ROOT / "data" / "events" / "events_seed.jsonl"
    if p.exists():
        for line in p.read_text().splitlines():
            nums |= {str(int(b[5])) for b in json.loads(line)["bars"] if b[5] >= 10_000}
    return {n for n in nums if int(n) % 1000}


FINGERPRINT = re.compile(r"\b\d{5,9}\b")


def _match(path: str, patterns) -> bool:
    return any(fnmatch.fnmatch(path, p) or (p.endswith("/*") and path.startswith(p[:-1])) for p in patterns)


def tracked() -> list[str]:
    """Files git tracks; in a tree that isn't a git checkout (a CI build), every file."""
    r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode == 0:
        return [p for p in r.stdout.splitlines() if (ROOT / p).is_file()]
    return sorted(f.relative_to(ROOT).as_posix() for f in ROOT.rglob("*")
                  if f.is_file() and ".git" not in f.relative_to(ROOT).parts and "__pycache__" not in f.parts)


def code_files(files=None) -> list[str]:
    files = tracked() if files is None else files
    return sorted(p for p in files if _match(p, CODE_INCLUDE) and not _match(p, CODE_EXCLUDE))


def scan_text(path: str, text: str) -> list[str]:
    hits = []
    for label, rx in FORBIDDEN + private_patterns():
        if _match(path, GATE_ALLOW.get(label, [])):
            continue
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{path}:{line}: {label}: {m.group(0)[:50]!r}")
    return hits


def scan_tree(tree: Path) -> list[str]:
    problems = []
    real = real_data_fingerprints()
    for f in sorted(p for p in tree.rglob("*") if p.is_file() and ".git" not in p.relative_to(tree).parts):
        rel = f.relative_to(tree).as_posix()
        if f.stat().st_size > MAX_BYTES:
            problems.append(f"{rel}: larger than {MAX_BYTES} bytes")
            continue
        try:
            text = f.read_text()
        except UnicodeDecodeError:
            continue                       # images; size-checked above
        problems += scan_text(rel, text)
        found = set(FINGERPRINT.findall(text)) & real
        if found:
            problems.append(f"{rel}: real market data ({len(found)} exact volumes from the brokerage fixtures, "
                            f"e.g. {sorted(found)[0]})")
    return problems


# ------------------------------------------------------------------ build
def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def build(repo: str, out: Path) -> list[str]:
    if out.exists() and any(p.name != ".git" for p in out.iterdir()):
        for p in out.iterdir():
            if p.name != ".git":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    out.mkdir(parents=True, exist_ok=True)
    written = []
    if repo == "code":
        for rel in code_files():
            _copy(ROOT / rel, out / rel)
            written.append(rel)
    if repo == "stories":
        sys.path.insert(0, str(ROOT))
        from scripts import stories as S
        data = S.export()
        (out / "data").mkdir(parents=True, exist_ok=True)
        (out / "data" / "stories.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        n = data["count"]
        for f in sorted((ROOT / "community" / "stories" / "approved").glob("*.json")):
            d = json.loads(f.read_text())
            md = out / "stories" / f"{d['id']}.md"
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_text(story_markdown(d))
            written.append(md.relative_to(out).as_posix())
        written.append(f"data/stories.json ({n} stories)")
    overlay = ROOT / OVERLAY[repo]
    for f in sorted(p for p in overlay.rglob("*") if p.is_file()):
        rel = f.relative_to(overlay).as_posix()
        _copy(f, out / rel)
        written.append(rel)
    return written


def story_markdown(d: dict) -> str:
    tags = ", ".join(d.get("tactics", []))
    return (f"# {d['title']}\n\n"
            f"*{', '.join(d.get('stocks', []))} · {d.get('month_from')} to {d.get('month_to')} · "
            f"via {d.get('channel')} · loss {d.get('loss_range')} · tactics: {tags}*\n\n"
            f"> {d.get('summary', '')}\n\n{d['body']}\n\n---\n"
            f"Shared with Red Flag Club and anonymised; published with the author's consent under "
            f"CC BY-NC-ND 4.0. Corrections or takedown: open an issue with the story id `{d['id']}`.\n")


# ------------------------------------------------------------------ cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="build every public repo into a temp dir and run the gate")
    c.add_argument("--tree", type=Path, help="gate an existing tree instead (used by the public CI)")
    b = sub.add_parser("build")
    b.add_argument("--repo", choices=sorted(OVERLAY), default="code")
    b.add_argument("--out", type=Path, required=True)
    sub.add_parser("list")
    a = ap.parse_args(argv)

    if a.cmd == "list":
        print("\n".join(code_files()))
        return 0
    if a.cmd == "build":
        written = build(a.repo, a.out)
        problems = scan_tree(a.out)
        print(f"{a.repo}: {len(written)} files → {a.out}")
        if problems:
            print("\n".join(problems))
            print(f"LEAK GATE FAILED: {len(problems)} problem(s); do not publish {a.out}")
            return 1
        print("leak gate: clean")
        return 0
    if a.tree:
        problems = scan_tree(a.tree)
    else:
        import tempfile
        problems = []
        with tempfile.TemporaryDirectory() as tmp:
            for repo in sorted(OVERLAY):
                d = Path(tmp) / repo
                build(repo, d)
                problems += [f"[{repo}] {p}" for p in scan_tree(d)]
    if problems:
        print("\n".join(problems))
        print(f"LEAK GATE FAILED: {len(problems)} problem(s)")
        return 1
    print("leak gate: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
