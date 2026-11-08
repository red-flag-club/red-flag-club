#!/usr/bin/env bash
# One-time (and re-runnable) set-up of the red-flag-club organisation's repos,
# labels and spec-pipeline board (spec 008, docs/workflow.md).
#
#   gh auth login            # as the MAINTAINER account, never a personal one
#   scripts/org_setup.sh [--dry-run]
#
# Needs gh >= 2.40 with the `project` scope (gh auth refresh -s project).
# It never touches secrets, deploy keys or Pages: those stay manual
# (specs/008-community-org/plan.md, Phase 4).
set -euo pipefail

ORG="${ORG:-red-flag-club}"
PUBLIC_REPOS=(red-flag-club red-flag-club.github.io stories .github)
PRIVATE_REPOS=(pd-defender stories-inbox)
PROJECT_TITLE="Red Flag Club: spec pipeline"
PHASES=(Inbox Specify Plan Tasks Implement Review Done "Won't do" Blocked)
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LABELS="$HERE/public/dotgithub/labels.json"
DRY=0; [[ "${1:-}" == "--dry-run" ]] && DRY=1

run() { if (( DRY )); then echo "+ $*"; else "$@"; fi; }
exists() { gh repo view "$ORG/$1" --json name >/dev/null 2>&1; }

echo "== who am I"
gh api user --jq '"signed in as " + .login + " (use the maintainer account, not a personal one)"'

echo "== labels in every repo"
for repo in "${PUBLIC_REPOS[@]}" "${PRIVATE_REPOS[@]}"; do
  exists "$repo" || { echo "skip $ORG/$repo (not created yet)"; continue; }
  python3 - "$LABELS" <<'PY' | while IFS=$'\t' read -r name color desc; do
import json, sys
for l in json.load(open(sys.argv[1])):
    print(f"{l['name']}\t{l['color']}\t{l['description']}")
PY
    run gh label create "$name" --repo "$ORG/$repo" --color "$color" --description "$desc" --force >/dev/null
  done
  echo "labels: $ORG/$repo"
done

echo "== repo settings"
for repo in "${PUBLIC_REPOS[@]}" "${PRIVATE_REPOS[@]}"; do
  exists "$repo" || continue
  run gh repo edit "$ORG/$repo" --delete-branch-on-merge --enable-squash-merge \
      --enable-merge-commit=false --enable-rebase-merge=false >/dev/null
done
exists red-flag-club && run gh repo edit "$ORG/red-flag-club" --enable-discussions --enable-issues \
    --description "Open-source defence against pump-and-dump scams: checks, community site, true stories" \
    --homepage "https://red-flag-club.github.io" >/dev/null
exists red-flag-club.github.io && run gh repo edit "$ORG/red-flag-club.github.io" --enable-issues=false \
    --enable-wiki=false --description "The published Red Flag Club site (built by a bot)" >/dev/null
exists stories && run gh repo edit "$ORG/stories" --enable-wiki=false \
    --description "True, anonymised pump-and-dump stories (CC BY-NC-ND 4.0)" >/dev/null

echo "== branch protection on the code repo"
if exists red-flag-club && (( ! DRY )); then
  gh api -X PUT "repos/$ORG/red-flag-club/branches/main/protection" --input - >/dev/null <<'JSON' || echo "branch protection: set it in Settings → Branches"
{
  "required_status_checks": {"strict": true, "contexts": ["tests (3.11)", "tests (3.12)", "node", "leak-gate", "spec-gate / spec-gate"]},
  "enforce_admins": true,
  "required_pull_request_reviews": {"required_approving_review_count": 1, "require_code_owner_reviews": true, "dismiss_stale_reviews": true},
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
fi

echo "== the board"
number=$(gh project list --owner "$ORG" --format json --jq ".projects[] | select(.title == \"$PROJECT_TITLE\") | .number" || true)
if [[ -z "$number" ]]; then
  if (( DRY )); then echo "+ gh project create --owner $ORG --title \"$PROJECT_TITLE\""; number=0
  else number=$(gh project create --owner "$ORG" --title "$PROJECT_TITLE" --format json --jq .number); fi
fi
echo "project number: $number"
if (( ! DRY )); then
  if ! gh project field-list "$number" --owner "$ORG" --format json --jq '.fields[].name' | grep -qx Phase; then
    opts=$(IFS=,; echo "${PHASES[*]}")
    gh project field-create "$number" --owner "$ORG" --name Phase --data-type SINGLE_SELECT \
        --single-select-options "$opts" >/dev/null
  fi
  for repo in "${PUBLIC_REPOS[@]}" "${PRIVATE_REPOS[@]}"; do
    exists "$repo" && gh project link "$number" --owner "$ORG" --repo "$ORG/$repo" >/dev/null 2>&1 || true
  done
  gh project edit "$number" --owner "$ORG" --visibility PUBLIC \
     --description "Every change: issue → spec → plan → tasks → code → review. Maintainers move items; see docs/workflow.md" >/dev/null
fi

cat <<EOF

Done. By hand (GitHub has no API for these):
  1. Project $number → Settings → Manage access: org members "Read"; team "maintainers" "Write".
  2. Project → Workflows: turn on "Auto-add to project" for each repo (filter: is:issue,pr is:open),
     "Item closed" → Phase Done, "Pull request merged" → Phase Done.
  3. Views: a Board grouped by Phase, and a table "Waiting for review" filtered to Specify/Plan/Tasks/Review.
  4. In $ORG/.github → Settings → Variables: PROJECT_NUMBER=$number, and either BOT_APP_ID +
     secret BOT_APP_PRIVATE_KEY (recommended) or secret PROJECT_TOKEN.
  5. Team "maintainers": visibility "secret" so membership isn't public.
EOF
