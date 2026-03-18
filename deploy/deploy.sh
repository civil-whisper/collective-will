#!/usr/bin/env bash
set -euo pipefail

ENV="${1:?Usage: deploy.sh <production|staging> <image-tag>}"
IMAGE_TAG="${2:?Usage: deploy.sh <production|staging> <image-tag>}"

BASE_DIR="/opt/collective-will"
ENV_DIR="${BASE_DIR}/${ENV}"
DEPLOY_SRC="${BASE_DIR}/repo-deploy"
PUBLIC_ENV="${DEPLOY_SRC}/public.env.${ENV}"
SECRETS_ENV="${ENV_DIR}/.env.secrets"
LEGACY_ENV="${ENV_DIR}/.env"
RUNTIME_ENV="${ENV_DIR}/.env"
TMP_FILTERED_SECRETS="$(mktemp)"
TMP_RUNTIME_ENV="$(mktemp)"
PULL_RETRIES="${PULL_RETRIES:-3}"
PULL_RETRY_BACKOFF_SECONDS="${PULL_RETRY_BACKOFF_SECONDS:-15}"
HEALTH_RETRIES="${HEALTH_RETRIES:-12}"
HEALTH_RETRY_INTERVAL_SECONDS="${HEALTH_RETRY_INTERVAL_SECONDS:-3}"
MIN_DISK_AVAIL_GB="${MIN_DISK_AVAIL_GB:-2}"
MIN_MEM_AVAIL_MB="${MIN_MEM_AVAIL_MB:-256}"
REQUIRED_SERVICES=(postgres migrate backend scheduler web)

if [[ "$ENV" != "production" && "$ENV" != "staging" ]]; then
  echo "Error: environment must be 'production' or 'staging'" >&2
  exit 1
fi

if [[ "$ENV" == "production" ]]; then
  WEB_PORT=3000
  BACKEND_PORT=8000
  CADDY_HOST="collectivewill.org"
else
  WEB_PORT=3100
  BACKEND_PORT=8100
  CADDY_HOST="staging.collectivewill.org"
fi

check_ghcr_reachable() {
  local status
  status="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 https://ghcr.io/v2/ || true)"
  case "$status" in
    200|401|403|405)
      echo "==> GHCR reachability check: HTTP ${status} (ok)"
      ;;
    *)
      echo "Error: GHCR reachability check failed (status=${status:-none})." >&2
      return 1
      ;;
  esac
}

check_resource_headroom() {
  local disk_avail_kb min_disk_kb mem_avail_kb min_mem_kb

  disk_avail_kb="$(df -Pk "${ENV_DIR}" | awk 'NR==2 {print $4}')"
  min_disk_kb=$((MIN_DISK_AVAIL_GB * 1024 * 1024))
  if [[ -n "$disk_avail_kb" && "$disk_avail_kb" -lt "$min_disk_kb" ]]; then
    echo "Error: low disk headroom (${disk_avail_kb}KB available; need >= ${min_disk_kb}KB)." >&2
    return 1
  fi

  mem_avail_kb="$(awk '/MemAvailable/ {print $2}' /proc/meminfo 2>/dev/null || true)"
  min_mem_kb=$((MIN_MEM_AVAIL_MB * 1024))
  if [[ -n "$mem_avail_kb" && "$mem_avail_kb" -lt "$min_mem_kb" ]]; then
    echo "Error: low memory headroom (${mem_avail_kb}KB available; need >= ${min_mem_kb}KB)." >&2
    return 1
  fi

  echo "==> Resource headroom check passed"
}

check_compose_services() {
  local services expected
  services="$(docker compose config --services)"
  echo "==> Compose services:"
  echo "${services}"

  for expected in "${REQUIRED_SERVICES[@]}"; do
    if ! grep -qx "${expected}" <<< "${services}"; then
      echo "Error: required compose service '${expected}' missing." >&2
      return 1
    fi
  done
}

check_url_status() {
  local url="$1"
  shift
  curl -sS -o /dev/null -w "%{http_code}" --max-time 10 "$@" "${url}" || true
}

wait_for_healthy_url() {
  local label="$1"
  local url="$2"
  shift 2
  local status="" attempt=1

  while [[ "$attempt" -le "$HEALTH_RETRIES" ]]; do
    status="$(check_url_status "${url}" "$@")"
    if [[ "$status" =~ ^[23][0-9][0-9]$ ]]; then
      echo "==> Health check passed: ${label} (HTTP ${status})"
      return 0
    fi
    echo "==> Waiting for ${label} (attempt ${attempt}/${HEALTH_RETRIES}, status=${status:-none})"
    sleep "${HEALTH_RETRY_INTERVAL_SECONDS}"
    attempt=$((attempt + 1))
  done

  echo "Error: health check failed for ${label}; last status=${status:-none}" >&2
  return 1
}

