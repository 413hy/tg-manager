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
need_cmd appium

mode="${1:-background}"
valid_port "$APPIUM_PORT" || die "Invalid APPIUM_PORT: $APPIUM_PORT"
install -d "$(dirname "$APPIUM_LOG")" "$(dirname "$APPIUM_PID_FILE")"

if [ "$mode" = "--foreground" ] || [ "$mode" = "foreground" ]; then
  exec env ANDROID_HOME="$ANDROID_HOME" ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" \
    appium server --address "$APPIUM_BIND_ADDR" --port "$APPIUM_PORT"
fi

if [ -r "$APPIUM_PID_FILE" ] && kill -0 "$(cat "$APPIUM_PID_FILE")" 2>/dev/null; then
  log "Appium is already running with PID $(cat "$APPIUM_PID_FILE")"
else
  log "Starting Appium on $APPIUM_BIND_ADDR:$APPIUM_PORT"
  nohup env ANDROID_HOME="$ANDROID_HOME" ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" \
    appium server --address "$APPIUM_BIND_ADDR" --port "$APPIUM_PORT" >"$APPIUM_LOG" 2>&1 &
  echo "$!" > "$APPIUM_PID_FILE"
fi

for _ in $(seq 1 45); do
  if curl -fsS "http://$APPIUM_BIND_ADDR:$APPIUM_PORT/status"; then
    exit 0
  fi
  sleep 1
done

warn "Appium status endpoint is not ready; see $APPIUM_LOG"
exit 1
