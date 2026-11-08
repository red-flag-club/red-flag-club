# Implementation Plan: Community Stories

## Pieces
| Piece | Where | Runs |
|---|---|---|
| Brand + social card | `web/index.html`, `web/og.png`, `web/app.css` | static |
| Share form (voice/text), Stories wall, story page, Stocks page, Quiz | `web/stories.js`, `web/quiz.js`, `web/app.js` routes | browser |
| Intake | `worker/stories/` (Cloudflare Worker, plain JS, WebCrypto) | Cloudflare free |
| Inbox | separate private repo, ciphertext only | GitHub |
| Owner tooling | `scripts/stories.py` (`keygen`, `pull`, `list`, `check`, `approve`, `reject`, `export`) | owner's machine |
| Anonymiser | `.claude/skills/story-anonymise/SKILL.md` | owner's Claude Code |
| Publish | `.github/workflows/site.yml` runs `stories.py export` into the site | self-hosted runner |

## Constitution Check
Read-only against the brokerage (no change). Stories are user content, not
defence-path verdicts; no buy signal; nothing about a stock is asserted by the
system beyond its existing risk check. Recall/lookahead unaffected. `cryptography`
(Python) is needed only by the owner tooling to decrypt — justified by FR-001.

## Security notes
- The Worker's GitHub token is fine-grained: Contents read/write on the inbox
  repo only. The private key never leaves the owner's machine
  (`~/.config/pd-defence/stories_key.pem`, mode 600).
- Decrypted inbox and drafts live under `community/inbox/` (git-ignored);
  only approved, anonymised stories are committed.
