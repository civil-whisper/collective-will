#!/usr/bin/env bash
# ci-deploy.sh — Local smoke tests for deploy configuration.
# Catches config drift that only surfaces on the VPS during deploy.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="${SCRIPT_DIR}/deploy"
ERRORS=0

err() { echo "FAIL: $1" >&2; ERRORS=$((ERRORS + 1)); }
ok()  { echo "  OK: $1"; }

echo "=== Deploy config validation ==="

# 1. Shell syntax check
if bash -n "${DEPLOY_DIR}/deploy.sh"; then
  ok "deploy.sh syntax"
else
  err "deploy.sh has syntax errors"
fi

# 2. docker-compose.prod.yml parses (warnings about missing env vars are expected locally)
COMPOSE_OUTPUT="$(docker compose -f "${DEPLOY_DIR}/docker-compose.prod.yml" config 2>&1 || true)"
if echo "$COMPOSE_OUTPUT" | grep -qi "error"; then
  err "docker-compose.prod.yml has errors"
else
  ok "docker-compose.prod.yml parses (env var warnings expected locally)"
fi

# 3. Every REQUIRED_SERVICES entry exists in compose
REQUIRED_SERVICES=(postgres migrate backend scheduler web)
COMPOSE_SERVICES="$(docker compose -f "${DEPLOY_DIR}/docker-compose.prod.yml" config --services 2>/dev/null || true)"

for svc in "${REQUIRED_SERVICES[@]}"; do
  if echo "$COMPOSE_SERVICES" | grep -qx "$svc"; then
    ok "service '${svc}' defined in compose"
  else
    err "service '${svc}' listed in REQUIRED_SERVICES but missing from compose"
  fi
done

# 4. DB name consistency — compose should use collective_will, not bare collective
if grep -qE 'POSTGRES_DB:\s*collective_will' "${DEPLOY_DIR}/docker-compose.prod.yml"; then
  ok "POSTGRES_DB is collective_will"
else
  err "POSTGRES_DB not set to collective_will in compose"
fi

# Check DATABASE_URL uses correct DB name
BAD_DB_URLS=$(grep -n 'DATABASE_URL' "${DEPLOY_DIR}/docker-compose.prod.yml" | grep -v 'collective_will' || true)
if [[ -z "$BAD_DB_URLS" ]]; then
  ok "All DATABASE_URL entries use collective_will"
else
  err "DATABASE_URL with wrong DB name: ${BAD_DB_URLS}"
fi

# 5. Public env file for staging exists
if [[ -f "${DEPLOY_DIR}/public.env.staging" ]]; then
  ok "public.env.staging exists"
else
  err "public.env.staging missing"
fi

# 6. Staging env references correct DB name (if it contains DATABASE_URL)
envfile="${DEPLOY_DIR}/public.env.staging"
if [[ -f "$envfile" ]]; then
  bad=$(grep 'DATABASE_URL' "$envfile" | grep -v 'collective_will' || true)
  if [[ -n "$bad" ]]; then
    err "public.env.staging has DATABASE_URL without collective_will: ${bad}"
  fi
fi

# 7. cw-apply-caddy exists, is executable, and has valid bash syntax
if [[ -x "${DEPLOY_DIR}/cw-apply-caddy" ]]; then
  ok "deploy/cw-apply-caddy is executable"
else
  err "deploy/cw-apply-caddy missing or not executable"
fi
if [[ -f "${DEPLOY_DIR}/cw-apply-caddy" ]] && bash -n "${DEPLOY_DIR}/cw-apply-caddy"; then
  ok "deploy/cw-apply-caddy syntax"
else
  err "deploy/cw-apply-caddy has syntax errors"
fi

# 8. VPS provision scripts
for script in \
  "${SCRIPT_DIR}/scripts/bootstrap-server.sh" \
  "${SCRIPT_DIR}/scripts/provision-vps.sh" \
  "${SCRIPT_DIR}/scripts/sync-deploy-bundle.sh" \
  "${SCRIPT_DIR}/scripts/repoint-origin-dns.sh" \
  "${DEPLOY_DIR}/remote-entry.sh"
do
  if bash -n "$script"; then
    ok "$(basename "$script") syntax"
  else
    err "${script} has syntax errors"
  fi
done

BUNDLE_LIST="${DEPLOY_DIR}/BUNDLE"
if [[ -f "$BUNDLE_LIST" ]]; then
  ok "deploy/BUNDLE exists"
  while IFS= read -r rel; do
    [[ -z "$rel" || "$rel" =~ ^# ]] && continue
    if [[ -f "${DEPLOY_DIR}/${rel}" ]]; then
      ok "bundle file ${rel}"
    else
      err "BUNDLE lists missing file: ${rel}"
    fi
  done < "$BUNDLE_LIST"
else
  err "deploy/BUNDLE missing"
fi

# 9. deploy.yml workflow exists, uses remote-entry, and has reasonable timeout
WORKFLOW="${SCRIPT_DIR}/.github/workflows/deploy.yml"
if [[ -f "$WORKFLOW" ]]; then
  ok "deploy.yml workflow exists"
  if grep -q 'remote-entry.sh' "$WORKFLOW"; then
    ok "deploy.yml invokes remote-entry.sh"
  else
    err "deploy.yml does not invoke remote-entry.sh"
  fi
  timeout_val=$(grep 'command_timeout' "$WORKFLOW" | head -1 | grep -oE '[0-9]+m' || true)
  if [[ -n "$timeout_val" ]]; then
    minutes="${timeout_val%m}"
    if [[ "$minutes" -ge 12 ]]; then
      ok "SSH timeout is ${timeout_val} (>= 12m)"
    else
      err "SSH timeout ${timeout_val} may be too short for image pulls"
    fi
  fi
else
  err "deploy.yml workflow not found"
fi

echo ""
if [[ "$ERRORS" -gt 0 ]]; then
  echo "=== ${ERRORS} error(s) found ==="
  exit 1
else
  echo "=== All deploy checks passed ==="
fi
