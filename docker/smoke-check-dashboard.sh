#!/usr/bin/env bash
set -euo pipefail

GATEWAY_URL="${1:-http://127.0.0.1:8800}"

echo "== gateway health =="
curl -fsS "${GATEWAY_URL}/health"
echo

echo "== dashboard HTML (expect 200) =="
curl -fsS -o /dev/null -w "HTTP %{http_code}\n" "${GATEWAY_URL}/"

echo "== dashboard overview API =="
curl -fsS "${GATEWAY_URL}/api/overview"
echo

echo "== all checks passed =="
