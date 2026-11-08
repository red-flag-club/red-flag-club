"""Community stories owner tooling (specs/007-community-stories)."""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import stories as S

RAW = {
    "id": "sabc12345", "consent": True, "stocks": ["RYDE"], "channel": "whatsapp",
    "text": ("I saw an ad on Facebook and joined a WhatsApp group run by John Carter, who called himself a professor. "
             "On September 9 he told us all to buy RYDE before 'the big news'. I put in $17,431 from my savings. "
             "My account number is 5551234987 and you can reach me at victim@example.com or +1 (312) 555-0199. "
             "Two days later it fell 90% and the group vanished. Then someone called offering to recover my money "
             "for a fee. I reported it to the SEC at https://www.sec.gov/tcr and to the FBI."),
}
GOOD = {
    "id": "sabc12345", "title": "A WhatsApp 'professor' and RYDE",
    "summary": "An ad led to a WhatsApp group where a self-styled professor pushed RYDE; it collapsed two days later.",
    "body": ("I saw an ad on Facebook and joined a WhatsApp group run by a man who called himself a professor. "
             "In September he told us all to buy RYDE before 'the big news'. I put in a large part of my savings "
             "(between $10,000 and $50,000). Two days later it fell 90% and the group vanished. Then someone called "
             "offering to recover my money for a fee. I reported it to the SEC at https://www.sec.gov/tcr and to the FBI."),
    "stocks": ["RYDE"], "month_from": "2024-09", "month_to": "2024-09", "submitted": "2026-10-16",
    "channel": "whatsapp", "tactics": ["investment-club", "teacher-or-professor", "urgency"],
    "outcome": ["sold-at-loss", "recovery-scam-attempt", "reported-to-regulator"], "loss_range": "10k-50k",
    "language": "en",
}


def test_checker_passes_a_proper_anonymisation():
    errors, notes = S.check_draft(GOOD, RAW)
    assert errors == [], errors
    assert any("capitalised words" in n for n in notes)


@pytest.mark.parametrize("leak,label", [
    ("victim@example.com", "email"), ("+1 (312) 555-0199", "phone"), ("5551234987", "long number"),
    ("$17,431", "dollar amount"), ("September 9", "exact date"), ("@pumpking", "handle"),
    ("https://t.me/clubxyz", "web link"), ("John Carter", "person name"),
])
def test_checker_catches_each_kind_of_personal_data(leak, label):
    bad = dict(GOOD, body=GOOD["body"] + f" Detail: {leak}.")
    errors, _ = S.check_draft(bad, RAW)
    assert errors, f"{label} not caught"


def test_checker_protects_the_storyline_and_stocks_and_vocabulary():
    short = dict(GOOD, body="Lost money on RYDE via WhatsApp.")
    assert any("storyline" in e for e in S.check_draft(short, RAW)[0])
    no_stock = dict(GOOD, stocks=[])
    assert any("dropped" in e for e in S.check_draft(no_stock, RAW)[0])
    bad_tag = dict(GOOD, tactics=["made-up"])
    assert any("vocabulary" in e for e in S.check_draft(bad_tag, RAW)[0])
    no_consent = dict(RAW, consent=False)
    assert any("consent" in e for e in S.check_draft(GOOD, no_consent)[0])


def test_regulator_links_and_share_prices_are_allowed():
    ok = dict(GOOD, body=GOOD["body"] + " It traded at $3.50 a share. See https://www.investor.gov for help.")
    assert S.check_draft(ok, RAW)[0] == []


def test_self_harm_blocks_publication():
    sad = dict(GOOD, body=GOOD["body"] + " I wanted to end my life.")
    assert any("self-harm" in e for e in S.check_draft(sad, RAW)[0])


@pytest.fixture()
def community(tmp_path, monkeypatch):
    base = tmp_path / "community"
    for name, sub in (("INBOX", "inbox"), ("DRAFTS", "stories/drafts"), ("APPROVED", "stories/approved")):
        monkeypatch.setattr(S, name, base / sub)
    monkeypatch.setattr(S, "REJECTED", base / "stories" / "rejected.txt")
    return base


