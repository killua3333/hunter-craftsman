#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
CRAFTSMAN_ROOT="${REPO_ROOT}/craftsman"

check() {
  local name="$1"
  local ok="$2"
  local detail="$3"
  printf '{"name":"%s","ok":%s,"detail":"%s"}\n' "$name" "$ok" "$detail"
}

if command -v python >/dev/null 2>&1; then
  python_detail="$(python --version 2>&1)"
  check "python" "true" "${python_detail}"
elif command -v python3 >/dev/null 2>&1; then
  python_detail="$(python3 --version 2>&1)"
  check "python3" "true" "${python_detail}"
else
  check "python" "false" "python not found"
fi

[[ -d "${CRAFTSMAN_ROOT}" ]] && check "craftsman-root" "true" "${CRAFTSMAN_ROOT}" || check "craftsman-root" "false" "${CRAFTSMAN_ROOT}"
[[ -f "${REPO_ROOT}/docker/systemd/craftsman.service" ]] && check "systemd-unit-template" "true" "${REPO_ROOT}/docker/systemd/craftsman.service" || check "systemd-unit-template" "false" "${REPO_ROOT}/docker/systemd/craftsman.service"
[[ -f "${REPO_ROOT}/docker/systemd/craftsman.env.example" ]] && check "systemd-env-template" "true" "${REPO_ROOT}/docker/systemd/craftsman.env.example" || check "systemd-env-template" "false" "${REPO_ROOT}/docker/systemd/craftsman.env.example"
[[ -f "${REPO_ROOT}/docker/nginx/craftsman.conf.example" ]] && check "nginx-template" "true" "${REPO_ROOT}/docker/nginx/craftsman.conf.example" || check "nginx-template" "false" "${REPO_ROOT}/docker/nginx/craftsman.conf.example"
[[ -d "${CRAFTSMAN_ROOT}/workspace" ]] && check "workspace-dir" "true" "${CRAFTSMAN_ROOT}/workspace" || check "workspace-dir" "false" "${CRAFTSMAN_ROOT}/workspace"
[[ -d "${CRAFTSMAN_ROOT}/callbacks" ]] && check "callbacks-dir" "true" "${CRAFTSMAN_ROOT}/callbacks" || check "callbacks-dir" "false" "${CRAFTSMAN_ROOT}/callbacks"
