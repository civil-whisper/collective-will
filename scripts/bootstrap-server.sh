#!/usr/bin/env bash
#
# bootstrap-server.sh — prepare a VPS to receive Collective Will deploys
#
# Target: Ubuntu 22.04/24.04/26.04. Safe to run on a box that already has
# Docker / fail2ban / ufw / an admin user. Does not deploy the app.
#
# Run as root (or: sudo bash ...):
#
#   scp scripts/bootstrap-server.sh deploy-host:/tmp/
#   ssh deploy-host "sudo bash /tmp/bootstrap-server.sh \
#       'ssh-ed25519 AAAA... deploy-key' collectivewill.org"
#
# Idempotent. Does NOT:
#   - lock out an existing admin user (e.g. mehrdad)
#   - apt-get upgrade (too risky on a living box)
#   - restart docker if other containers are already running
#
# Leaves the box in the state deploy/README.md assumes:
#   - deploy user with SSH + docker + systemd-journal
#   - scoped sudoers for cw-apply-caddy and the monitor-timer wrapper
#   - /opt/collective-will/{production,staging,repo-deploy,backups}
#   - Caddy with DOMAIN in the systemd unit, then restarted so it takes effect
#   - swap, ufw 22/80/443, docker log rotation

set -euo pipefail

DEPLOY_USER="deploy"
SWAP_SIZE_GB=4
SSH_PUBKEY="${1:-}"
DOMAIN="${2:-collectivewill.org}"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root (sudo bash $0 ...)."
[[ -n "$SSH_PUBKEY" ]] || die "Usage: bootstrap-server.sh '<ssh-public-key>' [domain]"
[[ "$SSH_PUBKEY" == ssh-* ]] || die "Argument 1 doesn't look like an SSH public key."

export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
log "1/10  System packages (no dist-upgrade)"
# ---------------------------------------------------------------------------
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg ufw fail2ban unattended-upgrades \
                       debian-keyring debian-archive-keyring apt-transport-https \
                       jq htop ncdu git age postgresql-client

# ---------------------------------------------------------------------------
log "2/10  ${DEPLOY_USER} user"
# ---------------------------------------------------------------------------
id "$DEPLOY_USER" &>/dev/null || adduser --disabled-password --gecos "" "$DEPLOY_USER"
# docker + journal access; NOT the sudo group (scoped sudoers only, below)
usermod -aG docker "$DEPLOY_USER" 2>/dev/null || true
getent group systemd-journal >/dev/null && usermod -aG systemd-journal "$DEPLOY_USER"

install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
AUTH_KEYS="/home/$DEPLOY_USER/.ssh/authorized_keys"
touch "$AUTH_KEYS"
grep -qF "$SSH_PUBKEY" "$AUTH_KEYS" || echo "$SSH_PUBKEY" >> "$AUTH_KEYS"
chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH_KEYS"
chmod 600 "$AUTH_KEYS"

# ---------------------------------------------------------------------------
log "3/10  SSH hardening (does not lock out existing admin users)"
# ---------------------------------------------------------------------------
cat > /etc/ssh/sshd_config.d/99-collective-will.conf <<'EOF'
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
X11Forwarding no
AllowAgentForwarding no
EOF

if sshd -t; then
  systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null \
    || systemctl restart ssh 2>/dev/null || systemctl restart sshd
else
  rm -f /etc/ssh/sshd_config.d/99-collective-will.conf
  die "sshd config test failed; reverted."
fi

# ---------------------------------------------------------------------------
log "4/10  Firewall"
# ---------------------------------------------------------------------------
ufw --force default deny incoming
ufw --force default allow outgoing
ufw allow 22/tcp  comment 'SSH'
ufw allow 80/tcp  comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
# App ports (8000/8100/3000/3100) intentionally NOT opened — Caddy uses localhost.

# ---------------------------------------------------------------------------
log "5/10  fail2ban"
# ---------------------------------------------------------------------------
if [[ ! -f /etc/fail2ban/jail.local ]]; then
  cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd

[sshd]
enabled  = true
port     = ssh
filter   = sshd
maxretry = 3
EOF
fi
systemctl enable --now fail2ban
systemctl restart fail2ban

# ---------------------------------------------------------------------------
log "6/10  Swap (${SWAP_SIZE_GB}G)"
# ---------------------------------------------------------------------------
if swapon --show | grep -q '/swapfile'; then
  echo "    swapfile already active"
