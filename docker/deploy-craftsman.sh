#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-/home/admin/hunter-craftsman}"
SERVICE_NAME="${2:-craftsman}"
ENV_TARGET="${3:-/etc/hunter-craftsman/craftsman.env}"
INSTALL_NGINX="${INSTALL_NGINX:-false}"
INSTALL_HUNTER_TIMER="${INSTALL_HUNTER_TIMER:-false}"

echo "== preflight =="
bash "${REPO_ROOT}/docker/preflight-check.sh" "${REPO_ROOT}"

echo "== install systemd service =="
bash "${REPO_ROOT}/docker/systemd/install-craftsman-service.sh" "${REPO_ROOT}" "${SERVICE_NAME}" "${ENV_TARGET}"

if [[ "${INSTALL_NGINX}" == "true" ]]; then
  echo "== install nginx site =="
  bash "${REPO_ROOT}/docker/nginx/install-craftsman-nginx.sh" "${REPO_ROOT}" "${SERVICE_NAME}"
fi

if [[ "${INSTALL_HUNTER_TIMER}" == "true" ]]; then
  echo "== install hunter autopilot timer =="
  bash "${REPO_ROOT}/docker/systemd/install-hunter-autopilot.sh" "${REPO_ROOT}"
fi

echo "== deployment scaffolded =="
echo "1. edit ${ENV_TARGET}"
echo "2. sudo systemctl start ${SERVICE_NAME}"
echo "3. bash ${REPO_ROOT}/docker/smoke-check.sh"
