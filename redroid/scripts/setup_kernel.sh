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

log "Preparing binder and ashmem prerequisites"

modprobe binder_linux devices="binder,hwbinder,vndbinder" 2>/dev/null || true
modprobe ashmem_linux 2>/dev/null || true

mkdir -p /dev/binderfs
if ! mountpoint -q /dev/binderfs 2>/dev/null; then
  mount -t binder binder /dev/binderfs 2>/dev/null || true
fi

for dev in binder hwbinder vndbinder; do
  if [ ! -e "/dev/$dev" ] && [ -e "/dev/binderfs/$dev" ]; then
    ln -sf "/dev/binderfs/$dev" "/dev/$dev"
  fi
done

if [ -r /proc/misc ]; then
  while read -r major name; do
    case "$name" in
      binder|hwbinder|vndbinder)
        [ -e "/dev/$name" ] || mknod "/dev/$name" c 10 "$major" 2>/dev/null || true
        ;;
    esac
  done < /proc/misc
fi

chmod 666 /dev/binder /dev/hwbinder /dev/vndbinder 2>/dev/null || true

install -d /etc/modules-load.d /etc/modprobe.d
cat >/etc/modules-load.d/redroid.conf <<'EOF_MODLOAD'
binder_linux
ashmem_linux
EOF_MODLOAD
cat >/etc/modprobe.d/redroid.conf <<'EOF_MODPROBE'
options binder_linux devices=binder,hwbinder,vndbinder
EOF_MODPROBE

missing=0
for dev in binder hwbinder vndbinder; do
  if [ ! -e "/dev/$dev" ]; then
    warn "/dev/$dev is missing"
    missing=1
  fi
done

if [ "$missing" -eq 1 ]; then
  warn "The VPS kernel may not provide Android binder devices. redroid can fail on this host."
else
  log "Binder devices are available"
fi
