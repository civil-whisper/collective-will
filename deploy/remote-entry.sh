#!/usr/bin/env bash
# Run on the VPS by GitHub Actions and by scripts/provision-vps.sh.
# Applies the Caddyfile (if needed) then deploy.sh.
set -euo pipefail

ENV="${1:?Usage: remote-entry.sh <staging|production> [image-tag]}"
IMAGE_TAG="${2:-latest}"

CADDY_APPLY="/usr/local/bin/cw-apply-caddy"
CADDY_SRC="/opt/collective-will/repo-deploy/Caddyfile"
CADDY_DST="/etc/caddy/Caddyfile"
DEPLOY_SH="/opt/collective-will/repo-deploy/deploy.sh"

if [[ "$ENV" != "production" && "$ENV" != "staging" ]]; then
  echo "Error: environment must be 'staging' or 'production'" >&2
  exit 1
fi

if command -v sudo >/dev/null 2>&1 && sudo -n cmp -s "$CADDY_SRC" "$CADDY_DST"; then
  echo "==> Caddyfile unchanged; skipping caddy apply"
else
  if [[ ! -x "$CADDY_APPLY" ]]; then
    echo "ERROR: $CADDY_APPLY is missing or not executable." >&2
    echo "Run scripts/bootstrap-server.sh (or scripts/provision-vps.sh) on this host first." >&2
    exit 1
  fi

  if [[ "$(id -u)" -eq 0 ]]; then
    "$CADDY_APPLY"
  elif command -v sudo >/dev/null 2>&1 && sudo -n -l "$CADDY_APPLY" >/dev/null 2>&1; then
    sudo -n "$CADDY_APPLY"
  else
    echo "ERROR: Deploy user cannot run $CADDY_APPLY non-interactively." >&2
    exit 1
  fi
fi

chmod +x "$DEPLOY_SH"
"$DEPLOY_SH" "$ENV" "$IMAGE_TAG"
