# Infrastructure Guide: Collective Will MVP

A practical guide for setting up and managing the infrastructure for Collective Will. Written for beginners.

> **⚠️ Safety First**: If you or any contributors have family in Iran or other sensitive countries, read the [Operational Security Guide](operational-security.md) BEFORE setting up infrastructure. Your standard credit card and identity should NOT be attached to this project.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Hosting Provider Setup](#2-hosting-provider-setup)
3. [Server Initial Setup](#3-server-initial-setup)
4. [Docker & Application Deployment](#4-docker--application-deployment)
5. [Domain, DNS & HTTPS](#5-domain-dns--https)
6. [Database Access](#6-database-access)
7. [Backups](#7-backups)
8. [Security Hardening](#8-security-hardening)
9. [Monitoring](#9-monitoring)
10. [Cost Summary](#10-cost-summary)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Architecture Overview

### What We're Building

```
                                    Internet
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  │
               Your Users      Telegram Bot API          │
                    │                  │                  │
                    └──────────────────┘                  │
                                       │                  │
                                       ▼                  │
                              ┌─────────────────┐        │
                              │   Cloudflare    │        │
                              │  (DNS + CDN +   │        │
                              │   DDoS + WAF)   │        │
                              │    ✅ ACTIVE     │        │
                              └────────┬────────┘        │
                                       │                  │
                                       ▼                  │
┌──────────────────────────────────────────────────────────────────┐
│                  1984.is VPS (Ubuntu 22.04)                      │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                      Docker Compose                         │ │
│  │                                                             │ │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────┐   │ │
│  │  │  Caddy  │  │   web   │  │ backend │  │  scheduler  │   │ │
│  │  │ :80/443 │─▶│ :3000   │  │  :8000  │  │   (cron)    │   │ │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────────┘   │ │
│  │       │                          │              │          │ │
│  │       │            ┌─────────────┴──────────────┘          │ │
│  │       │            ▼                                       │ │
│  │       │     ┌─────────────┐                                │ │
│  │       │     │  postgres   │                                │ │
│  │       │     │   :5432     │                                │ │
│  │       │     └─────────────┘                                │ │
│  │       │            │                                       │ │
│  │       │            ▼                                       │ │
│  │       │     /var/lib/postgresql/data (persistent)          │ │
│  └───────┴────────────────────────────────────────────────────┘ │
│                                                                  │
│  /backups → Off-server storage (Backblaze B2 or equivalent)      │
└──────────────────────────────────────────────────────────────────┘
```

### Why This Architecture

| Choice | Reason |
|--------|--------|
| **Single VPS** | Simple, sufficient for MVP scale (<1000 users) |
| **Docker Compose** | Reproducible deployments, easy updates, isolated services |
| **Njalla + 1984.is** | Njalla for domain privacy + 1984.is for VPS hosting |
| **Cloudflare** | Free DDoS protection, hides server IP, fast DNS — **active** (nameservers: `glen.ns.cloudflare.com`, `tani.ns.cloudflare.com`) |
| **PostgreSQL** | Mature, reliable, supports pgvector for embeddings |

### When to Scale Beyond This

This architecture handles:
- ~1,000 concurrent users
- ~10,000 submissions
- ~100 requests/second

Consider scaling when you hit these limits. Until then, keep it simple.

---

## 2. Hosting Provider Setup

### Choosing a Provider

**Use privacy-focused providers with explicit roles: Njalla for domain, 1984.is for VPS.** This is a v0 frozen decision.

The key protection is that **WHOIS shows the registrar, not you**. This requires using a privacy-focused provider. Credit card payment is fine.

| Provider | WHOIS Shows | Jurisdiction | Credit Card OK? | v0 Status |
|----------|-------------|--------------|-----------------|-----------|
| **Njalla** | "Njalla, Sweden" | Sweden | ✅ Yes | **Domain registrar** |
| **1984.is** | Privacy-protected | Iceland | ✅ Yes | **Default VPS host** |
| Hetzner | Your identity | Germany | ❌ Don't use | **Not for this project** |
| Regular registrar | Your name/address | Varies | ❌ Don't use | **Not for this project** |

**Why NOT Hetzner/DigitalOcean**: They verify your identity and that information is more easily discoverable. The privacy protection comes from the provider's model, not from payment method.

See [Operational Security Guide](operational-security.md) for the full risk framework.

---

### Default: 1984.is VPS (Required for This Project)

**Why 1984.is for hosting:**
- Privacy-focused hosting in Icelandic jurisdiction
- Aligned with v0 decision to separate domain privacy (Njalla) from VPS hosting
- Avoids standard identity-verified VPS providers
- **Credit card payment is fine** — crypto optional

| Plan | vCPU | RAM | Storage | Monthly |
|------|------|-----|---------|---------|
| 1GB | 1 | 1 GB | provider-dependent | provider-dependent |
| **4GB** | 2 | 4 GB | provider-dependent | provider-dependent |
| 8GB | 4 | 8 GB | provider-dependent | provider-dependent |

Provider pricing changes over time. Use the current 1984.is pricing page when provisioning.

**Alternative**: Njalla VPS (acceptable fallback if 1984.is provisioning is unavailable).

---

### Step-by-Step: Create 1984.is VPS (Recommended)

**Why 1984.is**: It aligns with the v0 hosting default while keeping a privacy-forward provider model. Credit card payment is fine — the privacy posture comes from provider choice, not payment method.

1. **Create 1984.is account** (via provider website)
   - Use pseudonymous email (ProtonMail recommended)
   - No identity verification required

2. **Register domain via Njalla** (recommended split):
   - Njalla owns the domain on your behalf
   - WHOIS shows Njalla, not you
   - Use this domain in DNS + TLS setup later

3. **Create VPS**:
   - Select a 4GB-class plan for MVP
   - Payment: **Credit card is fine** (crypto optional for extra layer)

4. **Access your VPS**:
   - 1984.is provides SSH access details
   - Connect: `ssh root@your-server-ip`

**Alternative**: If 1984.is is unavailable, use Njalla VPS temporarily and keep the same architecture.

---

### Hetzner VPS (NOT for this project — reference only)

> **⚠️ Do not use for Collective Will.** Hetzner requires real identity verification. Per [v0 Frozen Decisions](mvp-specification.md#v0-frozen-decisions), use Njalla or 1984.is. This section is preserved only as reference for other projects or future migration if threat model changes.

1. **Create account**: https://accounts.hetzner.com/signUp
   - ⚠️ Requires real identity for fraud prevention

2. **Add payment method**: Credit card or PayPal

3. **Create project**: 
   - Go to Cloud Console: https://console.hetzner.cloud
   - Click "New project" → Name it with a neutral name (not "collective-will")

4. **Create SSH key** (on your laptop):
   ```bash
   # Generate a secure SSH key
   ssh-keygen -t ed25519 -C "collective-will-server"
   
   # This creates:
   # ~/.ssh/id_ed25519       (private key - NEVER share)
   # ~/.ssh/id_ed25519.pub   (public key - upload to Hetzner)
   
   # View your public key
   cat ~/.ssh/id_ed25519.pub
   ```

5. **Add SSH key to Hetzner**:
   - In Cloud Console → Security → SSH Keys → Add SSH Key
   - Paste your public key content
   - Name it (e.g., "my-laptop")

6. **Create server**:
   - Click "Add Server"
   - Location: **Falkenstein** or **Helsinki** (EU)
   - Image: **Ubuntu 22.04**
   - Type: **CX32** (4 vCPU, 8 GB RAM)
   - SSH Key: Select your key
   - Name: `collective-will-prod`
   - Click "Create & Buy"

7. **Note your server IP**: Shown in the dashboard (e.g., `168.119.xxx.xxx`)

### First Connection

```bash
# Connect to your server
ssh root@YOUR_SERVER_IP

# If it works, you'll see Ubuntu welcome message
# If it fails, check your SSH key setup
```

---

## 3. Server Initial Setup

### Create Non-Root User

Running as root is dangerous. Create a regular user:

```bash
# On the server (as root)

# Create user
adduser deploy
# Set a strong password, skip other prompts (Enter through them)

# Give sudo access
usermod -aG sudo deploy

# Copy SSH key to new user
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Test: open NEW terminal and connect as deploy
# ssh deploy@YOUR_SERVER_IP
```

### Disable Root Login

After confirming `deploy` user works:

```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Find and change these lines:
PermitRootLogin no
PasswordAuthentication no

# Save (Ctrl+X, Y, Enter) and restart SSH
sudo systemctl restart sshd
```

### Configure Firewall

```bash
# Allow only necessary ports
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# Check status
sudo ufw status
```

### Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker dependencies
sudo apt install -y ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow your user to run Docker without sudo
sudo usermod -aG docker deploy

# Log out and back in for group change to take effect
exit
# ssh deploy@YOUR_SERVER_IP

# Verify Docker works
docker --version
docker compose version
```

### Set Up Automatic Security Updates

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
# Select "Yes" when prompted
```

---

## 4. Docker & Application Deployment

### Project Structure on Server

```bash
# Create application directory
mkdir -p ~/collective-will
cd ~/collective-will

# Create necessary directories
mkdir -p data/postgres
mkdir -p backups
mkdir -p certs
```

### Docker Compose Configuration

Create `docker-compose.yml`:

```bash
nano ~/collective-will/docker-compose.yml
```

```yaml
version: '3.8'

services:
  # Reverse proxy & HTTPS termination
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/letsencrypt:ro
    depends_on:
      - web
      - backend
    restart: unless-stopped

  # Next.js website
  web:
    build: ./web
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
      - NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
      - NEXTAUTH_URL=https://collectivewill.org
    depends_on:
      - backend
    restart: unless-stopped

  # Python backend (FastAPI)
  backend:
    build: .
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000
    environment:
      - DATABASE_URL=postgres://collective:${DB_PASSWORD}@postgres:5432/collective_will
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - EVOLUTION_API_URL=http://evolution:8080
      - EVOLUTION_API_KEY=${EVOLUTION_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    depends_on:
      - postgres
      - evolution
    restart: unless-stopped

  # Background job scheduler
  scheduler:
    build: .
    command: python -m src.scheduler
    environment:
      - DATABASE_URL=postgres://collective:${DB_PASSWORD}@postgres:5432/collective_will
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    depends_on:
      - postgres
    restart: unless-stopped

  # Evolution API (WhatsApp gateway — v0)
  # v0: Self-hosted Evolution API (no Meta approval needed)
  # v1: Migrate to official WhatsApp Business API when user count exceeds a few hundred
  #     or when stability/compliance requires it. Only whatsapp.py changes.
  evolution:
    image: atendai/evolution-api:latest
    environment:
      - AUTHENTICATION_API_KEY=${EVOLUTION_API_KEY}
      - DATABASE_ENABLED=false
    volumes:
      - ./data/evolution:/evolution/instances
    restart: unless-stopped

  # PostgreSQL database
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      - POSTGRES_USER=collective
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=collective_will
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    restart: unless-stopped
    # Not exposed to internet - only accessible within Docker network

volumes:
  postgres_data:
```

### Environment Variables

Create `.env` file (never commit this to git!):

```bash
nano ~/collective-will/.env
```

```bash
# Database
DB_PASSWORD=your_very_strong_password_here_min_32_chars

# Authentication
NEXTAUTH_SECRET=another_random_string_min_32_chars

# Messaging APIs
TELEGRAM_TOKEN=your_telegram_bot_token
EVOLUTION_API_KEY=your_evolution_api_key_here

# LLM API
ANTHROPIC_API_KEY=sk-ant-your-key-here
# Or: MISTRAL_API_KEY=your-mistral-key
```

Generate strong passwords:

```bash
# Generate random passwords
openssl rand -base64 32
```

### Nginx Configuration

Create `nginx.conf`:

```bash
nano ~/collective-will/nginx.conf
```

```nginx
events {
    worker_connections 1024;
}

http {
    # Redirect HTTP to HTTPS
    server {
        listen 80;
        server_name collectivewill.org www.collectivewill.org;
        return 301 https://$server_name$request_uri;
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name collectivewill.org www.collectivewill.org;

        ssl_certificate /etc/letsencrypt/live/collectivewill.org/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/collectivewill.org/privkey.pem;

        # Security headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;

        # Website
        location / {
            proxy_pass http://web:3000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
        }

        # API endpoints (Python backend)
        location /api/ {
            proxy_pass http://backend:8000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Webhook endpoints for messaging platforms
        location /webhook/ {
            proxy_pass http://backend:8000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

### Deploy Application

```bash
cd ~/collective-will

# Clone your repository (when ready)
# git clone https://github.com/yourusername/collective-will.git .

# Start services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f web
docker compose logs -f postgres
```

### Common Docker Commands

```bash
# Stop all services
docker compose down

# Restart a service
docker compose restart web

# Rebuild after code changes
docker compose build web
docker compose up -d web

# Enter a container (for debugging)
docker compose exec postgres psql -U collective collective_will

# View resource usage
docker stats
```

---

## 5. Domain, DNS & HTTPS

### Get a Domain

**Recommended registrars:**

| Registrar | Privacy | Price | Notes |
|-----------|---------|-------|-------|
| **Njalla** | Excellent | ~$15/yr | Privacy-focused, they own domain on your behalf |
| **Porkbun** | Good | ~$9/yr | WHOIS privacy included |
| **Namecheap** | Good | ~$10/yr | WHOIS privacy included |
| **Cloudflare** | Good | At-cost | No markup, but fewer TLDs |

For a privacy-sensitive project, consider **Njalla** (Swedish, privacy-first).

### Cloudflare DNS & CDN (ACTIVE)

Cloudflare is **active** for `collectivewill.org` (Free plan). Nameservers
`glen.ns.cloudflare.com` and `tani.ns.cloudflare.com` are set at Njalla.

**What Cloudflare provides (free tier):**
- DNS hosting
- DDoS protection + Bot Fight Mode
- CDN (faster page loads)
- Hides origin server IP from public
- Automatic HTTPS (edge certificates)

**Current DNS records (managed in Cloudflare):**
```
A   collectivewill.org   → VPS IP   (Proxied / orange cloud)
A   staging              → VPS IP   (Proxied / orange cloud)
MX  send                 → Resend SMTP (DNS only)
TXT resend_domainkey     → DKIM key (DNS only)
TXT send                 → SPF record (DNS only)
```

**Cloudflare settings applied:**
- SSL/TLS → Full (strict)
- SSL/TLS → Edge Certificates: Always Use HTTPS, Min TLS 1.2, TLS 1.3
- Caching → Cache Rule: bypass cache for `/api/*`
- Security → automated protection (always protected) + Bot Fight Mode
- Network → WebSockets enabled

**Caddy trusted proxy configuration:** The Caddyfile includes a global
`trusted_proxies static` block with all Cloudflare IPv4/IPv6 ranges plus
`trusted_proxies_strict` (right-to-left XFF parsing). This ensures
`{client_ip}` and `X-Forwarded-For` reflect the real visitor IP, not the
Cloudflare edge. See `deploy/Caddyfile`.

**Maintaining Cloudflare IP ranges:** Cloudflare publishes its ranges at
https://www.cloudflare.com/ips/. If they change, update the `trusted_proxies`
block in `deploy/Caddyfile` accordingly.

### Set Up HTTPS with Let's Encrypt

```bash
# Install Certbot
sudo apt install -y certbot

# Stop nginx temporarily
docker compose stop nginx

# Get certificate (replace with your domain)
sudo certbot certonly --standalone -d collectivewill.org -d www.collectivewill.org

# Certificates are saved to:
# /etc/letsencrypt/live/collectivewill.org/fullchain.pem
# /etc/letsencrypt/live/collectivewill.org/privkey.pem

# Copy to your project (or symlink)
sudo cp -rL /etc/letsencrypt/live/collectivewill.org ~/collective-will/certs/
sudo chown -R deploy:deploy ~/collective-will/certs/

# Start nginx
docker compose start nginx

# Set up auto-renewal
sudo crontab -e
# Add this line:
0 3 * * * certbot renew --quiet && docker compose -f /home/deploy/collective-will/docker-compose.yml restart nginx
```

---

## 6. Database Access

### Option 1: Direct Access via SSH

```bash
# SSH into server and use psql
ssh deploy@YOUR_SERVER_IP
docker compose exec postgres psql -U collective collective_will

# Run queries
SELECT COUNT(*) FROM submissions;
SELECT * FROM clusters ORDER BY approval_count DESC LIMIT 10;

# Exit
\q
```

### Option 2: SSH Tunnel + GUI Tool

This lets you use a nice GUI (TablePlus, DBeaver, pgAdmin) from your laptop:

```bash
# On your laptop, create SSH tunnel
ssh -L 5432:localhost:5432 deploy@YOUR_SERVER_IP -N

# Keep this terminal open
# Now connect your GUI tool to:
# Host: localhost
# Port: 5432
# User: collective
# Password: (from your .env file)
# Database: collective_will
```

**Recommended GUI tools:**
- **TablePlus** (Mac/Windows) - Clean, fast, $0 for basic use
- **DBeaver** (All platforms) - Free, full-featured
- **pgAdmin** (All platforms) - Official Postgres tool, web-based

### Option 3: Build Admin Dashboard

Add protected admin routes to your Next.js app:

```typescript
// apps/web/app/admin/page.tsx
// Password-protected dashboard showing:
// - Submission counts
// - Cluster overview
// - User statistics
// - Evidence log viewer
```

### Useful Queries

```sql
-- Recent submissions
SELECT id, created_at, raw_text, status 
FROM submissions 
ORDER BY created_at DESC 
LIMIT 20;

-- Cluster statistics
SELECT 
  c.id,
  c.summary,
  c.member_count,
  c.approval_count
FROM clusters c
ORDER BY c.approval_count DESC;

-- User activity
SELECT 
  DATE(created_at) as day,
  COUNT(*) as submissions
FROM submissions
GROUP BY DATE(created_at)
ORDER BY day DESC;

-- Evidence log integrity check
SELECT 
  COUNT(*) as total_entries,
  COUNT(DISTINCT hash) as unique_hashes,
  MIN(timestamp) as first_entry,
  MAX(timestamp) as last_entry
FROM evidence_log;
```

---

## 7. Backups

### Why Backups Matter

Your database contains:
- User submissions (irreplaceable)
- Voting history (audit trail)
- Evidence log (integrity chain)

**Losing this data = losing trust.**

### Backup Strategy

| Type | Frequency | Retention | Location |
|------|-----------|-----------|----------|
| **Database dump** | Daily | 30 days | Off-server storage |
| **Full server snapshot** | Weekly | 4 weeks | Provider snapshots (if available) |
| **Evidence log export** | Daily | Forever | Off-server + local |

### Set Up Automated Backups

**1. Create backup script:**

```bash
nano ~/collective-will/backup.sh
```

```bash
#!/bin/bash
set -e

# Configuration
BACKUP_DIR="/home/deploy/collective-will/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Create backup directory
mkdir -p $BACKUP_DIR

# Dump database
echo "Starting database backup..."
docker compose -f /home/deploy/collective-will/docker-compose.yml exec -T postgres \
  pg_dump -U collective collective_will | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Export evidence log separately (critical data)
echo "Exporting evidence log..."
docker compose -f /home/deploy/collective-will/docker-compose.yml exec -T postgres \
  psql -U collective collective_will -c "COPY evidence_log TO STDOUT WITH CSV HEADER" \
  | gzip > "$BACKUP_DIR/evidence_$DATE.csv.gz"

# Delete old backups
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "evidence_*.csv.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $DATE"
ls -lh $BACKUP_DIR | tail -5
```

```bash
chmod +x ~/collective-will/backup.sh
```

**2. Schedule daily backups:**

```bash
crontab -e
# Add:
0 4 * * * /home/deploy/collective-will/backup.sh >> /home/deploy/collective-will/backups/backup.log 2>&1
```

**3. Copy backups off-server:**

Option A: **Backblaze B2** (~$0.005/GB/month, privacy-compatible)

```bash
# Install rclone
curl https://rclone.org/install.sh | sudo bash

# Configure Backblaze
rclone config
# Follow prompts to add B2

# Add to backup script:
rclone sync $BACKUP_DIR b2:your-bucket-name/collective-will-backups/
```

### Test Restoring Backups

**Practice this BEFORE you need it:**

```bash
# Restore database from backup
gunzip -c backups/db_20260211_040000.sql.gz | docker compose exec -T postgres psql -U collective collective_will

# Verify data
docker compose exec postgres psql -U collective collective_will -c "SELECT COUNT(*) FROM submissions;"
```

### Provider Snapshots

If your hosting provider supports automatic server snapshots, enable them as an additional backup layer. Check Njalla/1984.is documentation for snapshot availability.

---

## 8. Security Hardening

### SSH Hardening

```bash
sudo nano /etc/ssh/sshd_config
```

Ensure these settings:
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
```

```bash
sudo systemctl restart sshd
```

### Install Fail2ban

Blocks IPs that try to brute-force login:

```bash
sudo apt install -y fail2ban

sudo nano /etc/fail2ban/jail.local
```

```ini
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
```

```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Check status
sudo fail2ban-client status sshd
```

### Docker Security

```bash
# Don't run containers as root (add to Dockerfiles)
USER node  # or appropriate non-root user

# Keep Docker updated
sudo apt update && sudo apt upgrade docker-ce -y
```

### Secrets Management

Never commit secrets to git:

```bash
# .gitignore should include:
.env
*.pem
*.key
certs/
```

Rotate secrets periodically:
- Database password: Every 6 months
- API keys: When suspected compromise
- SSH keys: Annually

### Security Checklist

- [ ] SSH key authentication only (no passwords)
- [ ] Non-root user for daily operations
- [ ] Firewall enabled (ufw)
- [ ] Fail2ban installed
- [ ] Automatic security updates enabled
- [ ] HTTPS everywhere
- [ ] Secrets not in git
- [ ] Backups tested
- [ ] Cloudflare DDoS protection

---

## 9. Monitoring

### Basic Uptime Monitoring

**Option 1: Uptime Kuma (self-hosted)**

```yaml
# Add to docker-compose.yml
uptime-kuma:
  image: louislam/uptime-kuma:1
  volumes:
    - ./data/uptime-kuma:/app/data
  ports:
    - "3001:3001"
  restart: unless-stopped
```

Access at `https://collectivewill.org:3001` (add firewall rule: `sudo ufw allow 3001/tcp`)

**Option 2: Healthchecks.io (hosted, free tier)**

1. Sign up at https://healthchecks.io
2. Create a check for each critical component
3. Add to your cron:
   ```bash
   # Ping healthchecks after backup completes
   curl -fsS -m 10 --retry 5 https://hc-ping.com/your-uuid-here
   ```

### Log Aggregation

View logs easily:

```bash
# All logs
docker compose logs -f

# Specific service
docker compose logs -f web --tail 100

# Search logs
docker compose logs web | grep -i error
```

For more advanced logging, consider:
- **Loki + Grafana** (self-hosted)
- **Papertrail** (hosted, free tier)

### Resource Monitoring

```bash
# Current resource usage
docker stats

# Disk usage
df -h

# Memory
free -h

# Set up alerts with simple script
```

Create `~/collective-will/check-resources.sh`:

```bash
#!/bin/bash
DISK_THRESHOLD=80
MEM_THRESHOLD=80

DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
MEM_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')

if [ $DISK_USAGE -gt $DISK_THRESHOLD ]; then
  echo "WARNING: Disk usage is ${DISK_USAGE}%"
  # Add notification (email, Slack, etc.)
fi

if [ $MEM_USAGE -gt $MEM_THRESHOLD ]; then
  echo "WARNING: Memory usage is ${MEM_USAGE}%"
fi
```

```bash
chmod +x ~/collective-will/check-resources.sh

# Run hourly
crontab -e
# Add:
0 * * * * /home/deploy/collective-will/check-resources.sh >> /home/deploy/collective-will/backups/resources.log 2>&1
```

---

## 10. Cost Summary

### Monthly Costs (MVP)

| Item | Provider | Cost |
|------|----------|------|
| VPS (4GB-class plan) | 1984.is | provider-dependent |
| LLM API | Anthropic/Mistral | $5-15 |
| Domain | Njalla | ~$1 (yearly÷12) |
| DNS/CDN | Cloudflare | Free |
| SSL Certificates | Let's Encrypt | Free |
| **Total** | | **~$40-50/month** |

### One-Time Costs

| Item | Cost |
|------|------|
| Domain registration | ~$10-15/year |
| Your time learning | Priceless 😄 |

### Cost Comparison

| Approach | Monthly Cost |
|----------|--------------|
| **This guide (1984.is VPS + Njalla domain + Cloudflare)** | provider-dependent |
| Hetzner + Cloudflare (no privacy protection) | ~$25 |
| AWS (comparable specs) | ~$80-150 |
| Heroku/Railway/Render | ~$50-100 |
| DigitalOcean | ~$60-80 |

---

## 11. Troubleshooting

### Common Issues

**"Connection refused" when accessing website:**
```bash
# Check if containers are running
docker compose ps

# Check nginx logs
docker compose logs nginx

# Check if ports are open
sudo ufw status
```

**"502 Bad Gateway":**
```bash
# Web app probably crashed
docker compose logs web

# Restart it
docker compose restart web
```

**Database connection errors:**
```bash
# Check postgres is running
docker compose logs postgres

# Check connection from within network
docker compose exec web ping postgres
```

**Out of disk space:**
```bash
# Check usage
df -h

# Clean Docker cache
docker system prune -a

# Check what's using space
du -sh /* | sort -h
```

**SSL certificate expired:**
```bash
# Renew manually
sudo certbot renew
docker compose restart nginx
```

### Getting Help

1. **Check logs first**: `docker compose logs [service]`
2. **Search the error**: Copy exact error message to Google
3. **DigitalOcean tutorials**: Best documentation for common tasks
4. **Stack Overflow**: For specific technical questions
5. **Your hosting provider's support** (Njalla, 1984.is)

### Emergency Recovery

If everything breaks:

1. **Create new VPS** from provider snapshot (if available)
2. **Or restore manually:**
   ```bash
   # New server setup (follow Section 3)
   # Clone repo
   # Copy .env from backup
   # Restore database from backup
   # docker compose up -d
   ```

---

## Quick Reference

### SSH Access
```bash
ssh deploy@YOUR_SERVER_IP
```

### Docker Commands
```bash
docker compose up -d          # Start all services
docker compose down           # Stop all services
docker compose logs -f        # View logs
docker compose restart web    # Restart specific service
docker compose exec postgres psql -U collective collective_will  # Database shell
```

### Backup Commands
```bash
~/collective-will/backup.sh   # Manual backup
ls -la ~/collective-will/backups/  # List backups
```

### Useful Paths
```
~/collective-will/            # Application root
~/collective-will/.env        # Secrets (never commit)
~/collective-will/data/       # Persistent data
~/collective-will/backups/    # Local backup copies
/etc/letsencrypt/             # SSL certificates
```

---

*This guide will be updated as the project evolves. Last updated: February 2026*
