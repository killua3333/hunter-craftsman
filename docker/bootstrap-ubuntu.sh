#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-/opt/hunter-agent}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "== apt update =="
sudo apt-get update

echo "== install base packages =="
sudo apt-get install -y \
  git \
  curl \
  nginx \
  python3 \
  python3-venv \
  python3-pip

echo "== create repo directories =="
sudo mkdir -p "${REPO_ROOT}"
sudo chown "$(id -u):$(id -g)" "${REPO_ROOT}"

echo "== create virtualenv =="
if [[ ! -d "${REPO_ROOT}/.venv" ]]; then
  "${PYTHON_BIN}" -m venv "${REPO_ROOT}/.venv"
fi

echo "== install craftsman dependencies =="
"${REPO_ROOT}/.venv/bin/pip" install --upgrade pip
"${REPO_ROOT}/.venv/bin/pip" install -r "${REPO_ROOT}/craftsman/requirements.txt"
"${REPO_ROOT}/.venv/bin/pip" install -e "${REPO_ROOT}/craftsman"
"${REPO_ROOT}/.venv/bin/pip" install -e "${REPO_ROOT}/hunter"

echo "== bootstrap complete =="
echo "next: run docker/deploy-craftsman.sh after reviewing env values"
