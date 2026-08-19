# Collective Will — New VPS Setup Runbook

**Audience**: an AI coding agent (or engineer) executing this end to end.
**Goal**: bring the Collective Will stack up on a brand-new Hetzner VPS and get
`staging.collectivewill.org` serving traffic.
**Written**: 2026-08-19
**Status 2026-08-19 evening**: server bootstrapped, staging containers running
on localhost, ops monitor timer installed. Public HTTPS is **blocked on DNS** —
Cloudflare A records still resolve to the old origin `195.246.231.210`, so
Let's Encrypt is failing against that IP. Do not keep retrying ACME until DNS
is grey-clouded to `5.75.158.200`.

This document is self-contained. You do not need any prior conversation context.
Read the whole thing before running anything.

### Next VPS move (automated)

Do **not** re-walk this 15-phase paste. After you can SSH to the new box as a
sudoer:

```bash
# 1. Create the VM at the provider. SSH as the admin user (sudo -n).
# 2. Grey-cloud DNS to the new IP (dashboard, or CLOUDFLARE_API_TOKEN):
CLOUDFLARE_API_TOKEN=... ./scripts/repoint-origin-dns.sh --ip NEW.IP --grey

# 3. Bootstrap + env + first deploy (refuses to run deploy.sh if DNS is wrong):
./scripts/provision-vps.sh --set-github-secrets admin@NEW.IP

# 4. After Caddy has certs:
CLOUDFLARE_API_TOKEN=... ./scripts/repoint-origin-dns.sh --ip NEW.IP --orange
# then SSL/TLS Full (strict) + Cloudflare-only firewall (IPv4 and IPv6)
```

`provision-vps.sh` does not create or destroy VMs and does not touch the
provider firewall. Day-to-day deploys stay on **Actions → Deploy**.

---

## 0. What this box actually is (read this)

This is **not** a blank dedicated Collective Will VPS.

| | |
|---|---|
| Hostname | `MehrVPS` |
| OS | Ubuntu **26.04** LTS |
| SSH | `mehrdad` (passwordless sudo) and `deploy` (scoped sudoers). Root SSH is off. |
| Already running | `postgres:16-alpine` on `127.0.0.1:5432` from `/srv/postgres` (other projects). Do not `docker compose down` that stack. |
| CW Postgres | compose-internal only (no host port). No clash with the existing 5432. |
| GHCR | `civil-whisper` is the GitHub **username**. Images pull anonymously. |

`ssh 5.75.158.200` is `mehrdad`. `ssh cw` is `deploy` (`~/.ssh/config` Host cw).

**Old VPS dump**: already taken. Clean staging install. Do not restore unless asked.

---

## 1. Situation

The project previously ran on a VPS at `195.246.231.210` (~€30/mo). That server was
dropped for cost reasons — the project has no traction yet and the spend wasn't
justified. A cheaper Hetzner box has replaced it. Your job is to stand the stack back
up there.

The CI/CD pipeline already exists and works. This is mostly **repointing** it and
recreating the server-side state that lives outside git. Two genuine bugs in the repo
block a fresh deploy; you fix those first.

### Target

| | |
|---|---|
| Provider | Hetzner Cloud |
| Type | CX23 — 2 shared vCPU, 4 GB RAM, 40 GB NVMe, 20 TB traffic |
| IP | `5.75.158.200` |
| OS | Ubuntu 22.04 or 24.04 (fresh) |
| Cost | ~€4/mo (was ~€30) |

4 GB matches what the spec asks for (`mvp-specification.md`: "4GB+ RAM VPS"). This is
not a capacity downgrade — the old box was the same class at 7× the price.

### Repo

| | |
|---|---|
| GitHub | `github.com/civil-whisper/collective-will` (public) |
| Local working copy | `/Users/mehrdad/wa/collective-will-code/collective-will` |
| Remote (via SSH alias) | `git@github-civil-whisper:civil-whisper/collective-will.git` |
| Branch | `main` |

> There is a **stale clone** at `/Users/mehrdad/wa/collective-will` — 21 commits,
> docs-only, remote points at a repo that now 404s. **Ignore it entirely.** Do not read
> it, do not commit to it.

### Stack

Python/FastAPI backend + Next.js web + PostgreSQL (pgvector) + a scheduler process,
behind Caddy on the host. Telegram is the live channel (WhatsApp/Evolution API is
deferred post-MVP and commented out of the production compose file). Voice verification
is offloaded to Modal, so it costs no RAM here. Alembic handles migrations. An ops
monitor runs on a systemd timer and emails alerts via Resend.

Images are built by GitHub Actions (`.github/workflows/ci.yml`) on push to `main` and
pushed to `ghcr.io/civil-whisper/collective-will-backend:latest` and
`...-web:latest`. **Nothing is ever built on the VPS** — a Next.js build on 2 shared
vCPUs would be miserable, and the 40 GB disk doesn't want the layers.

