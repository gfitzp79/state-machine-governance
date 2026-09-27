#!/usr/bin/env bash
#
# Apply this repository's rules to main, as two GitHub rulesets.
#
# CODEOWNERS does nothing on its own. Without rules behind it, it is a list of
# names in a file: exactly the sort of control this project exists to argue
# against. This script is the enforcement, kept in the repository so the
# intended settings are reviewable rather than living only in somebody's browser
# history.
#
#   main: integrity   No bypass for anyone, the maintainer included.
#                     - every change arrives by pull request
#                     - all three CI jobs pass, on a branch up to date with main
#                     - history stays linear
#                     - main cannot be force-pushed or deleted
#
#   main: review      The maintainer may bypass this one, and only by merging a
#                     pull request, never by pushing. GitHub records each bypass.
#                     - one approval
#                     - code-owner review on the paths in .github/CODEOWNERS
#                     - approvals dismissed when new commits land
#                     - review conversations resolved before merge
#
# Why the split. The maintainer is the only code owner, and GitHub never counts
# a pull request author's own approval. A single rule requiring code-owner review
# with nobody able to bypass it would leave the maintainer unable to merge a
# framework change ever again; the first version of this script did exactly
# that and was, luckily, never run. Splitting the rules by who may bypass them
# keeps the part that must hold for everyone (CI, pull requests, no rewriting
# main) out of reach, and makes the one exception visible rather than silent.
#
#                     platform change            framework change
#   contributor       an approval from anyone    the maintainer's approval
#   maintainer        a contributor's approval   a recorded bypass on the PR
#
# Nobody else can approve a framework change. That is the "framework stays
# static" rule in CONTRIBUTING.md working, not a gap in it.
#
# Needs the GitHub CLI, authenticated as a repository admin:
#   https://cli.github.com
#   gh auth login
#
# Run from anywhere:
#   ./tools/setup_branch_protection.sh
#
# Re-running is safe. Each ruleset is found by name and replaced, not added to.

set -euo pipefail

REPO="${REPO:-gfitzp79/state-machine-governance}"
MAINTAINER="${MAINTAINER:-gfitzp79}"

command -v gh >/dev/null 2>&1 || {
  echo "gh is not installed. See https://cli.github.com" >&2
  exit 1
}

# Endpoints carry no leading slash. Git Bash on Windows rewrites any argument
# that starts with a slash into a filesystem path, so the endpoint reached gh
# as "C:/Program Files/Git/repos/..." and the script failed before applying
# anything. gh accepts both forms; only this one survives every shell.

# The bypass names a person, not a role. Role IDs are opaque numbers the API
# does not document, and a wrong guess would hand the bypass to every writer.
MAINTAINER_ID="$(gh api "users/${MAINTAINER}" --jq .id)"

# 15368 is the GitHub Actions app. Pinning the checks to it means a status
# posted through the API by anything else cannot satisfy them.
ACTIONS_APP_ID=15368

# Create the ruleset, or replace it if one with the same name exists.
apply() {
  local name="$1" body="$2" id
  id="$(gh api "repos/${REPO}/rulesets" --jq ".[] | select(.name == \"${name}\") | .id")"
  if [ -n "${id}" ]; then
    gh api --method PUT "repos/${REPO}/rulesets/${id}" --input - <<<"${body}" >/dev/null
    echo "  replaced  ${name} (${id})"
  else
    gh api --method POST "repos/${REPO}/rulesets" --input - <<<"${body}" >/dev/null
    echo "  created   ${name}"
  fi
}

echo "Applying rules to ${REPO}"

# The three CI jobs, by the names GitHub sees in .github/workflows/ci.yml. A
# ruleset naming a check that never reports blocks every merge forever, so these
# must match the `name:` of each job exactly.
apply "main: integrity" "$(cat <<JSON
{
  "name": "main: integrity",
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

apply "main: review" "$(cat <<JSON
{
  "name": "main: review",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [
    { "actor_id": ${MAINTAINER_ID}, "actor_type": "User", "bypass_mode": "pull_request" }
  ],
  "rules": [
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": true,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true
      }
    }
  ]
}
JSON
)"

echo
echo "Verify:"
echo "  gh api repos/${REPO}/rulesets --jq '.[] | {id, name, enforcement}'"
echo "  gh api repos/${REPO}/rules/branches/main --jq '.[].type'"
