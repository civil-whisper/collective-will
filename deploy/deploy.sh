#!/usr/bin/env bash
set -euo pipefail

ENV="${1:?Usage: deploy.sh <production|staging> <image-tag>}"
IMAGE_TAG="${2:?Usage: deploy.sh <production|staging> <image-tag>}"

BASE_DIR="/opt/collective-will"
ENV_DIR="${BASE_DIR}/${ENV}"
DEPLOY_SRC="${BASE_DIR}/repo-deploy"

if [[ "$ENV" != "production" && "$ENV" != "staging" ]]; then
  echo "Error: environment must be 'production' or 'staging'" >&2
  exit 1
fi

echo "==> Deploying ${ENV} with image tag: ${IMAGE_TAG}"

mkdir -p "${ENV_DIR}"

cp "${DEPLOY_SRC}/docker-compose.prod.yml" "${ENV_DIR}/docker-compose.yml"

if [[ ! -f "${ENV_DIR}/.env" ]]; then
  echo "Error: ${ENV_DIR}/.env not found. Create it with the required secrets first." >&2
  exit 1
fi

cd "${ENV_DIR}"

export IMAGE_TAG

# ---------------------------------------------------------------------------
# Guard: tear down any stale stack whose project name differs from ours.
#
# The canonical project name is the directory basename (staging / production).
# A previous version of this script used COMPOSE_PROJECT_NAME="collective-will-<env>",
# which created a parallel stack that grabbed the same ports.  This block
# detects leftover containers from that (or any other) mismatched project
# name and removes them so the new deploy can bind its ports.
# ---------------------------------------------------------------------------
EXPECTED_PREFIX="${ENV}-"
STALE=$(docker ps -a --format '{{.Names}}' \
  | grep -i "${ENV}" \
  | grep -v "^${EXPECTED_PREFIX}" \
  || true)

if [[ -n "$STALE" ]]; then
  echo "==> Removing stale containers from a previous project name:"
  echo "$STALE"
  echo "$STALE" | xargs -r docker rm -f
fi

echo "==> Pulling latest images..."
docker compose pull

echo "==> Starting services..."
docker compose up -d --remove-orphans

echo "==> Cleaning up old images..."
docker image prune -f

echo "==> Verifying deployment..."
docker compose ps

RUNNING=$(docker compose ps --format '{{.Service}} {{.State}}' | grep -c "running" || true)
EXPECTED=$(docker compose config --services | wc -l | tr -d ' ')
MIGRATE_COUNT=$(docker compose config --services | grep -c "migrate" || true)
EXPECTED_RUNNING=$((EXPECTED - MIGRATE_COUNT))

if [[ "$RUNNING" -lt "$EXPECTED_RUNNING" ]]; then
  echo "WARNING: Only ${RUNNING}/${EXPECTED_RUNNING} services running. Check logs:" >&2
  docker compose ps
  docker compose logs --tail=20
  exit 1
fi

echo "==> Deploy complete for ${ENV} (${RUNNING}/${EXPECTED_RUNNING} services running)"