Deploys are triggered manually: **Actions → Deploy → Run workflow → staging|production**.
That workflow scp's a deploy bundle to the box and runs `deploy/deploy.sh <env> latest`.

### Two environments, one box

| | staging | production |
|---|---|---|
| Host | `staging.collectivewill.org` | `collectivewill.org` |
| Backend port | 8100 | 8000 |
| Web port | 3100 | 3000 |
| Dir | `/opt/collective-will/staging` | `/opt/collective-will/production` |
| Status | **the working environment** | not deployed; Caddy serves a 503 page |

**Bring up staging only.** Production is Phase 8 and needs a deliberate Caddyfile edit.

> ⚠️ **Do not run both simultaneously on this box.** Staging is ~1.7 GB; both together
> is ~3.4 GB and will thrash swap on 4 GB. When production goes live, either stop
> staging or move to a CX33.

---

## 2. Ground rules

1. **Verify before proceeding.** Every phase ends with a check. If a check fails, stop
   and diagnose — do not continue to the next phase.
2. **Never commit secrets.** `.env.secrets`, `voice-phrases.json`, and any `.env` are
   gitignored. Keep it that way. Never paste secret *values* into logs, commit
   messages, or output.
3. **Do not build images on the server.**
4. **Do not open app ports (8000/8100/3000/3100) to the internet.** Caddy reaches them
   over localhost. This matters — see the security note below.
5. **Ask the human before anything destructive**: `docker compose down -v`, dropping a
   database, force-pushing, deleting the old VPS.

### Security context you must know

`docs/agent-context/security/02-incident-report-and-rotation-guide.md` documents a real
incident: **2025-03-02, a Next.js RCE (CVE-2025-66478, React Server Components
protocol) was exploited on staging** and used to install an XMRig cryptominer. The
payload was written to `/app/.next/` and consumed ~2 CPU cores and ~2.3 GB RAM. The
attacker needed nothing but an HTTP request to the exposed web container, and had read
access to that container's environment variables.

On a 2 vCPU / 4 GB box, a repeat of that takes the whole machine down rather than
merely degrading it. This is why Phase 7 (memory limits, read-only web container) is
not optional busywork, and why the firewall rules in Phase 3 matter.

### Secrets are already handled

The human has a complete, populated `.env.secrets` at
`/Users/mehrdad/wa/collective-will-code/collective-will/.env.secrets` — 16 keys, all
set. `voice-phrases.json` is present too. **Nothing needs to be recovered from the old
server.** `scripts/push-env.sh` will ship these to the box in Phase 5.

---

## 3. Decision required from the human before you start

**Is there anything on the old VPS (`195.246.231.210`) worth keeping?**

The only thing there that exists nowhere else is the staging PostgreSQL database,
including the evidence hash-chain. That chain is append-only and is the project's
audit backbone; a fresh install writes a new genesis entry rather than continuing it.

- **Default assumption: no.** Staging data is test data, the repo has been dormant since
  2026-03-25, and `deploy/README.md` documents wiping staging deliberately. Proceed
  with a clean install.
- **If the human says yes**, and the box still answers, dump it before doing anything
  else:

  ```bash
  ssh deploy@195.246.231.210 <<'EOF'
  set -euo pipefail
  cd /opt/collective-will/staging
  mkdir -p ~/migration
  docker compose exec -T postgres \
    pg_dump -U collective --no-owner --no-acl collective_will \
    | gzip > ~/migration/staging_db_$(date +%Y%m%d).sql.gz
  docker compose exec -T postgres \
    psql -U collective collective_will \
    -c "COPY evidence_log TO STDOUT WITH CSV HEADER" \
    | gzip > ~/migration/evidence_$(date +%Y%m%d).csv.gz
  ls -lh ~/migration/
  EOF

  scp -r deploy@195.246.231.210:~/migration ./migration-backup
  gunzip -c migration-backup/staging_db_*.sql.gz | head -40   # eyeball it
  ```

  Restore instructions are in Phase 6.5. **A dump nobody has looked at is not a backup.**

Everything below assumes a clean install unless noted.

---

## 4. Phase 1 — Fix two repo bugs (do this first; both block deploy)

Work in `/Users/mehrdad/wa/collective-will-code/collective-will`.

### 1.1 `cw-apply-caddy` is referenced but doesn't exist

`.github/workflows/deploy.yml` line 45 sets `CADDY_APPLY="/usr/local/bin/cw-apply-caddy"`
and **hard-fails the deploy** if that file is missing or not executable. The script is
defined nowhere in the repo and is not mentioned in `deploy/README.md`. It only ever
worked because someone hand-created it on the old server — which is exactly the class of
knowledge that dies with a box.

Create `deploy/cw-apply-caddy`:

```bash
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
```

