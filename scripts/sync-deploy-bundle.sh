#!/usr/bin/env bash
# Copy the deploy bundle to a VPS, or materialize it locally for CI.
#
#   scripts/sync-deploy-bundle.sh deploy@5.75.158.200
#   scripts/sync-deploy-bundle.sh --prepare /tmp/repo-deploy
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy"
BUNDLE_LIST="${DEPLOY_DIR}/BUNDLE"
MONITOR_SRC="${REPO_ROOT}/scripts/monitor-ops.sh"
SECRETS_EXAMPLE="${REPO_ROOT}/.env.secrets.example"
VOICE_EXAMPLE="${REPO_ROOT}/voice-phrases.json.example"

usage() {
  echo "Usage: $0 <user@host> | --prepare <local-dir>" >&2
  exit 1
}

bundle_files() {
  grep -vE '^[[:space:]]*(#|$)' "$BUNDLE_LIST"
}

prepare_dir() {
  local dest="$1"
  rm -rf "$dest"
  mkdir -p "$dest/systemd"

  local rel
  while IFS= read -r rel; do
    [[ -f "${DEPLOY_DIR}/${rel}" ]] || {
      echo "Missing ${DEPLOY_DIR}/${rel}" >&2
      exit 1
    }
    install -m 644 "${DEPLOY_DIR}/${rel}" "${dest}/${rel}"
  done < <(bundle_files)

  chmod 755 "${dest}/deploy.sh" "${dest}/remote-entry.sh"
  [[ -f "${dest}/cw-apply-caddy" ]] && chmod 755 "${dest}/cw-apply-caddy"

  install -m 755 "$MONITOR_SRC" "${dest}/monitor-ops.sh"
  install -m 644 "$SECRETS_EXAMPLE" "${dest}/.env.secrets.example"
  if [[ -f "$VOICE_EXAMPLE" ]]; then
    install -m 644 "$VOICE_EXAMPLE" "${dest}/voice-phrases.json.example"
  fi
}

if [[ "${1:-}" == "--prepare" ]]; then
  [[ -n "${2:-}" ]] || usage
  prepare_dir "$2"
  echo "==> Bundle prepared at $2"
  exit 0
fi

REMOTE="${1:-}"
[[ -n "$REMOTE" && "$REMOTE" == *@* ]] || usage

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
prepare_dir "${TMP}/repo-deploy"

echo "==> Syncing deploy bundle to ${REMOTE}:/opt/collective-will/repo-deploy"
ssh "$REMOTE" "mkdir -p /opt/collective-will/repo-deploy/systemd"
# Contents into repo-deploy (not a nested repo-deploy/repo-deploy).
scp -q -r "${TMP}/repo-deploy/." "${REMOTE}:/opt/collective-will/repo-deploy/"
ssh "$REMOTE" "chmod +x /opt/collective-will/repo-deploy/deploy.sh /opt/collective-will/repo-deploy/remote-entry.sh /opt/collective-will/repo-deploy/monitor-ops.sh"
echo "==> Done"
