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
need_cmd curl
need_cmd jq
need_cmd adb

serial="${ADB_SERIAL:-$REDROID_ADB_BIND_ADDR:$REDROID_HOST_ADB_PORT}"
install -d "$TELEGRAM_X_DOWNLOAD_DIR"

log "Resolving latest Telegram X APK from GitHub releases"
api_json="$(curl -fsSL https://api.github.com/repos/TGX-Android/Telegram-X/releases/latest)"
asset_url="$(printf '%s' "$api_json" | jq -r --arg re "$TELEGRAM_X_ASSET_NAME_REGEX" '
  [.assets[] | select(.name | test($re))]
  | sort_by(
      if (.name | test("universal|x86|x86_64"; "i")) then 0
      elif (.name | test("arm64|armeabi"; "i")) then 1
      else 2 end,
      (.name | length)
    )
  | .[0].browser_download_url // empty
')"

[ -n "$asset_url" ] || die "Failed to locate Telegram X APK asset"

log "Downloading Telegram X APK"
curl -fL "$asset_url" -o "$TELEGRAM_X_APK_PATH"

adb start-server >/dev/null 2>&1 || true
adb connect "$serial" >/dev/null 2>&1 || true

log "Installing Telegram X to $serial"
adb -s "$serial" install -r -g "$TELEGRAM_X_APK_PATH"
adb -s "$serial" shell pm list packages | grep -i 'org.thunderdog.challegram' || warn "Telegram X package was not listed after install"