```bash
chmod +x deploy/cw-apply-caddy
```

The bootstrap script in Phase 2 installs this to `/usr/local/bin/cw-apply-caddy`.

### 1.2 `.env.secrets.example` is missing three required keys

The working `.env.secrets` contains three keys the template doesn't:

- `TELEGRAM_WEBHOOK_SECRET` — without it, webhook signature verification fails
- `VOICE_ENCRYPTION_KEY` — voice records are encrypted at rest with this
- `VOICE_EMBEDDING_ENDPOINT_URL` — the Modal endpoint

Anyone following `deploy/README.md` §4 ("copy the template, fill in real values") gets a
deploy that fails in two places with no obvious cause. Add them:

```bash
cat >> .env.secrets.example <<'EOF'

# --- Telegram webhook verification ---
# openssl rand -hex 32
TELEGRAM_WEBHOOK_SECRET=

# --- Voice verification ---
# Encrypts voice records at rest. NEVER rotate this on a database that already
# holds voice data — existing records become permanently unreadable.
VOICE_ENCRYPTION_KEY=
# Modal endpoint for voice embeddings
VOICE_EMBEDDING_ENDPOINT_URL=
EOF
```

Also mark `MISTRAL_API_KEY` and `WITNESS_API_KEY` as optional — they're in the template
but unset in practice, which reads as "you forgot something."

### 1.3 Stale IP references

`195.246.231.210` is hardcoded in usage examples in:

- `deploy/README.md` (the `push-env.sh` examples)
- `scripts/push-env.sh` (header comments)

Replace with `5.75.158.200`.

### 1.4 `deploy/README.md` opening claim is now false

It begins: *"Docker and the `deploy` user are already configured on the VPS with SSH key
access."* True of the old box, not the new one. Replace with a pointer to
`scripts/bootstrap-server.sh` (Phase 2), and add `cw-apply-caddy` to the one-time setup
section alongside the existing monitor-timer wrapper.

### ✅ Verify Phase 1

```bash
./scripts/ci-deploy.sh          # repo's own deploy-config validator
test -x deploy/cw-apply-caddy && echo "wrapper present and executable"
bash -n deploy/cw-apply-caddy && echo "wrapper syntax ok"
grep -c "195.246.231.210" deploy/README.md scripts/push-env.sh   # expect 0 0
```

Commit. **Push to `main`** — this triggers CI, which rebuilds and pushes fresh
`:latest` images to GHCR. You want that before the first deploy, since the existing
images are from March.

---

## 5. Phase 2 — Bootstrap the server

The box is a bare Ubuntu install, currently reachable as root from the whole internet
and being port-scanned as you read this. Harden it before anything else.

### 2.1 SSH key (on the human's Mac)

If the old deploy key still exists, reuse it — then the `VPS_SSH_KEY` GitHub secret
doesn't need to change. Otherwise:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/collective_will -C "collective-will-deploy"

cat >> ~/.ssh/config <<'EOF'

Host cw
    HostName 5.75.158.200
    User deploy
    IdentityFile ~/.ssh/collective_will
    IdentitiesOnly yes
EOF
```

### 2.2 Get root access to the new box

If the Hetzner server was created **without** an SSH key, root password login is on:

```bash
ssh-copy-id -i ~/.ssh/collective_will.pub root@5.75.158.200
```

If it was created **with** a key, you already have root access — skip this.

### 2.3 Create `scripts/bootstrap-server.sh`

Save this in the repo (it belongs in git — that's the whole lesson of the
`cw-apply-caddy` bug):

```bash
#!/usr/bin/env bash
#
# bootstrap-server.sh — prepare a fresh VPS to receive Collective Will deploys
#
# Target: fresh Ubuntu 22.04/24.04, Hetzner Cloud CX23 (2 vCPU / 4 GB / 40 GB)
# Run as: root, on the new server
#
#   scp scripts/bootstrap-server.sh root@5.75.158.200:/tmp/
#   ssh root@5.75.158.200 "bash /tmp/bootstrap-server.sh \
#       'ssh-ed25519 AAAA... deploy-key' collectivewill.org"
#
# Idempotent — safe to re-run.
# Leaves the box in exactly the state deploy/README.md assumes.
# Does NOT deploy the app; GitHub Actions does that.

set -euo pipefail

DEPLOY_USER="deploy"
SWAP_SIZE_GB=4
SSH_PUBKEY="${1:-}"
DOMAIN="${2:-collectivewill.org}"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root."
[[ -n "$SSH_PUBKEY" ]] || die "Usage: bootstrap-server.sh '<ssh-public-key>' [domain]"
[[ "$SSH_PUBKEY" == ssh-* ]] || die "Argument 1 doesn't look like an SSH public key."

export DEBIAN_FRONTEND=noninteractive