pull_with_retry() {
  local attempt=1
  local sleep_for

  while [[ "$attempt" -le "$PULL_RETRIES" ]]; do
    echo "==> Pulling latest images (attempt ${attempt}/${PULL_RETRIES})..."
    if docker compose pull; then
      return 0
    fi

    if [[ "$attempt" -eq "$PULL_RETRIES" ]]; then
      echo "Error: docker compose pull failed after ${PULL_RETRIES} attempts." >&2
      return 1
    fi

    sleep_for=$((PULL_RETRY_BACKOFF_SECONDS * attempt))
    echo "==> Pull failed; retrying in ${sleep_for}s..."
    sleep "${sleep_for}"
    attempt=$((attempt + 1))
  done
}

cleanup() {
  rm -f "$TMP_FILTERED_SECRETS" "$TMP_RUNTIME_ENV"
}
trap cleanup EXIT

echo "==> Deploying ${ENV} with image tag: ${IMAGE_TAG}"

mkdir -p "${ENV_DIR}"

cp "${DEPLOY_SRC}/docker-compose.prod.yml" "${ENV_DIR}/docker-compose.yml"

if [[ ! -f "${PUBLIC_ENV}" ]]; then
  echo "Error: ${PUBLIC_ENV} not found. Ensure deploy/public.env.${ENV} is copied to the VPS." >&2
  exit 1
fi

SECRET_SOURCE=""
if [[ -f "${SECRETS_ENV}" ]]; then
  SECRET_SOURCE="${SECRETS_ENV}"
elif [[ -f "${LEGACY_ENV}" ]]; then
  SECRET_SOURCE="${LEGACY_ENV}"
  echo "==> Legacy mode: using ${LEGACY_ENV} as secret source"
  echo "==> Recommended: move secrets to ${SECRETS_ENV}"
else
  echo "Error: no secrets source found. Provide ${SECRETS_ENV} (preferred) or ${LEGACY_ENV}." >&2
  exit 1
fi

