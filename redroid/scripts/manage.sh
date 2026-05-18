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

usage() {
  cat <<EOF_USAGE
Usage: $0 <command>

Commands:
  init          install Docker/adb/Java/Node/Appium, kernel setup, systemd units
  kernel        prepare binder/ashmem devices
  start         start redroid container
  stop          stop redroid container
  restart       recreate and start redroid container
  adb [port]    connect adb to redroid
  tgx           download and install latest Telegram X
  appium        start Appium in background
  status        run health checks
  logs          show redroid container logs
  bot-status    show Telegram Bot service status
  bot-logs      show Telegram Bot logs
  bot-restart   restart Telegram Bot service
  ps            show redroid container
  enable        enable redroid-vps.service
  disable       disable redroid-vps.service
EOF_USAGE
}

cmd="${1:-}"
shift || true

case "$cmd" in
  init) exec "$PROJECT_DIR/scripts/init_redroid_env.sh" "$@" ;;
  kernel) exec "$PROJECT_DIR/scripts/setup_kernel.sh" "$@" ;;
  start) exec "$PROJECT_DIR/scripts/start_redroid.sh" "$@" ;;
  stop) exec "$PROJECT_DIR/scripts/stop_redroid.sh" "$@" ;;
  restart) REDROID_RECREATE=1 exec "$PROJECT_DIR/scripts/start_redroid.sh" "$@" ;;
  adb) exec "$PROJECT_DIR/scripts/connect_adb.sh" "$@" ;;
  tgx) exec "$PROJECT_DIR/scripts/install_telegram_x.sh" "$@" ;;
  appium) exec "$PROJECT_DIR/scripts/start_appium.sh" "$@" ;;
  status) exec "$PROJECT_DIR/scripts/healthcheck.sh" "$@" ;;
  logs)
    need_cmd docker
    exec docker logs --tail "${TAIL:-200}" -f "$REDROID_NAME"
    ;;
  bot-status)
    need_cmd systemctl
    exec systemctl status tg-redroid-bot.service --no-pager
    ;;
  bot-logs)
    exec tail -n "${TAIL:-200}" -f /var/log/tg-redroid-bot.log
    ;;
  bot-restart)
    need_cmd systemctl
    exec systemctl restart tg-redroid-bot.service
    ;;
  ps)
    need_cmd docker
    exec docker ps --filter "name=^/${REDROID_NAME}$" --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
    ;;
  enable)
    need_cmd systemctl
    systemctl enable --now redroid-vps.service
    ;;
  disable)
    need_cmd systemctl
    systemctl disable --now redroid-vps.service
    ;;
  -h|--help|help|'') usage ;;
  *) usage; exit 2 ;;
esac
