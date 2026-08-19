# VPS Deployment Setup

Remaining setup steps for GitHub Actions CI/CD after the server is bootstrapped.

**New box?** From the laptop, after you can SSH in with sudo:

```bash
./scripts/provision-vps.sh admin@NEW.IP
```

That runs `bootstrap-server.sh`, `push-env.sh`, copies the deploy bundle, and
runs the first deploy — but only if DNS already grey-clouded to that IP (Let's
Encrypt will otherwise fail). Details: `docs/VPS-SETUP-RUNBOOK.md`.

`bootstrap-server.sh` alone creates the `deploy` user, Docker log rotation,
Caddy, swap, and the root wrappers (`/usr/local/bin/cw-apply-caddy`,
`/usr/local/sbin/cw-install-monitor-timer.sh`) with scoped sudoers.

## Prerequisites

- Server bootstrapped (`scripts/bootstrap-server.sh`)
- A domain pointing to the VPS IP (A record for `yourdomain.com` and `staging.yourdomain.com`)

## 1. Export your existing SSH key as a GitHub Secret

You already have SSH key access to the VPS. Add the **private key** that
authenticates as the `deploy` user as a GitHub secret named `VPS_SSH_KEY`:

```bash
cat ~/.ssh/<your-deploy-key>
# Copy this output into GitHub → Settings → Secrets → Actions → VPS_SSH_KEY
```

## 2. Add all GitHub Secrets

Go to **GitHub repo → Settings → Secrets and variables → Actions** and add:

| Secret       | Value                                        |
| ------------ | -------------------------------------------- |
| `VPS_HOST`   | Your VPS IP address or hostname              |
| `VPS_USER`   | `deploy`                                     |
| `VPS_SSH_KEY` | Contents of the private key from step 1     |

`GITHUB_TOKEN` is provided automatically and gives GHCR push/pull access within the same repo.

Optionally add a **repository variable** (not secret):

| Variable         | Value                              |
| ---------------- | ---------------------------------- |
| `API_BASE_URL`   | e.g. `https://yourdomain.com/api`  |

## 3. Authenticate Docker on the VPS to pull from GHCR

SSH into the VPS as the deploy user and log in to GHCR. You need a GitHub
Personal Access Token (classic) with `read:packages` scope:

```bash
ssh deploy@YOUR_VPS_IP
echo "YOUR_GITHUB_PAT" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

The credentials are stored in `~/.docker/config.json` and persist across reboots.

## 4. Create environment directories and secrets

```bash
sudo mkdir -p /opt/collective-will/{production,staging,repo-deploy}
sudo chown -R deploy:deploy /opt/collective-will
```

Create `.env.secrets` files for each environment. Start from the repo-root
`.env.secrets.example` template and fill in real values. Most secrets (API keys)
are shared; only `DB_PASSWORD` and `WEB_ACCESS_TOKEN_SECRET` differ per environment:

```bash
# Copy the template for each environment
cp /opt/collective-will/repo-deploy/.env.secrets.example /opt/collective-will/production/.env.secrets
cp /opt/collective-will/repo-deploy/.env.secrets.example /opt/collective-will/staging/.env.secrets