log "1/10  System packages"
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq ca-certificates curl gnupg ufw fail2ban unattended-upgrades \
                       debian-keyring debian-archive-keyring apt-transport-https \
                       jq htop ncdu git age postgresql-client

log "2/10  deploy user"
id "$DEPLOY_USER" &>/dev/null || adduser --disabled-password --gecos "" "$DEPLOY_USER"
usermod -aG sudo "$DEPLOY_USER"

install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
AUTH_KEYS="/home/$DEPLOY_USER/.ssh/authorized_keys"
touch "$AUTH_KEYS"
grep -qF "$SSH_PUBKEY" "$AUTH_KEYS" || echo "$SSH_PUBKEY" >> "$AUTH_KEYS"
chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH_KEYS"
chmod 600 "$AUTH_KEYS"

# NOTE: deliberately NOT granting blanket NOPASSWD sudo. The deploy pipeline needs
# exactly two privileged commands; both get their own sudoers entry in step 9.

log "3/10  SSH hardening"
cat > /etc/ssh/sshd_config.d/99-collective-will.conf <<'EOF'
PermitRootLogin no
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
  systemctl restart ssh 2>/dev/null || systemctl restart sshd
  warn "Root login and passwords now disabled. KEEP THIS SESSION OPEN until you"
  warn "have verified 'ssh $DEPLOY_USER@<ip>' works from another terminal."
else
  rm -f /etc/ssh/sshd_config.d/99-collective-will.conf
  die "sshd config test failed; reverted."
fi

log "4/10  Firewall"
ufw --force default deny incoming
ufw --force default allow outgoing
ufw allow 22/tcp  comment 'SSH'
ufw allow 80/tcp  comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
# App ports (8000/8100/3000/3100) intentionally NOT opened — Caddy uses localhost.

log "5/10  fail2ban"
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
systemctl enable --now fail2ban
systemctl restart fail2ban

log "6/10  Swap (${SWAP_SIZE_GB}G)"
# Hetzner images ship with no swap. The scheduler loads numpy/hdbscan and clustering
# runs are bursty; without swap a spike OOM-kills Postgres.
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

log "7/10  Docker"
if ! command -v docker &>/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
                         docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "$DEPLOY_USER"

# Unbounded json-file logs are the likeliest cause of a disk-full outage on 40 GB.
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "live-restore": true
}
EOF
systemctl enable --now docker
systemctl restart docker

log "8/10  Caddy"
if ! command -v caddy &>/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
fi

install -d -m 755 /etc/systemd/system/caddy.service.d
cat > /etc/systemd/system/caddy.service.d/override.conf <<EOF
[Service]
Environment="DOMAIN=${DOMAIN}"
EOF
systemctl daemon-reload

log "9/10  Privileged wrappers the deploy pipeline calls"
# Paste the contents of deploy/cw-apply-caddy here, or scp it up first:
#   scp deploy/cw-apply-caddy root@5.75.158.200:/usr/local/bin/cw-apply-caddy
if [[ -f /tmp/cw-apply-caddy ]]; then
  install -o root -g root -m 755 /tmp/cw-apply-caddy /usr/local/bin/cw-apply-caddy
else
  warn "/tmp/cw-apply-caddy not found — install it manually before deploying:"
  warn "  scp deploy/cw-apply-caddy root@HOST:/usr/local/bin/cw-apply-caddy"
  warn "  ssh root@HOST 'chmod 755 /usr/local/bin/cw-apply-caddy'"
fi

# Monitor timer installer — documented in deploy/README.md "Ops Monitoring"
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

# Scoped sudoers: these commands only.
cat > /etc/sudoers.d/collective-will <<'EOF'
deploy ALL=(root) NOPASSWD: /usr/local/bin/cw-apply-caddy
deploy ALL=(root) NOPASSWD: /usr/local/sbin/cw-install-monitor-timer.sh
deploy ALL=(root) NOPASSWD: /usr/bin/cmp -s /opt/collective-will/repo-deploy/Caddyfile /etc/caddy/Caddyfile
EOF
chmod 440 /etc/sudoers.d/collective-will
visudo -cf /etc/sudoers.d/collective-will

log "10/10  Application directories"
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 755 \
  /opt/collective-will \
  /opt/collective-will/production \
  /opt/collective-will/staging \
  /opt/collective-will/repo-deploy \
  /opt/collective-will/backups

log "Done"
IP="$(hostname -I | awk '{print $1}')"
cat <<EOF

  ip      : ${IP}
  memory  : $(free -h | awk '/^Mem:/  {print $2}')
  swap    : $(free -h | awk '/^Swap:/ {print $2}')
  disk    : $(df -h / | awk 'NR==2 {print $4}') free
  docker  : $(docker --version)
  caddy   : $(caddy version 2>/dev/null | head -1)
  domain  : ${DOMAIN}

  VERIFY from a second terminal BEFORE closing this root session.

