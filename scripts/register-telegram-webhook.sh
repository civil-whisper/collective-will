#!/usr/bin/env bash
set -euo pipefail

# Register the Telegram bot webhook URL.
# Usage: ./scripts/register-telegram-webhook.sh [bot-token] [public-base-url] [webhook-secret]
#   If omitted, token is read from .env.secrets (TELEGRAM_BOT_TOKEN).
#   If base URL omitted, read from deploy/public.env.staging (APP_PUBLIC_BASE_URL).
#   If secret omitted, read from .env.secrets (TELEGRAM_WEBHOOK_SECRET).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_SECRETS="${REPO_ROOT}/.env.secrets"
PUBLIC_STAGING="${REPO_ROOT}/deploy/public.env.staging"

if [[ -z "${1:-}" ]] && [[ -f "$ENV_SECRETS" ]]; then
  TELEGRAM_BOT_TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_SECRETS" 2>/dev/null | cut -d= -f2- | sed 's/^"//;s/"$//' | head -1)
fi
if [[ -z "${2:-}" ]] && [[ -f "$PUBLIC_STAGING" ]]; then
  APP_PUBLIC_BASE_URL=$(grep -E '^APP_PUBLIC_BASE_URL=' "$PUBLIC_STAGING" 2>/dev/null | cut -d= -f2- | head -1)
fi
if [[ -z "${3:-}" ]] && [[ -f "$ENV_SECRETS" ]]; then
  TELEGRAM_WEBHOOK_SECRET=$(grep -E '^TELEGRAM_WEBHOOK_SECRET=' "$ENV_SECRETS" 2>/dev/null | cut -d= -f2- | sed 's/^"//;s/"$//' | head -1)
fi

TOKEN="${1:-${TELEGRAM_BOT_TOKEN:-}}"
BASE_URL="${2:-${APP_PUBLIC_BASE_URL:-}}"
SECRET="${3:-${TELEGRAM_WEBHOOK_SECRET:-}}"

if [[ -z "$TOKEN" ]] || [[ -z "$BASE_URL" ]]; then
  echo "Usage: $0 [bot-token] [public-base-url] [webhook-secret]" >&2
  echo "  Token from .env.secrets (TELEGRAM_BOT_TOKEN) if not passed." >&2
  echo "  Base URL from deploy/public.env.staging (APP_PUBLIC_BASE_URL) if not passed." >&2
  exit 1
fi

WEBHOOK_URL="${BASE_URL}/api/webhooks/telegram"

echo "Setting Telegram webhook to: ${WEBHOOK_URL}"

if [[ -n "$SECRET" ]]; then
  echo "Using TELEGRAM_WEBHOOK_SECRET for webhook registration."
  RESPONSE=$(curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook" \
    --data-urlencode "url=${WEBHOOK_URL}" \
    --data-urlencode "secret_token=${SECRET}")
else
  echo "No TELEGRAM_WEBHOOK_SECRET found; registering webhook without secret token."
  RESPONSE=$(curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook" \
    --data-urlencode "url=${WEBHOOK_URL}")
fi
echo "Response: ${RESPONSE}"

echo ""
echo "Verifying..."
INFO=$(curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo")
echo "Webhook info: ${INFO}"