# Edit each file — fill in API keys (shared) and per-env DB_PASSWORD / WEB_ACCESS_TOKEN_SECRET
nano /opt/collective-will/production/.env.secrets
nano /opt/collective-will/staging/.env.secrets
```

Secure the files:

```bash
chmod 600 /opt/collective-will/production/.env.secrets /opt/collective-will/staging/.env.secrets
```

### Pushing all env config to the VPS (preferred)

All VPS environment setup is done through `scripts/push-env.sh`. This is the
single entry point for getting config onto the server:

```bash
# From repo root — pushes merged .env, .env.secrets, and voice-phrases.json
./scripts/push-env.sh staging deploy@5.75.158.200
./scripts/push-env.sh production deploy@5.75.158.200
```

What it does:
1. Merges `deploy/public.env.<env>` (git-tracked) + `.env.secrets` (local, not committed)
2. Applies per-env overrides from `deploy/.env.<env>` if present
3. Pushes merged `.env` and raw `.env.secrets` to `/opt/collective-will/<env>/`
4. Pushes `voice-phrases.json` if present (required for voice verification)
5. Sets correct file permissions (600 for env files, 644 for voice phrases)

After pushing, deploy (via `deploy.sh` or GitHub Actions) will use these files.

To copy voice-phrases only (manual). Use `chmod 644` so the backend container (non-root) can read the mounted file:

```bash
scp voice-phrases.json deploy@YOUR_VPS:/opt/collective-will/production/voice-phrases.json
ssh deploy@YOUR_VPS "chmod 644 /opt/collective-will/production/voice-phrases.json"
```

During deploy, the workflow copies `deploy/public.env.production` and `deploy/public.env.staging`
from the repository to `/opt/collective-will/repo-deploy/`, and `deploy.sh` builds runtime
`/opt/collective-will/<env>/.env` by merging:
- public config from `public.env.<env>` (git-tracked, non-secret)
- secrets from `<env>/.env.secrets` (manual, from `.env.secrets.example` template)

If the same key exists in both files, the public value is kept and the duplicate in
`.env.secrets` is ignored with a warning in deploy logs.

For local development, `src/config.py` loads both `.env` (public) and `.env.secrets`
(secrets) automatically. See `.env.example` and `.env.secrets.example` for templates.

## 5. Install and configure Caddy

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Copy the Caddyfile and set your domain:

```bash
sudo cp /opt/collective-will/repo-deploy/Caddyfile /etc/caddy/Caddyfile
```

Edit `/etc/caddy/Caddyfile` and set the `DOMAIN` environment variable in the
Caddy systemd unit, or replace `{$DOMAIN}` with your actual domain:

```bash
sudo systemctl edit caddy
```

Add:

```ini
[Service]
Environment="DOMAIN=yourdomain.com"
```

Then reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart caddy
```

Caddy will automatically obtain TLS certificates from Let's Encrypt.

## 6. First deploy

Deploys are **manual**: GitHub → Actions → Deploy → Run workflow → `staging` or
`production`. Pushing to `main` only rebuilds GHCR images (`:latest`); it does
not deploy. Wait for the CI `build-backend` / `build-web` jobs to finish before
deploying, or you may pull a stale image.

```bash
curl -s https://staging.collectivewill.org/api/health
```

## Built-in Deploy Safeguards

`deploy/deploy.sh` now includes guard checks to reduce partial deploy risk:

- Preflight checks:
  - verifies compose has required services (`postgres`, `migrate`, `backend`, `scheduler`, `web`)
  - verifies GHCR reachability (`https://ghcr.io/v2/`)
  - verifies minimum disk and memory headroom
- Pull retries with backoff:
  - retries `docker compose pull` up to 3 times by default
- Post-deploy health checks:
  - verifies expected service count is running
  - verifies web/backend local ports respond
  - verifies Caddy host-header routing over both HTTP and HTTPS

The GitHub Actions workflow also skips Caddy apply when `deploy/Caddyfile`
has not changed, avoiding unnecessary Caddy reloads on app-only deploys.

### Post-deploy smoke tests

After all services are healthy, `deploy.sh` runs non-fatal smoke tests:

1. **Monitor health** — calls `/ops/monitor-health` and warns if any service reports `error`
2. **Telegram webhook** — calls Telegram's `getWebhookInfo` and checks:
   - Webhook URL matches `APP_PUBLIC_BASE_URL/api/webhooks/telegram`
   - No `last_error_message` from Telegram
   - `TELEGRAM_WEBHOOK_SECRET` is set
3. **Recent errors** — scans the last 50 backend log lines for error/traceback patterns

These tests do not fail the deploy (it already succeeded) but surface problems immediately
in the deploy output so you catch issues like the webhook 401 incident before waiting for
the monitoring timer.