echo "==> Building merged runtime env at ${RUNTIME_ENV}"
awk -F= '
  FNR == NR {
    if ($0 ~ /^[[:space:]]*#/ || $0 ~ /^[[:space:]]*$/) next
    key = $1
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
    public_keys[key] = 1
    next
  }
  {
    if ($0 ~ /^[[:space:]]*#/ || $0 ~ /^[[:space:]]*$/) {
      print
      next
    }
    key = $1
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
    if (key in public_keys) {
      printf("Skipping duplicate key from secrets source: %s\n", key) > "/dev/stderr"
      next
    }
    print
  }
' "$PUBLIC_ENV" "$SECRET_SOURCE" > "$TMP_FILTERED_SECRETS"

{
  echo "# Autogenerated by deploy.sh (${ENV})"
  echo "# Public source: ${PUBLIC_ENV}"
  echo "# Secret source: ${SECRET_SOURCE}"
  echo
  cat "$PUBLIC_ENV"
  echo
  cat "$TMP_FILTERED_SECRETS"
} > "$TMP_RUNTIME_ENV"

install -m 600 "$TMP_RUNTIME_ENV" "$RUNTIME_ENV"

cd "${ENV_DIR}"

export IMAGE_TAG

echo "==> Preflight checks..."
check_resource_headroom
check_ghcr_reachable
check_compose_services

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

PULL_START=$(date +%s)
pull_with_retry
PULL_ELAPSED=$(( $(date +%s) - PULL_START ))
echo "==> Image pull completed in ${PULL_ELAPSED}s"

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

wait_for_healthy_url "web container on :${WEB_PORT}" "http://127.0.0.1:${WEB_PORT}/"
wait_for_healthy_url "backend openapi on :${BACKEND_PORT}" "http://127.0.0.1:${BACKEND_PORT}/openapi.json"

echo "==> Verifying Caddy routes..."
CADDY_HTTP_STATUS="$(check_url_status "http://${CADDY_HOST}/" --resolve "${CADDY_HOST}:80:127.0.0.1")"
CADDY_HTTPS_STATUS="$(check_url_status "https://${CADDY_HOST}/" --resolve "${CADDY_HOST}:443:127.0.0.1" -k)"
echo "==> Caddy HTTP (${CADDY_HOST}): ${CADDY_HTTP_STATUS}"
echo "==> Caddy HTTPS (${CADDY_HOST}): ${CADDY_HTTPS_STATUS}"

if [[ "$CADDY_HTTP_STATUS" == "000" || "$CADDY_HTTPS_STATUS" == "000" ]]; then
  echo "Error: Caddy is not responding on at least one route." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Post-deploy smoke tests — catch issues like the Telegram webhook 401 incident
# These are non-fatal warnings (deploy already succeeded) but surface problems
# immediately instead of waiting for the monitor timer to catch them.
# ---------------------------------------------------------------------------
echo "==> Running post-deploy smoke tests..."
SMOKE_FAILURES=0

# Smoke test 1: monitor-health endpoint (comprehensive health summary)
MONITOR_HEALTH="$(curl -sS --max-time 15 "http://127.0.0.1:${BACKEND_PORT}/ops/monitor-health" 2>/dev/null || true)"
if [[ -n "$MONITOR_HEALTH" ]]; then
  OVERALL_STATUS="$(echo "$MONITOR_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('overall_status','unknown'))" 2>/dev/null || echo "parse_error")"
  echo "==> Monitor health overall_status: ${OVERALL_STATUS}"
  if [[ "$OVERALL_STATUS" == "error" ]]; then
    echo "WARNING: monitor-health reports errors after deploy:" >&2
    echo "$MONITOR_HEALTH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for svc in data.get('services', []):
    if svc['status'] in ('error', 'degraded'):
        print(f\"  {svc['name']}: {svc['status']} — {svc.get('detail', '')}\")
" 2>/dev/null || echo "$MONITOR_HEALTH"
    SMOKE_FAILURES=$((SMOKE_FAILURES + 1))
  fi
else
  echo "WARNING: monitor-health endpoint unreachable" >&2
  SMOKE_FAILURES=$((SMOKE_FAILURES + 1))
fi

# Smoke test 2: Telegram webhook verification (if token is configured)
TG_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "${RUNTIME_ENV}" 2>/dev/null | cut -d= -f2- | sed 's/^"//;s/"$//' | head -1 || true)"
TG_SECRET="$(grep -E '^TELEGRAM_WEBHOOK_SECRET=' "${RUNTIME_ENV}" 2>/dev/null | cut -d= -f2- | sed 's/^"//;s/"$//' | head -1 || true)"
if [[ -n "$TG_TOKEN" ]]; then
  TG_INFO="$(curl -sS --max-time 10 "https://api.telegram.org/bot${TG_TOKEN}/getWebhookInfo" 2>/dev/null || true)"
  if [[ -n "$TG_INFO" ]]; then
    TG_URL="$(echo "$TG_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('url',''))" 2>/dev/null || true)"
    TG_ERROR="$(echo "$TG_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('last_error_message',''))" 2>/dev/null || true)"
    TG_PENDING="$(echo "$TG_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('pending_update_count',0))" 2>/dev/null || true)"
    EXPECTED_WEBHOOK_URL="$(grep -E '^APP_PUBLIC_BASE_URL=' "${RUNTIME_ENV}" 2>/dev/null | cut -d= -f2- | head -1 || true)"
    EXPECTED_WEBHOOK_URL="${EXPECTED_WEBHOOK_URL%/}/api/webhooks/telegram"

    echo "==> Telegram webhook URL: ${TG_URL:-<not set>}"
    echo "==> Telegram pending updates: ${TG_PENDING}"

    if [[ -z "$TG_URL" ]]; then
      echo "WARNING: Telegram webhook URL is not set!" >&2
      SMOKE_FAILURES=$((SMOKE_FAILURES + 1))
    elif [[ "$TG_URL" != "$EXPECTED_WEBHOOK_URL" ]]; then
      echo "WARNING: Telegram webhook URL mismatch! Expected: ${EXPECTED_WEBHOOK_URL}, Got: ${TG_URL}" >&2
      SMOKE_FAILURES=$((SMOKE_FAILURES + 1))
    fi

    if [[ -n "$TG_ERROR" ]]; then
      echo "WARNING: Telegram reports webhook error: ${TG_ERROR}" >&2
      SMOKE_FAILURES=$((SMOKE_FAILURES + 1))
    fi

    if [[ -n "$TG_SECRET" ]]; then
      echo "==> TELEGRAM_WEBHOOK_SECRET is configured (good)"
    else
      echo "WARNING: TELEGRAM_WEBHOOK_SECRET is not set — webhook requests are not verified" >&2
    fi
  fi
else
  echo "==> Telegram bot token not configured, skipping webhook smoke test"
fi

# Smoke test 3: verify recent backend logs have no repeated errors
RECENT_ERRORS="$(docker compose logs backend --tail=50 --no-color 2>/dev/null | grep -ci "error\|traceback\|exception" || true)"
if [[ "$RECENT_ERRORS" -gt 5 ]]; then
  echo "WARNING: ${RECENT_ERRORS} error-like lines in recent backend logs" >&2
  SMOKE_FAILURES=$((SMOKE_FAILURES + 1))
fi

if [[ "$SMOKE_FAILURES" -gt 0 ]]; then
  echo "==> SMOKE TEST: ${SMOKE_FAILURES} warning(s) detected — review above output"
else
  echo "==> SMOKE TEST: all checks passed"
fi

