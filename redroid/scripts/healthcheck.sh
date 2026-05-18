#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_SOURCE" ]; do
  SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"
  SCRIPT_SOURCE="$(readlink "$SCRIPT_SOURCE")"
  [[ "$SCRIPT_SOURCE" != /* ]] && SCRIPT_SOURCE="$SCRIPT_DIR/$SCRIPT_SOURCE"
done
PROJECT_DIR="${PROJECT_DIR:-$(cd -P "$(dirname "$SCRIPT_SOURCE")/.." && pwd)}"
# shellcheck source=lib.sh
. "$PROJECT_DIR/scripts/lib.sh"
load_env

ok=1
check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '[OK]   %s\n' "$name"
  else
    printf '[FAIL] %s\n' "$name"
    ok=0
  fi
}

check "docker command" command -v docker
check "docker daemon" docker info
check "redroid container running" container_running
check "ADB tcp port $REDROID_ADB_BIND_ADDR:$REDROID_HOST_ADB_PORT" wait_for_tcp "$REDROID_ADB_BIND_ADDR" "$REDROID_HOST_ADB_PORT" 2

if command -v adb >/dev/null 2>&1; then
  adb connect "$REDROID_ADB_BIND_ADDR:$REDROID_HOST_ADB_PORT" >/dev/null 2>&1 || true
  check "ADB device state" adb -s "$REDROID_ADB_BIND_ADDR:$REDROID_HOST_ADB_PORT" get-state
else
  printf '[FAIL] adb command\n'
  ok=0
fi

if command -v curl >/dev/null 2>&1; then
  check "Appium status" curl -fsS "http://$APPIUM_BIND_ADDR:$APPIUM_PORT/status"
fi

[ "$ok" -eq 1 ]
