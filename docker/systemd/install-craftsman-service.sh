#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-/opt/hunter-agent}"
SERVICE_NAME="${2:-craftsman}"
ENV_TARGET="${3:-/etc/hunter-craftsman/craftsman.env}"
UNIT_TARGET="/etc/systemd/system/${SERVICE_NAME}.service"

mkdir -p "$(dirname "${ENV_TARGET}")"

if [[ ! -f "${ENV_TARGET}" ]]; then
  cp "${REPO_ROOT}/docker/systemd/craftsman.env.example" "${ENV_TARGET}"
  echo "created env template at ${ENV_TARGET}"
fi

sed \
  -e "s#/opt/hunter-agent#${REPO_ROOT//\//\\/}#g" \
  "${REPO_ROOT}/docker/systemd/craftsman.service" | sudo tee "${UNIT_TARGET}" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
echo "installed ${UNIT_TARGET}"
echo "edit ${ENV_TARGET} and then run: sudo systemctl start ${SERVICE_NAME}"
