#!/usr/bin/env bash
set -euo pipefail

# Push a local .env file to the VPS.
# Usage: ./scripts/push-env.sh <staging|production> [user@host]
#
# Examples:
#   ./scripts/push-env.sh staging
#   ./scripts/push-env.sh staging deploy@198.51.100.1
#   ./scripts/push-env.sh production deploy@my-vps.example.com

ENV="${1:?Usage: push-env.sh <staging|production> [user@host]}"
VPS="${2:-deploy@${VPS_HOST:?Set VPS_HOST env var or pass user@host as second arg}}"

if [[ "$ENV" != "production" && "$ENV" != "staging" ]]; then
  echo "Error: environment must be 'staging' or 'production'" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_ENV="${SCRIPT_DIR}/../deploy/.env.${ENV}"
REMOTE_DIR="/opt/collective-will/${ENV}"
REMOTE_PATH="${REMOTE_DIR}/.env"

if [[ ! -f "$LOCAL_ENV" ]]; then
  echo "Error: ${LOCAL_ENV} not found" >&2
  exit 1
fi

echo "==> Pushing ${LOCAL_ENV} → ${VPS}:${REMOTE_PATH}"

ssh "$VPS" "mkdir -p ${REMOTE_DIR}"
scp "$LOCAL_ENV" "${VPS}:${REMOTE_PATH}"
ssh "$VPS" "chmod 600 ${REMOTE_PATH}"

echo "==> Done. Verifying..."
ssh "$VPS" "wc -l ${REMOTE_PATH} && echo 'Permissions:' && ls -la ${REMOTE_PATH}"
