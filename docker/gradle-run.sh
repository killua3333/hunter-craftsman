#!/usr/bin/env bash
set -euo pipefail

cd "${WORKDIR:-/workspace/project}"
chmod +x ./gradlew 2>/dev/null || true

if [[ "${1:-}" == "smoke" ]]; then
  exec /opt/builder/smoke-run.sh "${2:-}"
fi

exec ./gradlew "$@"