else
  fallocate -l "${SWAP_SIZE_GB}G" /swapfile \
    || dd if=/dev/zero of=/swapfile bs=1M count=$((SWAP_SIZE_GB*1024)) status=none
  chmod 600 /swapfile
  mkswap -q /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
cat > /etc/sysctl.d/99-collective-will.conf <<'EOF'
vm.swappiness = 10
vm.vfs_cache_pressure = 50
EOF
sysctl -q --system

# ---------------------------------------------------------------------------
log "7/10  Docker"
# ---------------------------------------------------------------------------
if ! command -v docker &>/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
                         docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "$DEPLOY_USER"

cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "live-restore": true
}
EOF

RUNNING_CTN="$(docker ps -q 2>/dev/null | wc -l | tr -d ' ')"
if [[ "${RUNNING_CTN}" -gt 0 ]]; then
  warn "Docker containers are running — not restarting the daemon."
  warn "daemon.json (log rotation + live-restore) applies on the next docker restart."
else
  systemctl enable --now docker
  systemctl restart docker
fi

# ---------------------------------------------------------------------------
log "8/10  Caddy"
# ---------------------------------------------------------------------------
install_caddy_from_repo() {
  local suite="$1"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  # Cloudsmith's list uses the host codename; Ubuntu 26.04 (resolute) may not
  # exist yet. Caller can rewrite the suite after this if apt update fails.
  if [[ -n "$suite" ]]; then
    sed -i "s/$(. /etc/os-release && echo "$VERSION_CODENAME")/${suite}/g" \
      /etc/apt/sources.list.d/caddy-stable.list 2>/dev/null || true
  fi
  apt-get update -qq
  apt-get install -y -qq caddy
}

if ! command -v caddy &>/dev/null; then
  if ! install_caddy_from_repo ""; then
    warn "Caddy repo rejected this Ubuntu release; retrying with noble"
    install_caddy_from_repo "noble"
  fi
fi

install -d -m 755 /etc/systemd/system/caddy.service.d
cat > /etc/systemd/system/caddy.service.d/override.conf <<EOF
[Service]
Environment="DOMAIN=${DOMAIN}"
EOF
systemctl daemon-reload
systemctl enable caddy
# restart (not reload) so the running process picks up DOMAIN
systemctl restart caddy
echo "    DOMAIN=${DOMAIN}"

# ---------------------------------------------------------------------------
log "9/10  Privileged wrappers the deploy pipeline calls"
# ---------------------------------------------------------------------------
cat > /usr/local/bin/cw-apply-caddy <<'EOF'
#!/usr/bin/env bash
# Install the repo Caddyfile and reload Caddy. Root-owned; the deploy user may
# run ONLY this, via sudoers. Validates before applying so a bad Caddyfile
# cannot take the site down.
set -euo pipefail

SRC="/opt/collective-will/repo-deploy/Caddyfile"
DST="/etc/caddy/Caddyfile"

[[ -f "$SRC" ]] || { echo "Missing $SRC" >&2; exit 1; }

DOMAIN="$(systemctl show caddy -p Environment --value | tr ' ' '\n' \
          | sed -n 's/^DOMAIN=//p')"
[[ -n "$DOMAIN" ]] || { echo "DOMAIN not set in the caddy unit" >&2; exit 1; }

if ! DOMAIN="$DOMAIN" caddy validate --config "$SRC" --adapter caddyfile >/dev/null 2>&1; then
  echo "ERROR: Caddyfile failed validation; not applying." >&2
  DOMAIN="$DOMAIN" caddy validate --config "$SRC" --adapter caddyfile >&2 || true
  exit 1
fi

if [[ -f "$DST" ]] && cmp -s "$SRC" "$DST"; then
  echo "==> Caddyfile unchanged"
  exit 0
fi

cp -f "$DST" "${DST}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
install -o root -g root -m 644 "$SRC" "$DST"

if systemctl reload caddy; then
  echo "==> Caddy reloaded"
else
  echo "ERROR: reload failed; restoring previous Caddyfile" >&2
  LATEST_BAK="$(ls -1t ${DST}.bak.* 2>/dev/null | head -1 || true)"
  [[ -n "$LATEST_BAK" ]] && install -m 644 "$LATEST_BAK" "$DST" && systemctl reload caddy
  exit 1
fi
EOF
chown root:root /usr/local/bin/cw-apply-caddy
chmod 755 /usr/local/bin/cw-apply-caddy

