#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-/home/admin/hunter-craftsman}"
SERVICE_NAME="${2:-gateway}"
ENV_FILE="${3:-/home/admin/hunter-craftsman/craftsman/.env}"

SERVICE_FILE="${REPO_ROOT}/docker/systemd/gateway.service"

if [[ ! -f "${SERVICE_FILE}" ]]; then
  echo "ERROR: ${SERVICE_FILE} not found"
  exit 1
fi

echo "== installing gateway systemd service =="
sudo cp "${SERVICE_FILE}" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

echo "== gateway service installed =="
echo "next: sudo systemctl start ${SERVICE_NAME}"