EOF
```

### 2.4 Run it

```bash
cd /Users/mehrdad/wa/collective-will-code/collective-will
chmod +x scripts/bootstrap-server.sh

scp deploy/cw-apply-caddy       root@5.75.158.200:/tmp/
scp scripts/bootstrap-server.sh root@5.75.158.200:/tmp/

ssh root@5.75.158.200 \
  "bash /tmp/bootstrap-server.sh '$(cat ~/.ssh/collective_will.pub)' collectivewill.org"
```

### ✅ Verify Phase 2 — from a SECOND terminal, before closing the root session

```bash
ssh cw 'whoami; docker --version; free -h | grep -i swap; sudo -n /usr/local/bin/cw-apply-caddy; echo "rc=$?"'
```

Expect: `deploy`, a Docker version, ~4.0 Gi swap, and `cw-apply-caddy` exiting 1 with
`Missing /opt/collective-will/repo-deploy/Caddyfile`. **That failure is correct** — the
Caddyfile arrives with the first deploy. What you're proving is that `sudo -n` runs it
without prompting.

If SSH as `deploy` fails, fix it from the still-open root session. Hetzner Cloud Console
also has a web console as a last resort.

---

## 6. Phase 3 — Network: firewall and DNS

### 3.1 Hetzner Cloud Firewall

`ufw` runs on the machine; the Cloud Firewall runs at the network edge and drops traffic
before it costs you bandwidth. Use both.

Cloud Console → your server → Firewalls → Create:

| Direction | Protocol | Port | Source |
|---|---|---|---|
| Inbound | TCP | 22 | the human's IP, if static; else `0.0.0.0/0` |
| Inbound | TCP | 80 | Cloudflare IPv4 + IPv6 ranges |
| Inbound | TCP | 443 | Cloudflare IPv4 + IPv6 ranges |

Current Cloudflare ranges: https://www.cloudflare.com/ips/

Restricting 80/443 to Cloudflare is what makes origin hiding real — otherwise anyone
who learns the IP can bypass Cloudflare's WAF and hit the app directly. Given that the
March incident was a plain HTTP request to the web container, this is worth the ten
minutes.

### 3.2 DNS in Cloudflare

**Current (wrong):** `staging.collectivewill.org` still has an A record to
`195.246.231.210`. Let's Encrypt is hitting that dead origin and failing
(`tls: internal error` / Cloudflare 525).

**Do this in the Cloudflare dashboard, in this order:**

1. SSL/TLS → Overview → **Full** (not Full strict yet — no origin cert).
2. Turn **grey cloud (DNS only)** on `staging` and `@`.
3. Change both A records to `5.75.158.200`. Delete any leftover A record for
   `195.246.231.210`.
4. Wait until `dig +short staging.collectivewill.org` returns **only**
   `5.75.158.200`.
5. On the box: `sudo systemctl reload caddy` (or wait — it retries with backoff).
   Confirm `journalctl -u caddy` shows certificate obtained.
6. Then orange-cloud both records and set SSL/TLS to **Full (strict)**.

Do **not** restrict the Hetzner Cloud Firewall to Cloudflare IPs until step 6 —
Let's Encrypt must reach port 80/443 on the origin while grey-clouded.

IPv6: Hetzner assigned `2a01:4f8:1c18:72ad::1/64`. If you add Cloudflare-only
firewall rules, add **IPv6** Cloudflare ranges too, or IPv6 stays world-open.

### ✅ Verify Phase 3

```bash
dig +short staging.collectivewill.org      # Cloudflare IPs, not 5.75.158.200 — correct when proxied
curl -sI http://5.75.158.200               # should hang/refuse once the CF-only rule is on
```

---

## 7. Phase 4 — Repoint the pipeline

### 4.1 GitHub Actions secrets

Repo → Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `VPS_HOST` | `5.75.158.200` |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | private key contents (unchanged if reusing the old key) |

Optional repository **variable**: `API_BASE_URL` = `https://staging.collectivewill.org/api`

### 4.2 GHCR login on the box

The deploy pulls images from GHCR. The box needs credentials — a GitHub Personal Access
Token (classic) with **`read:packages` scope only**.

```bash
ssh cw
echo "$GITHUB_PAT" | docker login ghcr.io -u civil-whisper --password-stdin
```

Stored in `~/.docker/config.json`; survives reboots.

### 4.3 Push env config

From the repo root on the human's Mac:

```bash
./scripts/push-env.sh staging deploy@5.75.158.200
```

This merges `deploy/public.env.staging` (git-tracked, non-secret) with `.env.secrets`
(local, never committed), applies `deploy/.env.staging` overrides if present (there are
none), and ships the merged `.env`, raw `.env.secrets`, and `voice-phrases.json` to
`/opt/collective-will/staging/` with correct permissions (600 / 600 / 644).