cat > /usr/local/sbin/cw-install-monitor-timer.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_DEPLOY_DIR="/opt/collective-will/repo-deploy"
SERVICE_SRC="$REPO_DEPLOY_DIR/systemd/collective-will-monitor.service"
TIMER_SRC="$REPO_DEPLOY_DIR/systemd/collective-will-monitor.timer"
MONITOR_SCRIPT_SRC="$REPO_DEPLOY_DIR/monitor-ops.sh"
MONITOR_SCRIPT_DST="$REPO_DEPLOY_DIR/scripts/monitor-ops.sh"
STATE_DIR="/var/lib/collective-will-monitor"

[[ -f "$SERVICE_SRC" ]] || { echo "Missing $SERVICE_SRC" >&2; exit 1; }
[[ -f "$TIMER_SRC" ]] || { echo "Missing $TIMER_SRC" >&2; exit 1; }
[[ -f "$MONITOR_SCRIPT_SRC" ]] || { echo "Missing $MONITOR_SCRIPT_SRC" >&2; exit 1; }

install -d -o deploy -g deploy -m 755 "$STATE_DIR"
install -d -o deploy -g deploy -m 755 "$(dirname "$MONITOR_SCRIPT_DST")"
install -o deploy -g deploy -m 755 "$MONITOR_SCRIPT_SRC" "$MONITOR_SCRIPT_DST"

install -o root -g root -m 644 "$SERVICE_SRC" /etc/systemd/system/collective-will-monitor.service
install -o root -g root -m 644 "$TIMER_SRC" /etc/systemd/system/collective-will-monitor.timer

systemctl daemon-reload
systemctl enable collective-will-monitor.timer
systemctl restart collective-will-monitor.timer
systemctl is-active collective-will-monitor.timer
EOF
chown root:root /usr/local/sbin/cw-install-monitor-timer.sh
chmod 755 /usr/local/sbin/cw-install-monitor-timer.sh

cat > /etc/sudoers.d/collective-will <<'EOF'
deploy ALL=(root) NOPASSWD: /usr/local/bin/cw-apply-caddy
deploy ALL=(root) NOPASSWD: /usr/local/sbin/cw-install-monitor-timer.sh
deploy ALL=(root) NOPASSWD: /usr/bin/cmp -s /opt/collective-will/repo-deploy/Caddyfile /etc/caddy/Caddyfile
EOF
chmod 440 /etc/sudoers.d/collective-will
visudo -cf /etc/sudoers.d/collective-will

# ---------------------------------------------------------------------------
log "10/10  Application directories"
# ---------------------------------------------------------------------------
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 755 \
  /opt/collective-will \
  /opt/collective-will/production \
  /opt/collective-will/staging \
  /opt/collective-will/repo-deploy \
  /opt/collective-will/backups

# ---------------------------------------------------------------------------
log "Done"
# ---------------------------------------------------------------------------
IP="$(hostname -I | awk '{print $1}')"
cat <<EOF

  ip         : ${IP}
  os         : $(. /etc/os-release && echo "$PRETTY_NAME")
  memory     : $(free -h | awk '/^Mem:/  {print $2}')
  swap       : $(free -h | awk '/^Swap:/ {print $2}')
  disk free  : $(df -h / | awk 'NR==2 {print $4}')
  docker     : $(docker --version)
  compose    : $(docker compose version --short 2>/dev/null || echo '?')
  caddy      : $(caddy version 2>/dev/null | head -1)
  domain     : ${DOMAIN}
  ufw        : $(ufw status | head -1)
  fail2ban   : $(systemctl is-active fail2ban)

  VERIFY from a second terminal:

      ssh ${DEPLOY_USER}@${IP} \\
        'whoami && docker ps && free -h && sudo -n /usr/local/bin/cw-apply-caddy; echo rc=\$?'

  (cw-apply-caddy will exit 1 with "Missing .../Caddyfile" until the first
   deploy copies it up — that is expected. What matters is that sudo -n works.)

  STILL TO DO — see docs/VPS-SETUP-RUNBOOK.md:
    1. ./scripts/push-env.sh staging ${DEPLOY_USER}@${IP}
    2. GitHub secret VPS_HOST -> ${IP}
    3. DNS A records -> ${IP} (grey-cloud until Caddy has certs, then orange)
    4. Hetzner Cloud Firewall: 80/443 from Cloudflare IPv4 AND IPv6 ranges

EOF
