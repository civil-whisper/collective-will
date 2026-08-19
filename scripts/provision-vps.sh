#!/usr/bin/env bash
# Bring Collective Will up on a reachable Ubuntu host.
#
# This does NOT create the cloud VM, destroy an old VM, or open a provider
# firewall — those stay in the cloud console (or hcloud/terraform if you add
# them later). It automates everything we can do over SSH from this repo.
#
#   scripts/provision-vps.sh mehrdad@5.75.158.200
#   scripts/provision-vps.sh --env staging --skip-deploy admin@203.0.113.10
#
# After bootstrap, day-to-day deploys stay on GitHub Actions
# (Actions → Deploy → staging). Point VPS_HOST at the new IP first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV="staging"
DOMAIN="collectivewill.org"
DEPLOY_USER="deploy"
PUBKEY_FILE="${HOME}/.ssh/id_ed25519.pub"
ADMIN=""
SKIP_BOOTSTRAP=0
SKIP_DEPLOY=0
SET_GITHUB_SECRETS=0
REPOINT_DNS=""
GITHUB_REPO="civil-whisper/collective-will"

usage() {
  cat <<'EOF'
Usage: provision-vps.sh [options] <admin@host>

  admin@host     SSH login that can sudo -n (the first user on a new VPS)

Options:
  --env staging|production   default: staging
  --domain NAME              default: collectivewill.org
  --deploy-user NAME         default: deploy
  --pubkey-file PATH         public key installed on the deploy user
  --skip-bootstrap           host already bootstrapped
  --skip-deploy              sync env + bundle only (no deploy.sh)
  --set-github-secrets       gh secret set VPS_HOST and VPS_USER
  --repoint-dns grey|orange  Cloudflare A records (needs CLOUDFLARE_API_TOKEN)
  -h, --help

Still manual after this script (unless the matching flag is used):
  - create the VM at the provider
  - Cloudflare DNS / SSL (or --repoint-dns)
  - provider firewall: 80/443 from Cloudflare IPv4 AND IPv6
  - GitHub secret VPS_SSH_KEY (only if the deploy key changed)
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="${2:-}"; shift 2 ;;
    --domain) DOMAIN="${2:-}"; shift 2 ;;
    --deploy-user) DEPLOY_USER="${2:-}"; shift 2 ;;
    --pubkey-file) PUBKEY_FILE="${2:-}"; shift 2 ;;
    --skip-bootstrap) SKIP_BOOTSTRAP=1; shift ;;
    --skip-deploy) SKIP_DEPLOY=1; shift ;;
    --set-github-secrets) SET_GITHUB_SECRETS=1; shift ;;
    --repoint-dns) REPOINT_DNS="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    --*) echo "Unknown option: $1" >&2; usage ;;
    *)
      if [[ -z "$ADMIN" ]]; then
        ADMIN="$1"
        shift
      else
        echo "Unexpected argument: $1" >&2
        usage
      fi
      ;;
  esac
done

[[ -n "$ADMIN" && "$ADMIN" == *@* ]] || usage
if [[ "$ENV" != "staging" && "$ENV" != "production" ]]; then
  echo "Error: --env must be staging or production" >&2
  exit 1
fi

HOST="${ADMIN#*@}"
DEPLOY_REMOTE="${DEPLOY_USER}@${HOST}"
PUBKEY="$(cat "$PUBKEY_FILE")"
[[ "$PUBKEY" == ssh-* ]] || {
  echo "Error: ${PUBKEY_FILE} does not look like an SSH public key" >&2
  exit 1
}