### Optional tuning knobs

These environment variables can tune deploy behavior:

- `PULL_RETRIES` (default: `3`)
- `PULL_RETRY_BACKOFF_SECONDS` (default: `15`)
- `HEALTH_RETRIES` (default: `12`)
- `HEALTH_RETRY_INTERVAL_SECONDS` (default: `3`)
- `MIN_DISK_AVAIL_GB` (default: `2`)
- `MIN_MEM_AVAIL_MB` (default: `256`)

## Directory Layout (after first deploy)

```
/opt/collective-will/
├── repo-deploy/           # Deploy files copied by GitHub Actions
│   ├── docker-compose.prod.yml
│   ├── deploy.sh
│   ├── Caddyfile
│   ├── .env.secrets.example   # Template for secrets (from repo root)
│   ├── voice-phrases.json.example  # Template for voice phrase pool
│   ├── public.env.production
│   └── public.env.staging
├── production/
│   ├── docker-compose.yml # Copied from repo-deploy by deploy.sh
│   ├── .env.secrets       # Production secrets (from template, manual)
│   └── .env               # Runtime merged env (generated by deploy.sh)
└── staging/
    ├── docker-compose.yml # Copied from repo-deploy by deploy.sh
    ├── .env.secrets       # Staging secrets (from template, manual)
    └── .env               # Runtime merged env (generated by deploy.sh)
```

## Caddy Routing

**Production** currently serves a static 503 maintenance page since the
production stack is not deployed yet.  When production is ready, replace
the `respond` block in the `{$DOMAIN}` server block with the same
`handle`/`reverse_proxy` routes from the staging block (using ports
8000/3000 instead of 8100/3100).

**Staging** Caddyfile splits `/api/auth/*` between two services:

- **Backend** (FastAPI): `/api/auth/subscribe`, `/api/auth/verify/*`, `/api/auth/web-session`
- **Web** (NextAuth): everything else under `/api/auth/*` (session, callback, etc.)

All other `/api/*` routes go to the backend. Everything else goes to the web frontend.

**Important**: Use `handle` + `uri strip_prefix /api` (not `handle_path`) for backend
routes. `handle_path` strips the *entire* matched prefix, which breaks the backend
routing. The backend expects paths like `/auth/subscribe`, so only `/api` should be
stripped. NextAuth routes must keep their full `/api/auth/...` path.

## Resetting Staging Data (Volume Nuke)

To wipe all staging data (database, evidence chain) and start fresh:

```bash
cd /opt/collective-will/staging
docker compose down -v
docker compose up -d
```

The `-v` flag removes all Docker volumes including the PostgreSQL data.
The `migrate` service will recreate the schema on startup.
A fresh genesis entry will be created on the first evidence append.

**Never run this on production without explicit confirmation.**

## Checking Telegram (token and webhook)

To confirm the bot token is valid and the webhook is set (so Telegram sends updates to your server):

```bash
# From repo root — use your staging bot token
./scripts/check-telegram.sh "YOUR_BOT_TOKEN"

# Or with token in env (e.g. from .env.secrets)
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
./scripts/check-telegram.sh
```

The script calls Telegram’s `getMe` (validates token, prints bot username) and `getWebhookInfo` (shows current webhook URL). If the webhook is not set or points elsewhere, button clicks and messages will not reach your backend.

To set or update the webhook (e.g. for staging):

```bash
./scripts/register-telegram-webhook.sh "YOUR_BOT_TOKEN" "https://staging.collectivewill.org"
```

If you use `TELEGRAM_WEBHOOK_SECRET`, register the secret with Telegram when calling `setWebhook` (e.g. add `secret_token` as in the security doc) so the backend can verify webhook requests.

Unit tests for the Telegram webhook (with a fake token) live in `tests/test_api/test_webhooks.py`. There is no in-repo test that calls the real Telegram API to validate a token; use `scripts/check-telegram.sh` for that.

## Ops Monitoring (Email Alerts)

