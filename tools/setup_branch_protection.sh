#!/usr/bin/env bash
#
# Apply this repository's branch protection to main.
#
# CODEOWNERS does nothing on its own. Without a rule requiring code-owner review,
# it is a list of names in a file: exactly the sort of control this project
# exists to argue against. This script is the enforcement, kept in the repository
# so the intended settings are reviewable rather than living only in somebody's
# browser history.
#
# Needs the GitHub CLI, authenticated as a repository admin:
#   https://cli.github.com
#   gh auth login
#
# Run from anywhere:
#   ./tools/setup_branch_protection.sh
#
# Re-running is safe; the API call replaces the rule rather than adding to it.

set -euo pipefail

REPO="${REPO:-gfitzp79/state-machine-governance}"
BRANCH="${BRANCH:-main}"

command -v gh >/dev/null 2>&1 || {
  echo "gh is not installed. See https://cli.github.com" >&2
  exit 1
}

echo "Applying branch protection to ${REPO}:${BRANCH}"

# The three CI jobs, by the names GitHub sees in .github/workflows/ci.yml.
# A protection rule naming a check that does not exist blocks every merge
# forever, so these must match the `name:` of each job.
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/${REPO}/branches/${BRANCH}/protection" \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Platform build and enforcement tests",
      "Frontend typecheck and build",
      "Links, secrets and licence headers"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "require_code_owner_reviews": true,
    "dismiss_stale_reviews": true,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON

echo
echo "Applied:"
echo "  - a pull request is required, with one approval"
echo "  - code owners must review: every framework path needs the maintainer"
echo "  - approvals are dismissed when new commits land"
echo "  - the three CI jobs must pass, and the branch must be up to date"
echo "  - admins are included. A rule the owner can walk past teaches the"
echo "    contributor that it is optional"
echo "  - linear history: no force pushes, no branch deletion"
echo "  - conversations must be resolved before merge"
echo
echo "Verify:"
echo "  gh api /repos/${REPO}/branches/${BRANCH}/protection | jq '{"
echo "    checks: .required_status_checks.contexts,"
echo "    code_owners: .required_pull_request_reviews.require_code_owner_reviews,"
echo "    admins: .enforce_admins.enabled }'"
