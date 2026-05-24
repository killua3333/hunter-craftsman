#!/usr/bin/env bash
# Best-effort emulator smoke test inside builder container.
set -euo pipefail

PACKAGE_ID="${1:?package id required}"
APK="app/build/outputs/apk/debug/app-debug.apk"

if [[ ! -f "$APK" ]]; then
  echo "[smoke] APK not found: $APK — run assembleDebug first"
  exit 2
fi

if ! command -v emulator >/dev/null 2>&1; then
  echo "[smoke] emulator not installed in image — skipped"
  exit 2
fi

# KVM 不可用时模拟器无法启动，直接跳过避免 600s 阻塞
if [[ ! -c /dev/kvm ]]; then
  echo "[smoke] /dev/kvm not available — smoke skipped (enable KVM on host for emulator support)"
  exit 2
fi

export ANDROID_HOME="${ANDROID_HOME:-/opt/android-sdk}"
export PATH="${PATH}:${ANDROID_HOME}/platform-tools:${ANDROID_HOME}/emulator"

echo "[smoke] creating AVD if missing..."
echo no | avdmanager create avd -n smoke_avd -k "system-images;android-34;google_apis;x86_64" -d pixel_6 2>/dev/null || true

echo "[smoke] starting emulator headless..."
nohup emulator -avd smoke_avd -no-window -no-audio -gpu swiftshader_indirect -no-snapshot-save >/tmp/emulator.log 2>&1 &

# 轮询启动状态（最多 120 秒），避免 sleep 固定等待
BOOT_WAIT=0
until adb -e shell getprop sys.boot_completed 2>/dev/null | grep -q 1; do
  if (( BOOT_WAIT >= 120 )); then
    echo "[smoke] emulator boot timeout — skipped"
    adb emu kill 2>/dev/null || true
    exit 2
  fi
  sleep 3
  (( BOOT_WAIT += 3 ))
done
echo "[smoke] emulator booted in ${BOOT_WAIT}s"

echo "[smoke] installing $APK"
adb install -r "$APK"

echo "[smoke] monkey 50 events on $PACKAGE_ID"
set +e
adb shell monkey -p "$PACKAGE_ID" -v 50
MONKEY_EXIT=$?
set -e

LOG=$(adb logcat -d 2>/dev/null || true)
if echo "$LOG" | grep -q "FATAL EXCEPTION"; then
  echo "[smoke] FATAL EXCEPTION detected"
  echo "$LOG" | grep -A3 "FATAL EXCEPTION" | tail -20
  adb emu kill 2>/dev/null || true
  exit 1
fi

adb emu kill 2>/dev/null || true
if [[ $MONKEY_EXIT -ne 0 ]]; then
  echo "[smoke] monkey exit code $MONKEY_EXIT"
  exit 1
fi

echo "[smoke] passed"
exit 0