def test_approve_requires_a_clean_draft_and_export_has_only_public_fields(community):
    S._write(S.INBOX / "sabc12345.json", RAW)
    S._write(S.DRAFTS / "sabc12345.json", dict(GOOD, body=GOOD["body"] + " Call 312-555-0199."))
    with pytest.raises(SystemExit):
        S.approve("sabc12345", set())
    S._write(S.DRAFTS / "sabc12345.json", GOOD)
    S.approve("sabc12345", set(), today="2026-10-16")
    assert not (S.DRAFTS / "sabc12345.json").exists()
    data = S.export()
    assert data["count"] == 1
    story = data["stories"][0]
    assert set(story) <= set(S.PUBLIC_FIELDS)
    assert "text" not in story and "consent" not in story
    assert data["stocks"] == [{"s": "RYDE", "people": 1, "first_month": "2024-09", "last_month": "2024-09"}]
    assert data["tags"]["tactics"]["teacher-or-professor"] == 1
    assert S.purge() == 1 and not (S.INBOX / "sabc12345.json").exists()


def test_reject_removes_decrypted_text(community):
    S._write(S.INBOX / "sx.json", RAW)
    S.reject("sx", "spam")
    assert not (S.INBOX / "sx.json").exists() and "sx" in S.rejected_ids()


def test_export_counts_people_per_stock_and_orders_featured_first(community):
    for i, (sym, month, feat) in enumerate([("RYDE", "2024-09", False), ("RYDE", "2024-10", True), ("ABCD", "2025-01", False)]):
        S._write(S.APPROVED / f"s{i}.json", dict(GOOD, id=f"s{i}", stocks=[sym], month_from=month, month_to=month,
                                                  submitted=f"2026-10-1{i}", status="approved", featured=feat))
    data = S.export()
    assert data["stories"][0]["id"] == "s1"
    ryde = next(e for e in data["stocks"] if e["s"] == "RYDE")
    assert ryde == {"s": "RYDE", "people": 2, "first_month": "2024-09", "last_month": "2024-10"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_worker_ciphertext_decrypts_in_python(tmp_path, monkeypatch):
    """SC-001: encrypt with the Worker's code (Node WebCrypto), decrypt here."""
    key = tmp_path / "k.pem"
    spki = S.keygen(key)
    with pytest.raises(SystemExit):
        S.keygen(key)                                                   # never overwrites
    assert oct(key.stat().st_mode)[-3:] == "600"
    payload = {"text": RAW["text"], "stocks": ["RYDE"], "consent": True}
    cli = Path(S.ROOT / "worker" / "stories" / "encrypt_cli.mjs")
    out = subprocess.run(["node", str(cli), json.dumps(payload), spki], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    envelope = json.loads(out.stdout)
    assert RAW["text"][:20] not in json.dumps(envelope)
    assert S.decrypt(envelope, key.read_bytes()) == payload
    # pull: inbox repo layout → decrypted, git-ignored copy
    repo = tmp_path / "inbox-repo"
    (repo / "inbox" / "2026" / "10").mkdir(parents=True)
    (repo / "inbox" / "2026" / "10" / "sq.json").write_text(json.dumps({"v": 1, "id": "sq", "received": "2026-10-16", **envelope}))
    base = tmp_path / "community"
    monkeypatch.setattr(S, "INBOX", base / "inbox")
    monkeypatch.setattr(S, "DRAFTS", base / "drafts")
    monkeypatch.setattr(S, "APPROVED", base / "approved")
    monkeypatch.setattr(S, "REJECTED", base / "rejected.txt")
    assert S.pull(repo, key.read_bytes()) == ["sq"]
    assert S.pull(repo, key.read_bytes()) == []                        # idempotent
    assert json.loads((base / "inbox" / "sq.json").read_text())["text"] == RAW["text"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_worker_node_suite():
    r = subprocess.run(["node", "--test", str(S.ROOT / "worker" / "stories" / "index.test.mjs")],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
