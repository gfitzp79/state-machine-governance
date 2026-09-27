#!/bin/sh
# Fresh database, standard seed, then the scope-aware testing demo on top.
#
#   sh e2e/reset-demo.sh            from platform/, stack name "platform"
#   PROJECT=smg-feat sh e2e/reset-demo.sh
#
# Each recorded journey starts from this state, so every video is reproducible.
set -e
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
PROJECT="${PROJECT:-platform}"

docker compose -p "$PROJECT" down -v >/dev/null 2>&1
docker compose -p "$PROJECT" up -d --build --wait >/dev/null 2>&1
docker compose -p "$PROJECT" cp e2e/seed_scope_demo.py api:/tmp/seed_scope_demo.py >/dev/null 2>&1
docker compose -p "$PROJECT" exec -T -e PYTHONPATH=/srv api python /tmp/seed_scope_demo.py