A lightweight monitor checks backend health every 5 minutes and sends email
alerts on failures plus a daily heartbeat when all is well.

### Configuration

Add `OPS_ALERT_EMAILS` to your `.env.secrets` on the VPS (it contains your email, so
it belongs with secrets, not in the git-tracked public env):

```bash
# In /opt/collective-will/staging/.env.secrets (and production)
OPS_ALERT_EMAILS=your-email@example.com
```

The other settings have sensible defaults in `public.env.<env>` and can be overridden:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPS_ALERT_EMAILS` | *(empty)* | Comma-separated recipient emails |
| `OPS_HEARTBEAT_HOUR_UTC` | `8` | UTC hour to send the daily "all OK" email |
| `OPS_MONITOR_LOOKBACK_MINUTES` | `10` | Window for counting recent errors |
| `OPS_ALERT_DEDUP_MINUTES` | `60` | Suppress repeat alerts for same issue |
| `RESEND_API_KEY` | — | Required for sending emails |
| `EMAIL_FROM` | `ops@resend.dev` | Sender address |

### Systemd timer installation (automatic)

The `deploy.sh` script automatically installs and enables the systemd timer on
every deploy by calling a root-owned wrapper script on the VPS:
`sudo -n /usr/local/sbin/cw-install-monitor-timer.sh`.

**Prerequisite (one-time)**: install the wrapper and allow the `deploy` user to
run only that script without a password:

```bash
sudo install -d -m 755 /usr/local/sbin

sudo tee /usr/local/sbin/cw-install-monitor-timer.sh >/dev/null <<'EOF'
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

sudo chown root:root /usr/local/sbin/cw-install-monitor-timer.sh
sudo chmod 755 /usr/local/sbin/cw-install-monitor-timer.sh

sudo tee /etc/sudoers.d/collective-will-monitor >/dev/null <<'EOF'
deploy ALL=(root) NOPASSWD: /usr/local/sbin/cw-install-monitor-timer.sh
EOF

sudo chmod 440 /etc/sudoers.d/collective-will-monitor
sudo visudo -cf /etc/sudoers.d/collective-will-monitor

sudo -n /usr/local/sbin/cw-install-monitor-timer.sh
```

### Deploy notification email

After every deploy, a notification email is sent to `OPS_ALERT_EMAILS` confirming:
- Environment and image tag
- Service count
- Smoke test results
- That the email delivery pipeline is working

This is sent using the backend Docker image, so it exercises the same code path
as the monitoring alerts. If you don't receive it, the email pipeline is broken.

### Verify

```bash
# Check timer status
systemctl list-timers collective-will-monitor.timer

# Run manually
sudo systemctl start collective-will-monitor.service
journalctl -u collective-will-monitor.service --no-pager -n 30

# View monitor state
cat /var/lib/collective-will-monitor/staging.json
```

### What it checks

- **API**: backend reachable via `/ops/monitor-health`
- **Database**: PostgreSQL health check
- **Telegram webhook**: active `getWebhookInfo` verification (URL match, pending updates, last error)
- **Scheduler**: heartbeat staleness
- **Email transport**: Resend API key presence
- **Recent errors/warnings**: from in-memory ops event buffer
- **Pipeline degradations**: from evidence log

## Troubleshooting

**Bot: clicking Submit or other buttons does nothing**  
Telegram is not sending updates to your server. Run `./scripts/check-telegram.sh <token>`. If the webhook is empty or wrong, run `./scripts/register-telegram-webhook.sh <token> <base-url>` so the webhook points at your backend (e.g. `https://staging.collectivewill.org/api/webhooks/telegram`). Then try the button again and check `docker compose logs backend --tail=50` for incoming webhook requests.

```bash
# Check running containers
cd /opt/collective-will/production && docker compose ps

# View logs
docker compose logs -f backend
docker compose logs -f web

# Check Caddy status
sudo systemctl status caddy
sudo journalctl -u caddy -f

# Manually pull and restart
docker compose pull && docker compose up -d
```