# ---------------------------------------------------------------------------
# Install ops monitor systemd timer (idempotent — safe to run every deploy)
# ---------------------------------------------------------------------------
MONITOR_SERVICE_SRC="${DEPLOY_SRC}/systemd/collective-will-monitor.service"
MONITOR_TIMER_SRC="${DEPLOY_SRC}/systemd/collective-will-monitor.timer"
MONITOR_SCRIPT_SRC="${DEPLOY_SRC}/monitor-ops.sh"
MONITOR_SCRIPT_DST="${DEPLOY_SRC}/scripts/monitor-ops.sh"

if [[ -f "$MONITOR_SERVICE_SRC" && -f "$MONITOR_TIMER_SRC" ]]; then
  echo "==> Installing ops monitor systemd timer..."

  # Ensure the scripts directory exists and the monitor script is executable
  mkdir -p "$(dirname "$MONITOR_SCRIPT_DST")"
  if [[ -f "$MONITOR_SCRIPT_SRC" ]]; then
    cp "$MONITOR_SCRIPT_SRC" "$MONITOR_SCRIPT_DST"
    chmod +x "$MONITOR_SCRIPT_DST"
  fi

  NEED_RELOAD=0
  if command -v sudo >/dev/null 2>&1; then
    sudo -n mkdir -p /var/lib/collective-will-monitor
    sudo -n chown "$(whoami):$(id -gn)" /var/lib/collective-will-monitor

    for unit_file in "$MONITOR_SERVICE_SRC" "$MONITOR_TIMER_SRC"; do
      unit_name="$(basename "$unit_file")"
      dest="/etc/systemd/system/${unit_name}"
      if ! sudo -n cmp -s "$unit_file" "$dest" 2>/dev/null; then
        sudo -n cp "$unit_file" "$dest"
        NEED_RELOAD=1
      fi
    done

    if [[ "$NEED_RELOAD" -eq 1 ]]; then
      sudo -n systemctl daemon-reload
    fi
    sudo -n systemctl enable collective-will-monitor.timer 2>/dev/null || true
    sudo -n systemctl start collective-will-monitor.timer 2>/dev/null || true
    echo "==> Ops monitor timer installed and running"
    systemctl is-active collective-will-monitor.timer 2>/dev/null && echo "==> Timer status: active" || echo "==> Timer status: check manually"
  else
    echo "==> sudo not available; install systemd units manually (see deploy/README.md)"
  fi
else
  echo "==> Monitor systemd units not found in deploy bundle, skipping"
fi

# ---------------------------------------------------------------------------
# Post-deploy notification email — confirms email pipeline works after deploy
# ---------------------------------------------------------------------------
ALERT_EMAILS="$(grep -E '^OPS_ALERT_EMAILS=' "${RUNTIME_ENV}" 2>/dev/null | cut -d= -f2- | head -1 || true)"
RESEND_KEY="$(grep -E '^RESEND_API_KEY=' "${RUNTIME_ENV}" 2>/dev/null | cut -d= -f2- | head -1 || true)"
EMAIL_FROM="$(grep -E '^EMAIL_FROM=' "${RUNTIME_ENV}" 2>/dev/null | cut -d= -f2- | head -1 || echo "ops@resend.dev")"
BACKEND_IMAGE="ghcr.io/civil-whisper/collective-will-backend:latest"

if [[ -n "$ALERT_EMAILS" && -n "$RESEND_KEY" ]]; then
  echo "==> Sending deploy notification email to ${ALERT_EMAILS}..."
  DEPLOY_TS="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  SMOKE_RESULT="all passed"
  if [[ "$SMOKE_FAILURES" -gt 0 ]]; then
    SMOKE_RESULT="${SMOKE_FAILURES} warning(s)"
  fi

  docker run --rm --network host \
    -e RESEND_API_KEY="${RESEND_KEY}" \
    -e EMAIL_FROM="${EMAIL_FROM}" \
    -e OPS_ALERT_EMAILS="${ALERT_EMAILS}" \
    -e DEPLOY_ENV="${ENV}" \
    -e DEPLOY_IMAGE_TAG="${IMAGE_TAG}" \
    -e DEPLOY_TIMESTAMP="${DEPLOY_TS}" \
    -e DEPLOY_SERVICES_RUNNING="${RUNNING}/${EXPECTED_RUNNING}" \
    -e DEPLOY_SMOKE_RESULT="${SMOKE_RESULT}" \
    "${BACKEND_IMAGE}" \
    uv run python -m src.ops.deploy_notify 2>/dev/null \
    && echo "==> Deploy notification email sent" \
    || echo "==> Deploy notification email failed (non-fatal)"
else
  echo "==> Skipping deploy notification (OPS_ALERT_EMAILS or RESEND_API_KEY not set)"
fi

echo "==> Deploy complete for ${ENV} (${RUNNING}/${EXPECTED_RUNNING} services running)"
