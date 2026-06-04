#!/usr/bin/env bash
set -euo pipefail

cd "${WORKDIR:-/workspace/project}"

if [[ "${1:-}" == "smoke" ]]; then
  exec /opt/builder/smoke-run.sh "${2:-}"
fi

# Prefer pre-installed Gradle to avoid wrapper network downloads.
# The Dockerfile unzips to /opt/gradle-8.7 so check that first.
for G in /opt/gradle-8.7/bin/gradle /opt/gradle/bin/gradle gradle; do
  if command -v "$G" &>/dev/null || [[ -x "$G" ]]; then
    exec "$G" --no-daemon "$@"
  fi
done

# Fallback: use gradlew wrapper
chmod +x ./gradlew 2>/dev/null || true
exec ./gradlew "$@"
