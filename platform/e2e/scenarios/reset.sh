#!/usr/bin/env bash
# Rebuild the stack from a clean, freshly seeded database.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose down -v >/dev/null 2>&1
docker compose up -d --wait >/dev/null 2>&1
echo "reset ok"