### ✅ Verify Phase 4

```bash
ssh cw 'ls -la /opt/collective-will/staging/; docker login ghcr.io 2>&1 | tail -1'
```

Expect `.env` (600), `.env.secrets` (600), `voice-phrases.json` (644).

---

## 8. Phase 5 — First deploy

**GitHub → Actions → Deploy → Run workflow → environment: `staging`**

The workflow scp's the deploy bundle to `/opt/collective-will/repo-deploy/`, applies the
Caddyfile via `cw-apply-caddy`, then runs `deploy/deploy.sh staging latest`.

`deploy.sh` preflights before pulling: GHCR reachability, ≥2 GB free disk, ≥256 MB free
memory, and that the compose file defines all of `postgres migrate backend scheduler web`.
It retries pulls 3× with backoff, then health-checks web/backend local ports and Caddy
host-header routing over both HTTP and HTTPS. It also auto-installs the ops monitor
systemd timer via the wrapper from Phase 2.

Migrations run automatically — the `migrate` service runs `alembic upgrade head` and
`backend`/`scheduler` wait on it completing successfully.

### ✅ Verify Phase 5

```bash
curl -s https://staging.collectivewill.org/api/health
ssh cw 'cd /opt/collective-will/staging && docker compose ps'
ssh cw 'cd /opt/collective-will/staging && docker compose logs --tail=50 backend'
ssh cw 'systemctl list-timers collective-will-monitor.timer'
ssh cw 'free -h && df -h /'
```

Expect 5 services (`postgres`, `backend`, `scheduler`, `web` running; `migrate` exited 0),
memory around 1.7–2.0 GB used, disk well under 40 GB.

`deploy.sh` also sends a deploy notification email to `OPS_ALERT_EMAILS` using the
backend image — if that arrives, the Resend pipeline works end to end. If it doesn't,
email alerting is broken and the monitor will be silent when it matters.

### 5.5 Only if restoring a dump from §3

```bash
scp migration-backup/staging_db_*.sql.gz cw:~/
ssh cw
cd /opt/collective-will/staging
docker compose stop backend scheduler web
gunzip -c ~/staging_db_*.sql.gz | docker compose exec -T postgres psql -U collective -d collective_will
docker compose start backend scheduler web
docker compose exec -T postgres psql -U collective collective_will -c \
  "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM evidence_log;"
```

Then run the app's own chain verification via the ops console — a row count does not
prove the hashes still link.

> If restoring, **do not rotate `VOICE_ENCRYPTION_KEY`**: voice records in the dump are
> encrypted with it and a new key makes them permanently unreadable. `DB_PASSWORD` is
> safe to change (a logical dump carries no role password) as long as `DATABASE_URL` in
> `.env.secrets` is updated to match before you push it.

---

## 9. Phase 6 — Functional verification

Don't declare success on green containers. Walk the actual user path.

```bash
# Telegram token valid and webhook pointed at this server
./scripts/check-telegram.sh "$TELEGRAM_BOT_TOKEN"
```

The webhook URL (`https://staging.collectivewill.org/api/webhooks/telegram`) is unchanged
by the move, so it should still be correct — the hostname just resolves to a new IP. If
`getWebhookInfo` shows it empty, wrong, or carrying a `last_error_message`:

```bash
./scripts/register-telegram-webhook.sh "$TELEGRAM_BOT_TOKEN" "https://staging.collectivewill.org"
```

Then, by hand in Telegram:

1. Message the bot, submit an issue → confirm it's accepted
2. `ssh cw 'cd /opt/collective-will/staging && docker compose logs --tail=30 backend'` →
   confirm the webhook arrived
3. Wait for the pipeline (staging runs `PIPELINE_INTERVAL_HOURS=0.1`, i.e. every 6
   minutes) → confirm canonicalization and clustering ran
4. Vote on a cluster → confirm it records
5. `curl -s https://staging.collectivewill.org/api/ops/monitor-health | jq`

If buttons in the bot do nothing, that's the webhook — see `deploy/README.md`
troubleshooting.

---

## 10. Phase 7 — Harden for 4 GB

Not optional, given the March incident. Edit `deploy/docker-compose.prod.yml`, commit,
redeploy.

### 7.1 Memory limits

The miner took ~2 cores and 2.3 GB. On this box that's everything. Limits turn "site
down" into "one container restarts."

```yaml
  web:
    deploy:
      resources:
        limits:
          memory: 512M
  backend:
    deploy:
      resources:
        limits:
          memory: 800M
  scheduler:
    deploy:
      resources:
        limits:
          memory: 900M
```

### 7.2 Read-only web container

The payload was written to `/app/.next/` because the `nextjs` user could write there.
Remove that capability:

```yaml
  web:
    read_only: true
    tmpfs:
      - /tmp
      - /app/.next/cache
    security_opt:
      - no-new-privileges:true
```

