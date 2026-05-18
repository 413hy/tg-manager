#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_SOURCE" ]; do
  SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"
  SCRIPT_SOURCE="$(readlink "$SCRIPT_SOURCE")"
  [[ "$SCRIPT_SOURCE" != /* ]] && SCRIPT_SOURCE="$SCRIPT_DIR/$SCRIPT_SOURCE"
done
PROJECT_DIR="${PROJECT_DIR:-$(cd -P "$(dirname "$SCRIPT_SOURCE")/.." && pwd)}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/redroid.env}"

log() { printf '\033[1;32m[+] %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
err() { printf '\033[1;31m[-] %s\033[0m\n' "$*" >&2; }
die() { err "$*"; exit 1; }

load_env() {
  if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  fi

  : "${REDROID_IMAGE:=redroid/redroid:12.0.0_64only-latest}"
  : "${REDROID_NAME:=redroid12}"
  : "${REDROID_DATA_DIR:=/var/lib/redroid/data}"
  : "${REDROID_ADB_BIND_ADDR:=127.0.0.1}"
  : "${REDROID_HOST_ADB_PORT:=5555}"
  : "${REDROID_RECREATE:=0}"
  : "${REDROID_DNS:=}"
  : "${REDROID_EXTRA_ARGS:=}"
  : "${ANDROID_SDK_ROOT_DIR:=/opt/android-sdk}"
  : "${APPIUM_BIND_ADDR:=127.0.0.1}"
  : "${APPIUM_PORT:=4723}"
  : "${APPIUM_LOG:=/var/log/appium-redroid.log}"
  : "${APPIUM_PID_FILE:=/run/appium-redroid.pid}"
  : "${TELEGRAM_X_DOWNLOAD_DIR:=/opt/redroid/apk}"
  : "${TELEGRAM_X_APK_PATH:=$TELEGRAM_X_DOWNLOAD_DIR/telegram-x-latest.apk}"
  : "${TELEGRAM_X_ASSET_NAME_REGEX:=^Telegram-X-.*\.apk$}"

  export ANDROID_HOME="${ANDROID_HOME:-$ANDROID_SDK_ROOT_DIR}"
  export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_SDK_ROOT_DIR}"
  export PATH="$PATH:$ANDROID_SDK_ROOT_DIR/platform-tools"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

require_root() {
  [ "${EUID:-$(id -u)}" -eq 0 ] || die "Please run as root"
}

valid_port() {
  case "${1:-}" in
    ''|*[!0-9]*) return 1 ;;
    *) [ "$1" -ge 1 ] && [ "$1" -le 65535 ] ;;
  esac
}

wait_for_tcp() {
  local host="$1" port="$2" timeout="${3:-60}" start
  start="$(date +%s)"
  while :; do
    if command -v nc >/dev/null 2>&1 && nc -z "$host" "$port" >/dev/null 2>&1; then
      return 0
    fi
    if command -v ss >/dev/null 2>&1 && ss -lnt | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
      return 0
    fi
    [ "$(( $(date +%s) - start ))" -lt "$timeout" ] || return 1
    sleep 1
  done
}

container_exists() {
  docker inspect "$REDROID_NAME" >/dev/null 2>&1
}

container_running() {
  [ "$(docker inspect -f '{{.State.Running}}' "$REDROID_NAME" 2>/dev/null || true)" = "true" ]
}
