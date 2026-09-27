#!/usr/bin/env bash
#
# Apply this repository's integrity rules to main, as a GitHub ruleset.
#
# CODEOWNERS does nothing on its own. Without rules behind it, it is a list of
# names in a file: exactly the sort of control this project exists to argue
# against. This script is the enforcement, kept in the repository so the
# intended settings are reviewable rather than living only in somebody's browser
# history.
#
# What it applies ("main: integrity", no bypass for anyone, admins included):
#
#   - every change arrives by pull request; nothing is pushed to main directly
#   - all three CI jobs pass, against a branch that is up to date with main
#   - history stays linear
#   - main cannot be force-pushed or deleted
#
# What it does not apply yet: required approvals and code-owner review.
#
# The first version of this script required both, with admins included. It was
# never run, which was lucky. The maintainer is the only code owner, and GitHub
# never counts a pull request author's own approval, so the maintainer could
# never have merged a change to any owned path again. How review should work for
# the maintainer's own framework changes is an open decision, recorded in
# CONTRIBUTING.md, and it belongs in this file once it is made.
#
# Needs the GitHub CLI, authenticated as a repository admin:
#   https://cli.github.com
#   gh auth login
#
# Run from anywhere:
#   ./tools/setup_branch_protection.sh
#
# Re-running is safe. The ruleset is found by name and replaced, not added to.

set -euo pipefail

REPO="${REPO:-gfitzp79/state-machine-governance}"
NAME="main: integrity"

command -v gh >/dev/null 2>&1 || {
  echo "gh is not installed. See https://cli.github.com" >&2
  exit 1
}

# 15368 is the GitHub Actions app. Pinning the checks to it means a status
# posted through the API by anything else cannot satisfy them.
ACTIONS_APP_ID=15368

# The three CI jobs, by the names GitHub sees in .github/workflows/ci.yml. A
# ruleset naming a check that never reports blocks every merge forever, so these
# must match the `name:` of each job exactly.
BODY="$(cat <<JSON
{
  "name": "${NAME}",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "required_linear_history" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "Platform build and enforcement tests", "integration_id": ${ACTIONS_APP_ID} },
          { "context": "Frontend typecheck and build", "integration_id": ${ACTIONS_APP_ID} },
          { "context": "Links, secrets and licence headers", "integration_id": ${ACTIONS_APP_ID} }
        ]
      }
    }
  ]
}
JSON
)"

ID="$(gh api "/repos/${REPO}/rulesets" --jq ".[] | select(.name == \"${NAME}\") | .id")"
if [ -n "${ID}" ]; then
  gh api --method PUT "/repos/${REPO}/rulesets/${ID}" --input - <<<"${BODY}" >/dev/null
  echo "Replaced ruleset '${NAME}' (${ID}) on ${REPO}"
else
  gh api --method POST "/repos/${REPO}/rulesets" --input - <<<"${BODY}" >/dev/null
  echo "Created ruleset '${NAME}' on ${REPO}"
fi

echo
echo "Verify:"
echo "  gh api /repos/${REPO}/rules/branches/main --jq '.[].type'"