Test on staging before production — Next.js standalone output occasionally wants another
writable path, which will show up immediately in the logs.

### 7.3 Postgres tuning for 4 GB

```yaml
  postgres:
    command: >
      postgres
      -c shared_buffers=512MB
      -c effective_cache_size=1536MB
      -c work_mem=16MB
      -c maintenance_work_mem=128MB
      -c max_connections=50
      -c random_page_cost=1.1
```

`random_page_cost=1.1` because the disk is NVMe — the default of 4.0 makes the planner
avoid index scans it should be using, which matters for pgvector similarity queries.

### 7.4 Disk hygiene

40 GB, roughly 17 GB at steady state. Docker log rotation is already set by the
bootstrap. Add after each deploy or as a weekly cron:

```bash
docker image prune -f
```

`deploy.sh` aborts below 2 GB free, so you get a loud failure rather than a corrupted
Postgres.

### ✅ Verify Phase 7

```bash
ssh cw 'docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"'
curl -s https://staging.collectivewill.org/api/health
```

---

## 11. Phase 8 — Production (only when staging is proven)

Production currently serves a static 503 maintenance page. Enabling it requires a
deliberate Caddyfile edit, and **you must not run both stacks at once on 4 GB**.

1. Stop staging: `ssh cw 'cd /opt/collective-will/staging && docker compose down'`
   (no `-v` — that would delete the data)
2. In `deploy/Caddyfile`, replace the `respond ... 503` block under `{$DOMAIN}` with the
   same `handle` / `reverse_proxy` routes as the staging block, using ports **8000/3000**
   instead of 8100/3100. Keep the `handle` + `uri strip_prefix /api` pattern —
   `handle_path` strips the entire matched prefix and breaks backend routing, and
   NextAuth routes under `/api/auth/*` must keep their full path.
3. `./scripts/push-env.sh production deploy@5.75.158.200`
4. Actions → Deploy → environment: `production`
5. Register the Telegram webhook against the production URL if using a separate bot.

Note `deploy/public.env.production` uses production-appropriate cadences
(`PIPELINE_INTERVAL_HOURS=6`, `VOTING_CYCLE_HOURS=48`, `MIN_CLUSTER_SIZE=5`) versus
staging's fast-feedback values — this is intentional, don't "fix" it.

---

## 12. Phase 9 — Backups

`deploy.sh` has no backup step. Before production carries real user data:

- Daily `pg_dump` plus a separate `evidence_log` CSV export
- **Encrypt client-side before upload** with `age` (installed by the bootstrap). Now that
  the host provider verifies identity, client-side encryption is what keeps backup
  *content* out of reach:
  ```bash
  ... | gzip | age -r age1yourpublickey > db_$(date +%F).sql.gz.age
  ```
  Keep the private key off the server.
- Off-site to a **different jurisdiction than Hetzner** — Backblaze B2 or rsync.net. Not
  Hetzner Storage Box: same provider, same account, same legal process.
- Enable Hetzner's own daily snapshots too (~€0.80/mo). Convenient for recovery, but
  same-jurisdiction — a complement, not a substitute.
- **Test a restore once, now**, while staging data is cheap to lose.

---

## 13. Phase 10 — Documentation debt

The move to Hetzner contradicts three documents. The project is built on auditability;
its own decision log shouldn't quietly disagree with reality.

| File | Change |
|---|---|
| `docs/infrastructure-guide.md` §2 | The "Hetzner — NOT for this project" section describes the live setup. Rewrite it as current, keeping Njalla/1984.is documented as the higher-privacy option. |
| `docs/mvp-specification.md` (v0 Frozen Decisions, ~L102-103, L1238-1244) | "Hosting: Njalla or 1984.is, not Hetzner" is now false. Amend with a dated entry. |
| `docs/operational-security.md` (~L109-126, L273-297) | Same, plus the framing below. |

Append to the decision log:

```markdown
## Amendment 2026-08-19 — Hosting provider

**Was**: Njalla VPS (€30/mo), privacy-first hosting, v0 frozen decision.
**Now**: Hetzner CX23 (~€4/mo), identity-verified, Germany. IP 5.75.158.200.
**Why**: €30/mo is not justifiable pre-traction. Capacity unchanged (4 GB both).
**Accepted risk**: the posture is now *publicly anonymous, legally identifiable*.
Nobody browsing the site, running WHOIS, or scanning the IP learns who operates it;
a German court order does.
**Mitigations**: domain stays with Njalla (WHOIS unchanged); Cloudflare proxy with
origin restricted to Cloudflare ranges; encrypted off-site backups in a different
jurisdiction.
**Gate**: revisit before the pilot carries real Iranian user data at volume.
```

Keep the domain at Njalla regardless — it's ~$15/yr and it's the part of the privacy
story that protects users day to day.

---

