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
need_cmd adb

endpoint="${1:-$REDROID_ADB_BIND_ADDR:$REDROID_HOST_ADB_PORT}"
case "$endpoint" in
  *:*) ;;
  *) endpoint="127.0.0.1:$endpoint" ;;
esac

adb start-server >/dev/null 2>&1 || true
log "Connecting adb to $endpoint"
adb connect "$endpoint"

serial="$endpoint"
for _ in $(seq 1 45); do
  state="$(adb -s "$serial" get-state 2>/dev/null || true)"
  [ "$state" = "device" ] && break
  sleep 1
done

adb devices
state="$(adb -s "$serial" get-state 2>/dev/null || true)"
[ "$state" = "device" ] || die "ADB device $serial is not ready"