ORIGIN_IP="$HOST"
if [[ ! "$ORIGIN_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  ORIGIN_IP="$(ssh -o BatchMode=yes "$ADMIN" "hostname -I | awk '{print \$1}'")"
fi

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

ssh_admin() { ssh -o BatchMode=yes "$ADMIN" "$@"; }
ssh_deploy() { ssh -o BatchMode=yes "$DEPLOY_REMOTE" "$@"; }

log "Checking admin SSH + passwordless sudo on ${ADMIN}"
ssh_admin "sudo -n true && echo sudo_ok"

if [[ "$SKIP_BOOTSTRAP" -eq 0 ]]; then
  log "Bootstrap (packages, ${DEPLOY_USER} user, Caddy, swap, sudoers)"
  scp -q "${REPO_ROOT}/scripts/bootstrap-server.sh" "${ADMIN}:/tmp/bootstrap-server.sh"
  ssh_admin "sudo bash /tmp/bootstrap-server.sh $(printf '%q' "$PUBKEY") $(printf '%q' "$DOMAIN")"
else
  log "Skipping bootstrap"
fi

log "Checking ${DEPLOY_REMOTE}"
ssh_deploy "whoami && docker ps >/dev/null && sudo -n /usr/local/bin/cw-apply-caddy >/dev/null 2>&1 || true"

log "Pushing ${ENV} env + voice phrases"
"${SCRIPT_DIR}/push-env.sh" "$ENV" "$DEPLOY_REMOTE"

log "Syncing deploy bundle"
"${SCRIPT_DIR}/sync-deploy-bundle.sh" "$DEPLOY_REMOTE"

if [[ -n "$REPOINT_DNS" ]]; then
  log "Cloudflare DNS --${REPOINT_DNS} -> ${ORIGIN_IP}"
  "${SCRIPT_DIR}/repoint-origin-dns.sh" --ip "$ORIGIN_IP" "--${REPOINT_DNS}" --domain "$DOMAIN"
fi

wait_for_grey_dns() {
  local n=1
  while [[ "$n" -le 18 ]]; do
    local got
    got="$(dig +short "staging.${DOMAIN}" A | grep -E '^[0-9.]+$' | head -1 || true)"
    if [[ "$got" == "$ORIGIN_IP" ]]; then
      echo "$got"
      return 0
    fi
    echo "    waiting for DNS staging.${DOMAIN} -> ${ORIGIN_IP} (now: ${got:-<none>}) ${n}/18"
    sleep 10
    n=$((n + 1))
  done
  return 1
}

ORIGIN_A="$(dig +short "staging.${DOMAIN}" A | grep -E '^[0-9.]+$' | head -1 || true)"
log "DNS staging.${DOMAIN} A=${ORIGIN_A:-<none>} (need ${ORIGIN_IP} while grey-clouded)"

if [[ "$SKIP_DEPLOY" -eq 0 ]]; then
  if [[ "$ORIGIN_A" != "$ORIGIN_IP" ]]; then
    if [[ -n "$REPOINT_DNS" && "$REPOINT_DNS" == "grey" ]] && wait_for_grey_dns; then
      ORIGIN_A="$ORIGIN_IP"
    fi
  fi
  if [[ "$ORIGIN_A" != "$ORIGIN_IP" ]]; then
    echo ""
    echo "WARNING: staging.${DOMAIN} does not resolve to ${ORIGIN_IP} (got ${ORIGIN_A:-<none>})."
    echo "Let's Encrypt will fail (that is what blocked the 2026-08-19 move)."
    echo "Grey-cloud the A records to ${ORIGIN_IP}, then re-run:"
    echo "  ssh ${DEPLOY_REMOTE} /opt/collective-will/repo-deploy/remote-entry.sh ${ENV} latest"
    echo ""
    echo "Or: CLOUDFLARE_API_TOKEN=... $0 --skip-bootstrap --repoint-dns grey ${ADMIN}"
    exit 3
  fi
  log "Deploy ${ENV}"
  ssh_deploy "/opt/collective-will/repo-deploy/remote-entry.sh ${ENV} latest"
else
  log "Skipping deploy.sh (--skip-deploy)"
fi

if [[ "$SET_GITHUB_SECRETS" -eq 1 ]]; then
  log "Updating GitHub Actions secrets VPS_HOST / VPS_USER on ${GITHUB_REPO}"
  gh secret set VPS_HOST --repo "$GITHUB_REPO" --body "$ORIGIN_IP"
  gh secret set VPS_USER --repo "$GITHUB_REPO" --body "$DEPLOY_USER"
  echo "    VPS_SSH_KEY left unchanged. Update it only if you installed a new deploy key."
fi

cat <<EOF

Provision finished for ${ORIGIN_IP} (${ENV}).

Still check:
  curl -sS https://staging.${DOMAIN}/api/health
  ./scripts/check-telegram.sh
  Hetzner/Cloud firewall: 22 (you), 80/443 Cloudflare IPv4+IPv6 only
  After certs: orange-cloud + SSL Full (strict)
  Day-to-day: Actions → Deploy → ${ENV}

EOF
