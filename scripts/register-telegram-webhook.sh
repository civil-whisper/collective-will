#!/usr/bin/env bash
set -euo pipefail

# Register the Telegram bot webhook URL.
# Usage: ./scripts/register-telegram-webhook.sh <bot-token> <public-base-url>
# Example: ./scripts/register-telegram-webhook.sh "123:ABC" "https://staging.collectivewill.org"

TOKEN="${1:?Usage: register-telegram-webhook.sh <bot-token> <public-base-url>}"
BASE_URL="${2:?Usage: register-telegram-webhook.sh <bot-token> <public-base-url>}"

WEBHOOK_URL="${BASE_URL}/api/webhooks/telegram"

echo "Setting Telegram webhook to: ${WEBHOOK_URL}"

RESPONSE=$(curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook?url=${WEBHOOK_URL}")
echo "Response: ${RESPONSE}"

echo ""
echo "Verifying..."
INFO=$(curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo")
echo "Webhook info: ${INFO}"
