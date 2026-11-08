# red-flag-club/.github

Organisation-wide defaults for every Red Flag Club repository:

| File | What it does |
|---|---|
| `profile/README.md` | The organisation's public page |
| `.github/ISSUE_TEMPLATE/` | Issue forms every repo uses (idea, bug, wrong verdict, red-flag report, translation, story correction). Each asks **what**, **why** and **how** |
| `.github/pull_request_template.md` | The PR template, with the hard-rules checklist |
| `.github/workflows/spec-gate.yml` | Reusable check: a PR may only change what its issue's phase allows |
| `.github/workflows/project-sync.yml` | Copies the board's Phase onto issues as `phase:*` labels |
| `labels.json` | The label set, applied to every repo by `scripts/org_setup.sh` in the code repo |
| `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md` | Defaults for repos without their own |

How work moves through the gates: [docs/workflow.md](https://github.com/red-flag-club/red-flag-club/blob/main/docs/workflow.md).
