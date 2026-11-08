"""Community stories — owner tooling (specs/007-community-stories).

Flow:  browser → Cloudflare Worker → encrypted file in the private inbox repo
       → `pull` (decrypt locally) → Claude Code `story-anonymise` skill writes a
       draft → `check` → `approve` → `export` into the public site.

Nothing is published without `approve`. Decrypted text and drafts live under
community/inbox/ and community/stories/drafts/, both git-ignored; only
approved, anonymised stories (community/stories/approved/) are committed.

    python3 scripts/stories.py keygen
    python3 scripts/stories.py pull --inbox ~/src/pd-defence-stories-inbox [--git-pull]
    python3 scripts/stories.py list
    python3 scripts/stories.py check <id> [--allow "Wall Street"]
    python3 scripts/stories.py approve <id> [--allow ...] [--featured]
    python3 scripts/stories.py reject <id> --reason "..."
    python3 scripts/stories.py export --out SITE/data
    python3 scripts/stories.py purge
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMUNITY = ROOT / "community"
INBOX = COMMUNITY / "inbox"                      # decrypted submissions (git-ignored)
DRAFTS = COMMUNITY / "stories" / "drafts"        # anonymised, unapproved (git-ignored)
APPROVED = COMMUNITY / "stories" / "approved"    # published (committed)
REJECTED = COMMUNITY / "stories" / "rejected.txt"
KEY = Path(os.environ.get("PD_STORIES_KEY", Path.home() / ".config" / "pd-defence" / "stories_key.pem"))

VOCAB = {
    "channel": ["whatsapp", "telegram", "discord", "facebook", "instagram", "x-twitter", "tiktok", "youtube",
                "reddit", "stocktwits", "text-message", "phone-call", "email", "dating-app", "friend-or-family",
                "other"],
    "tactics": ["investment-club", "fake-adviser", "teacher-or-professor", "insider-tip", "urgency",
                "screenshots-of-gains", "fake-news", "ipo-allocation", "vip-group", "small-new-listing",
                "foreign-issuer", "move-to-private-chat", "buy-signal-time"],
    "outcome": ["sold-at-loss", "still-holding", "account-restricted", "recovery-scam-attempt",
                "reported-to-regulator", "broker-helped"],
    "loss_range": ["under-1k", "1k-10k", "10k-50k", "50k-plus", "prefer-not-to-say"],
}
PUBLIC_FIELDS = ["id", "title", "summary", "body", "stocks", "month_from", "month_to", "submitted", "channel",
                 "tactics", "outcome", "loss_range", "language", "read_minutes", "featured"]
MIN_LENGTH_RATIO = 0.6
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
REGULATOR_HOSTS = ("sec.gov", "finra.org", "ic3.gov", "investor.gov", "irs.gov", "ftc.gov")
MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
          "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")

# ---------------------------------------------------------------- PII checks
PII = [
    ("email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("web link", re.compile(r"(?:https?://|www\.)\S+", re.I)),
    ("social handle", re.compile(r"(?<![\w@])@[A-Za-z0-9_]{2,}")),
    ("phone number", re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){8,}(?!\w)")),
    ("long number (account / order id?)", re.compile(r"(?<![\d,.$])\d{7,}(?![\d,])")),
    ("exact dollar amount", re.compile(r"\$\s?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\s?\d{4,}(?:\.\d+)?")),
    ("exact date", re.compile(rf"\b(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\b|\b\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?\b|"
                              r"\b\d{4}-\d{2}-\d{2}\b")),
]
NAME_PAIR = re.compile(r"\b([A-Z][a-z]{1,20})\s+([A-Z][a-z]{1,20})\b")
NOT_NAMES = {
    "Wall Street", "New York", "United States", "Hong Kong", "Securities Exchange", "Exchange Commission",
    "Investment Club", "Pump Dump", "Dump Defender", "Stock Exchange", "Federal Bureau", "Investor Alert",
    "Social Security", "Google Play", "App Store", "Middle East", "South Africa", "North America",
    "Customer Service", "Customer Support", "Help Center",
}


def pii_findings(text: str) -> list[str]:
    out = []
    for label, rx in PII:
        for m in rx.finditer(text):
            s = m.group(0)
            if label == "web link" and any(h in s.lower() for h in REGULATOR_HOSTS):
                continue
            if label == "exact dollar amount" and re.sub(r"[^\d.]", "", s).split(".")[0].endswith("000"):
                continue                     # round figures ("$10,000") don't identify anyone; $17,431 does
            out.append(f"{label}: {s.strip()[:40]}")
    return out


def name_candidates(text: str, allow: set[str] = frozenset()) -> set[str]:
    """Capitalised word pairs that look like a person's name. Deliberately
    over-inclusive: a false hit costs the owner one --allow."""
    out = set()
    for m in NAME_PAIR.finditer(text):
        pair = f"{m.group(1)} {m.group(2)}"
        if pair in NOT_NAMES or pair in allow or m.group(1) in ("The", "My", "Our", "This", "That", "When", "Then"):
            continue
        if re.fullmatch(MONTHS, m.group(1)) or re.fullmatch(MONTHS, m.group(2)):
            continue
        out.add(pair)
    return out


def check_draft(draft: dict, raw: dict | None, allow: set[str] = frozenset()) -> tuple[list[str], list[str]]:
    """(errors, notes). Errors block approval; notes are for the owner's eyes."""
    errors, notes = [], []
    for f in ("id", "title", "summary", "body", "stocks", "submitted", "channel", "tactics", "loss_range"):
        if draft.get(f) in (None, "", []) and f not in ("tactics",):
            errors.append(f"missing {f}")
    if len(draft.get("title", "")) > 90:
        errors.append("title longer than 90 characters")
    if len(draft.get("summary", "")) > 280:
        errors.append("summary longer than 280 characters")
    for s in draft.get("stocks", []):
        if not SYMBOL.match(s):
            errors.append(f"bad ticker {s!r}")
    for f in ("month_from", "month_to"):
        if draft.get(f) and not MONTH.match(draft[f]):
            errors.append(f"{f} must be YYYY-MM")
    if draft.get("channel") and draft["channel"] not in VOCAB["channel"]:
        errors.append(f"channel {draft['channel']!r} not in vocabulary")
    for f in ("tactics", "outcome"):
        for t in draft.get(f, []):
            if t not in VOCAB[f]:
                errors.append(f"{f} tag {t!r} not in vocabulary")
    if draft.get("loss_range") and draft["loss_range"] not in VOCAB["loss_range"]:
        errors.append(f"loss_range {draft['loss_range']!r} not in vocabulary")
    public_text = " ".join(str(draft.get(f, "")) for f in ("title", "summary", "body"))
    errors += [f"personal data left in: {x}" for x in pii_findings(public_text)]
    names = name_candidates(public_text, allow)
    if raw is not None:
        raw_text = raw.get("text", "")
        raw_names = name_candidates(raw_text, allow)
        for n in sorted(names & raw_names):
            errors.append(f"possible person name kept from the original: {n!r} (replace with a role, or --allow)")
        if len(draft.get("body", "")) < MIN_LENGTH_RATIO * len(raw_text):
            errors.append(f"body is {len(draft.get('body', ''))} chars vs {len(raw_text)} original — the storyline "
                          f"must be kept, not summarised (minimum {MIN_LENGTH_RATIO:.0%})")
        missing = set(raw.get("stocks", [])) - set(draft.get("stocks", []))
        if missing:
            errors.append(f"stocks from the submission dropped: {sorted(missing)}")
        if not raw.get("consent"):
            errors.append("the submission has no consent to publish")
    elif names:
        notes.append(f"name-like words to check by eye: {sorted(names)}")
    caps = sorted(set(re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", draft.get("body", ""))) - {"The", "I", "It", "My", "We"})
    notes.append("capitalised words to scan for names or real firms: " + ", ".join(caps[:60]))
    if re.search(r"\[In your own words", public_text):
        errors.append("placeholder text left in the story — replace every [In your own words: ...] part")
    if re.search(r"\b(kill myself|suicide|end my life|self.harm)\b", public_text, re.I):
        errors.append("mentions self-harm: contact the author with support resources before anything is published")
    return errors, notes


# ---------------------------------------------------------------- crypto
def keygen(path: Path = KEY) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    if path.exists():
        raise SystemExit(f"{path} exists; refusing to overwrite the key that decrypts your inbox")
    path.parent.mkdir(parents=True, exist_ok=True)
    k = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    path.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    os.chmod(path, 0o600)
    spki = k.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(spki).decode()


def decrypt(envelope: dict, key_pem: bytes) -> dict:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if envelope.get("alg") != "RSA-OAEP-256+A256GCM":
        raise ValueError(f"unknown envelope alg {envelope.get('alg')!r}")
    priv = serialization.load_pem_private_key(key_pem, password=None)
    aes = priv.decrypt(base64.b64decode(envelope["key"]),
                       padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    plain = AESGCM(aes).decrypt(base64.b64decode(envelope["iv"]), base64.b64decode(envelope["data"]), None)
    return json.loads(plain)


# ---------------------------------------------------------------- store helpers
def _read(p: Path) -> dict:
    return json.loads(p.read_text())


def _write(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def rejected_ids() -> set[str]:
    return {line.split()[0] for line in REJECTED.read_text().splitlines() if line.strip()} if REJECTED.exists() else set()


def pull(inbox_repo: Path, key_pem: bytes, git_pull: bool = False) -> list[str]:
    if git_pull:
        subprocess.run(["git", "-C", str(inbox_repo), "pull", "-q"], check=True)
    done = {p.stem for d in (INBOX, DRAFTS, APPROVED) if d.exists() for p in d.glob("*.json")} | rejected_ids()
    new = []
    for f in sorted((inbox_repo / "inbox").rglob("*.json")):
        env = _read(f)
        if env.get("id") in done:
            continue
        story = decrypt(env, key_pem)
        story.update({"id": env["id"], "received": env.get("received")})
        _write(INBOX / f"{env['id']}.json", story)
        os.chmod(INBOX / f"{env['id']}.json", 0o600)
        new.append(env["id"])
    return new


def read_minutes(text: str) -> int:
    return max(1, math.ceil(len(text.split()) / 200))


def approve(sid: str, allow: set[str], featured: bool = False, today: str | None = None) -> Path:
    draft_p = DRAFTS / f"{sid}.json"
    if not draft_p.exists():
        raise SystemExit(f"no draft for {sid}: run the story-anonymise skill first")
    draft = _read(draft_p)
    raw_p = INBOX / f"{sid}.json"
    raw = _read(raw_p) if raw_p.exists() else None
    errors, _ = check_draft(draft, raw, allow)
    if errors:
        raise SystemExit("not approved:\n  " + "\n  ".join(errors))
    draft.update({"status": "approved", "published": today or dt.date.today().isoformat(),
                  "read_minutes": read_minutes(draft["body"])})
    if featured:
        draft["featured"] = True
    out = APPROVED / f"{sid}.json"
    _write(out, draft)
    draft_p.unlink()
    return out


def reject(sid: str, reason: str) -> None:
    REJECTED.parent.mkdir(parents=True, exist_ok=True)
    with REJECTED.open("a") as fh:
        fh.write(f"{sid} {dt.date.today().isoformat()} {reason.replace(chr(10), ' ')[:200]}\n")
    for p in (DRAFTS / f"{sid}.json", INBOX / f"{sid}.json"):
        if p.exists():
            p.unlink()


def purge() -> int:
    """Delete decrypted originals of stories already approved or rejected."""
    gone = {p.stem for p in APPROVED.glob("*.json")} | rejected_ids()
    n = 0
    for p in INBOX.glob("*.json"):
        if p.stem in gone:
            p.unlink()
            n += 1
    return n


def export(approved_dir: Path | None = None, now: dt.date | None = None) -> dict:
    approved_dir = approved_dir or APPROVED
    stories = []
    for p in sorted(approved_dir.glob("*.json")) if approved_dir.exists() else []:
        s = _read(p)
        if s.get("status") != "approved":
            continue
        s.setdefault("read_minutes", read_minutes(s.get("body", "")))
        stories.append({k: s.get(k) for k in PUBLIC_FIELDS if s.get(k) not in (None, "", [])})
    stories.sort(key=lambda s: s.get("submitted", ""), reverse=True)     # newest first,
    stories.sort(key=lambda s: not s.get("featured", False))            # featured on top (stable)
    stocks: dict[str, dict] = {}
    tags = {"tactics": {}, "channel": {}, "outcome": {}, "loss_range": {}}
    for s in stories:
        first = s.get("month_from") or s.get("submitted", "")[:7]
        last = s.get("month_to") or first
        for sym in s.get("stocks", []):
            e = stocks.setdefault(sym, {"s": sym, "people": 0, "first_month": first, "last_month": last})
            e["people"] += 1
            e["first_month"], e["last_month"] = min(e["first_month"], first), max(e["last_month"], last)
        for t in s.get("tactics", []):
            tags["tactics"][t] = tags["tactics"].get(t, 0) + 1
        for f in ("channel", "loss_range"):
            if s.get(f):
                tags[f][s[f]] = tags[f].get(s[f], 0) + 1
        for t in s.get("outcome", []):
            tags["outcome"][t] = tags["outcome"].get(t, 0) + 1
    return {"built": (now or dt.date.today()).isoformat(), "count": len(stories), "stories": stories,
            "stocks": sorted(stocks.values(), key=lambda e: (-e["people"], e["s"])), "tags": tags,
            "vocab": VOCAB}


# ---------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="stories")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keygen")
    p = sub.add_parser("pull"); p.add_argument("--inbox", required=True); p.add_argument("--git-pull", action="store_true")
    sub.add_parser("list")
    for name in ("check", "approve"):
        c = sub.add_parser(name); c.add_argument("id"); c.add_argument("--allow", action="append", default=[])
        if name == "approve":
            c.add_argument("--featured", action="store_true")
    st = sub.add_parser("stage", help="copy a draft file (e.g. the owner's own story) into drafts/")
    st.add_argument("file")
    r = sub.add_parser("reject"); r.add_argument("id"); r.add_argument("--reason", required=True)
    e = sub.add_parser("export"); e.add_argument("--out", required=True)
    sub.add_parser("purge")
    a = ap.parse_args(argv)

    if a.cmd == "keygen":
        spki = keygen()
        print(f"private key written to {KEY} (mode 600). Keep it backed up offline; without it the inbox can't be read.")
        print("\nSet this as the Worker variable STORIES_PUBLIC_KEY:\n")
        print(spki)
    elif a.cmd == "pull":
        new = pull(Path(a.inbox).expanduser(), KEY.read_bytes(), a.git_pull)
        print(f"{len(new)} new: {', '.join(new) or '—'}  (decrypted to {INBOX}, git-ignored)")
    elif a.cmd == "list":
        raw = {p.stem for p in INBOX.glob("*.json")}
        drafts = {p.stem for p in DRAFTS.glob("*.json")}
        appr = {p.stem for p in APPROVED.glob("*.json")}
        print(f"waiting for anonymisation: {sorted(raw - drafts - appr) or '—'}")
        for sid in sorted(drafts):
            raw_p = INBOX / f"{sid}.json"
            errs, _ = check_draft(_read(DRAFTS / f"{sid}.json"), _read(raw_p) if raw_p.exists() else None)
            print(f"draft {sid}: {'ready to approve' if not errs else f'{len(errs)} problem(s)'}")
        print(f"approved: {len(appr)}; rejected: {len(rejected_ids())}")
    elif a.cmd == "check":
        raw_p = INBOX / f"{a.id}.json"
        errs, notes = check_draft(_read(DRAFTS / f"{a.id}.json"), _read(raw_p) if raw_p.exists() else None, set(a.allow))
        for n in notes:
            print("note:", n)
        for x in errs:
            print("ERROR:", x)
        print("OK — ready for `approve`" if not errs else f"{len(errs)} problem(s)")
        return 1 if errs else 0
    elif a.cmd == "approve":
        print(approve(a.id, set(a.allow), a.featured))
    elif a.cmd == "stage":
        d = _read(Path(a.file))
        _write(DRAFTS / f"{d['id']}.json", d)
        print(f"staged {d['id']}: edit {DRAFTS / (d['id'] + '.json')}, then `check` and `approve`")
    elif a.cmd == "reject":
        reject(a.id, a.reason)
        print(f"rejected {a.id}")
    elif a.cmd == "export":
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        data = export()
        (out / "stories.json").write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
        print(f"{data['count']} stories → {out / 'stories.json'}")
    elif a.cmd == "purge":
        print(f"deleted {purge()} decrypted originals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
