#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="${ROOT_DIR}/web"

if [[ ! -d "${WEB_DIR}" ]]; then
  echo "Error: web directory not found at ${WEB_DIR}" >&2
  exit 1
fi

cd "${WEB_DIR}"

export NEXT_TELEMETRY_DISABLED=1

echo "==> Install web dependencies"
npm ci

echo "==> Web lint"
npm run lint

echo "==> Web typecheck"
npm run typecheck

echo "==> Web tests"
npm test

echo "==> Next.js production build"
npm run build

if [[ "${CI_WEB_DOCKER_PARITY:-0}" == "1" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Error: CI_WEB_DOCKER_PARITY=1 but docker is not installed" >&2
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "Error: CI_WEB_DOCKER_PARITY=1 but docker daemon is not running" >&2
    exit 1
  fi

  echo "==> Docker web build parity"
  docker build \
    --build-arg NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-/api}" \
    --file "${WEB_DIR}/Dockerfile" \
    --tag collective-will-web:ci-local \
    "${WEB_DIR}"
fi

echo "Web CI parity checks passed."
