#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-/home/admin/hunter-craftsman}"
SERVICE_NAME="${2:-hunter-autopilot}"
ENV_TARGET="${3:-/etc/hunter-craftsman/hunter.env}"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}.service"
TIMER_TARGET="/etc/systemd/system/${SERVICE_NAME}.timer"

mkdir -p "$(dirname "${ENV_TARGET}")"

if [[ ! -f "${ENV_TARGET}" ]]; then
  cp "${REPO_ROOT}/docker/systemd/hunter.env.example" "${ENV_TARGET}"
  echo "created env template at ${ENV_TARGET}"
fi

sed \
  -e "s#/opt/hunter-agent#${REPO_ROOT//\//\\/}#g" \
  "${REPO_ROOT}/docker/systemd/hunter-autopilot.service" | sudo tee "${SERVICE_TARGET}" >/dev/null

cp "${REPO_ROOT}/docker/systemd/hunter-autopilot.timer" /tmp/hunter-autopilot.timer.tmp
sudo mv /tmp/hunter-autopilot.timer.tmp "${TIMER_TARGET}"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.timer"
echo "installed ${SERVICE_TARGET} and ${TIMER_TARGET}"
echo "edit ${ENV_TARGET} and then run: sudo systemctl start ${SERVICE_NAME}.timer"
