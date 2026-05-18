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
require_root
need_cmd docker

valid_port "$REDROID_HOST_ADB_PORT" || die "Invalid REDROID_HOST_ADB_PORT: $REDROID_HOST_ADB_PORT"

install -d "$REDROID_DATA_DIR"

if container_exists && [ "$REDROID_RECREATE" = "1" ]; then
  log "Removing existing container $REDROID_NAME because REDROID_RECREATE=1"
  docker rm -f "$REDROID_NAME" >/dev/null
fi

if container_exists; then
  if container_running; then
    log "Container $REDROID_NAME is already running"
  else
    log "Starting existing container $REDROID_NAME"
    docker start "$REDROID_NAME" >/dev/null
  fi
else
  run_args=(
    run -d
    --restart unless-stopped
    --privileged
    --pull missing
    --name "$REDROID_NAME"
    --label "managed-by=/root/redroid"
    -v "$REDROID_DATA_DIR:/data"
    -p "$REDROID_ADB_BIND_ADDR:$REDROID_HOST_ADB_PORT:5555"
  )

  for dev in binder hwbinder vndbinder; do
    if [ -e "/dev/$dev" ]; then
      run_args+=(-v "/dev/$dev:/dev/$dev")
    fi
  done

  if [ -n "$REDROID_DNS" ]; then
    run_args+=(--dns "$REDROID_DNS")
  fi

  extra_args=()
  if [ -n "$REDROID_EXTRA_ARGS" ]; then
    # Intentionally split on shell words for Docker/redroid kernel args.
    # Do not put secrets in REDROID_EXTRA_ARGS.
    read -r -a extra_args <<< "$REDROID_EXTRA_ARGS"
  fi

  log "Creating redroid container $REDROID_NAME"
  docker "${run_args[@]}" "$REDROID_IMAGE" "${extra_args[@]}" >/dev/null
fi

log "ADB endpoint: $REDROID_ADB_BIND_ADDR:$REDROID_HOST_ADB_PORT"
wait_for_tcp "$REDROID_ADB_BIND_ADDR" "$REDROID_HOST_ADB_PORT" 60 || warn "ADB port did not become ready within 60s"
docker ps --filter "name=^/${REDROID_NAME}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
