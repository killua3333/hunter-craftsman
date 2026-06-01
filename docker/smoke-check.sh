#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8791}"

echo "== health =="
curl -fsS "${BASE_URL}/health"
echo

echo "== readyz =="
curl -fsS "${BASE_URL}/readyz"
echo

echo "== dashboard =="
curl -fsS -o /dev/null -w "%{http_code}\n" "${BASE_URL}/dashboard"

echo "== dashboard overview =="
curl -fsS "${BASE_URL}/dashboard/api/overview"
echo
