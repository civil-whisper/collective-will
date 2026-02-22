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
export COMPOSE_PROJECT_NAME="collective-will-${ENV}"

echo "==> Pulling latest images..."
docker compose pull

echo "==> Starting services..."
docker compose up -d --remove-orphans

echo "==> Cleaning up old images..."
docker image prune -f

echo "==> Deploy complete for ${ENV}"
docker compose ps