## 14. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Deploy fails: `/usr/local/bin/cw-apply-caddy is missing` | Phase 1.1 / 2.3 not done | `scp deploy/cw-apply-caddy root@HOST:/usr/local/bin/` and `chmod 755` |
| Deploy fails: `Deploy user cannot run cw-apply-caddy non-interactively` | sudoers entry missing | Re-run bootstrap, or add `/etc/sudoers.d/collective-will` by hand |
| `docker compose pull` denied | GHCR not authenticated | Phase 4.2; PAT needs `read:packages` |
| Deploy aborts on low memory/disk | Preflight guard | `docker image prune -f`; check nothing else is running |
| 502 from Caddy | Backend not up | `docker compose logs backend`; check `migrate` exited 0 |
| Bot buttons do nothing | Telegram webhook wrong | `./scripts/check-telegram.sh`, then `register-telegram-webhook.sh` |
| Cert fails to issue | DNS still on old IP, orange-cloud + Full strict chicken-and-egg, or Cloudflare 525 | Grey-cloud A records to `5.75.158.200` first; watch `journalctl -u caddy`. Do not orange-cloud or Full (strict) until Caddy has a cert. |
| Postgres OOM-killed | No swap | Confirm the 4 GB swapfile is active |
| Site loads for you, not from Iran | Cloudflare or German IP filtering | Test with someone on the ground; see `docs/anonymity-and-decentralization.md` §2.5 for multi-TLD and `.onion` fallbacks |

Useful commands:

```bash
ssh cw 'cd /opt/collective-will/staging && docker compose ps'
ssh cw 'cd /opt/collective-will/staging && docker compose logs -f backend'
ssh cw 'sudo journalctl -u caddy -f'
ssh cw 'sudo journalctl -u collective-will-monitor.service --no-pager -n 30'
ssh cw 'cat /var/lib/collective-will-monitor/staging.json'
ssh cw 'docker stats --no-stream'
```

---

## 15. Master checklist

```
PHASE 1 — Repo fixes (blocks deploy)
  [ ] Create deploy/cw-apply-caddy, chmod +x
  [ ] Add 3 missing keys to .env.secrets.example
  [ ] Replace 195.246.231.210 in deploy/README.md and scripts/push-env.sh
  [ ] Fix deploy/README.md opening claim; document bootstrap + cw-apply-caddy
  [ ] ./scripts/ci-deploy.sh passes
  [ ] Commit and push to main (rebuilds :latest images — they're from March)

PHASE 2 — Server
  [ ] SSH keypair + ~/.ssh/config Host cw
  [ ] scp cw-apply-caddy and bootstrap-server.sh to /tmp
  [ ] Run bootstrap-server.sh as root
  [ ] Verify from a 2nd terminal: deploy user, docker, swap, sudo -n
  [ ] Close root session

PHASE 3 — Network
  [ ] Hetzner Cloud Firewall: 22 restricted, 80/443 Cloudflare-only
  [ ] Cloudflare A records @ and staging -> 5.75.158.200, proxied
  [ ] SSL/TLS mode: Full (strict)

PHASE 4 — Pipeline
  [ ] GitHub secret VPS_HOST = 5.75.158.200
  [ ] docker login ghcr.io on the box (PAT, read:packages)
  [ ] ./scripts/push-env.sh staging deploy@5.75.158.200
  [ ] Confirm .env 600, .env.secrets 600, voice-phrases.json 644

PHASE 5 — Deploy
  [ ] Actions -> Deploy -> staging
  [ ] /api/health returns OK
  [ ] 4 services running, migrate exited 0
  [ ] Monitor timer active
  [ ] Deploy notification email received

PHASE 6 — Functional
  [ ] check-telegram.sh clean
  [ ] Submit via bot -> lands in DB
  [ ] Pipeline runs -> cluster appears
  [ ] Vote records
  [ ] /api/ops/monitor-health all green

PHASE 7 — Hardening
  [ ] Memory limits on web/backend/scheduler
  [ ] read_only + tmpfs on web
  [ ] Postgres 4 GB tuning
  [ ] docker image prune after deploy

PHASE 8-10 — When ready
  [ ] Production Caddyfile + deploy (staging DOWN first)
  [ ] Encrypted off-site backups + restore test
  [ ] Amend the three hosting docs + decision record
```

---

## 16. Cost

| Item | Before | After |
|---|---|---|
| VPS | ~€30 | ~€4 |
| Domain (Njalla, amortized) | ~$1 | ~$1 |
| Hetzner snapshots | — | ~$1 |
| Off-site encrypted backup | ~$1 | ~$1 |
| Cloudflare + Let's Encrypt | free | free |
| LLM APIs + Modal | $5–15 | $5–15 |
| **Total** | **~$40–50/mo** | **~$12–23/mo** |

The LLM API is now the dominant line item, which is the right shape at this stage.
