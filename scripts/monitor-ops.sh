#!/usr/bin/env bash
# Ops monitor — runs every 5 minutes via systemd timer.
# Checks backend health for each configured environment and sends
# alert emails on failure or a daily heartbeat when all is well.
set -euo pipefail

BASE_DIR="/opt/collective-will"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load monitor-specific env vars from each environment's .env file.
# The Python module reads OPS_ALERT_EMAILS, RESEND_API_KEY, EMAIL_FROM,
# OPS_HEARTBEAT_HOUR_UTC, and OPS_ALERT_DEDUP_MINUTES from the process env.

load_env_file() {
  local envfile="$1"
  if [[ -f "$envfile" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$envfile"
    set +a
  fi
}

# Determine which environments are available
ENVS_FOUND=0

if [[ -f "${BASE_DIR}/staging/.env" ]]; then
  STAGING_PORT="$(grep -E '^BACKEND_PORT=' "${BASE_DIR}/staging/.env" 2>/dev/null | cut -d= -f2 || echo 8100)"
  export MONITOR_STAGING_URL="http://127.0.0.1:${STAGING_PORT:-8100}"
  ENVS_FOUND=1
fi

if [[ -f "${BASE_DIR}/production/.env" ]]; then
  PROD_PORT="$(grep -E '^BACKEND_PORT=' "${BASE_DIR}/production/.env" 2>/dev/null | cut -d= -f2 || echo 8000)"
  export MONITOR_PRODUCTION_URL="http://127.0.0.1:${PROD_PORT:-8000}"
  ENVS_FOUND=1
fi

if [[ "$ENVS_FOUND" -eq 0 ]]; then
  echo "No environment .env files found under ${BASE_DIR}. Nothing to monitor." >&2
  exit 0
fi

# Load shared secrets (RESEND_API_KEY, OPS_ALERT_EMAILS, etc.)
# Try staging first, then production — they share the same API keys.
for env_name in staging production; do
  envfile="${BASE_DIR}/${env_name}/.env"
  if [[ -f "$envfile" ]]; then
    load_env_file "$envfile"
    break
  fi
done

# Run the Python monitor module
cd "${BASE_DIR}/repo-deploy" 2>/dev/null || cd "${SCRIPT_DIR}/.."

# Use the backend Docker image to run the monitor (no local Python needed)
BACKEND_IMAGE="ghcr.io/civil-whisper/collective-will-backend:latest"

docker run --rm --network host \
  -e MONITOR_STAGING_URL="${MONITOR_STAGING_URL:-}" \
  -e MONITOR_PRODUCTION_URL="${MONITOR_PRODUCTION_URL:-}" \
  -e OPS_ALERT_EMAILS="${OPS_ALERT_EMAILS:-}" \
  -e RESEND_API_KEY="${RESEND_API_KEY:-}" \
  -e EMAIL_FROM="${EMAIL_FROM:-ops@resend.dev}" \
  -e OPS_HEARTBEAT_HOUR_UTC="${OPS_HEARTBEAT_HOUR_UTC:-8}" \
  -e OPS_ALERT_DEDUP_MINUTES="${OPS_ALERT_DEDUP_MINUTES:-60}" \
  -v /var/lib/collective-will-monitor:/var/lib/collective-will-monitor \
  "${BACKEND_IMAGE}" \
  uv run python -m src.ops.monitor
