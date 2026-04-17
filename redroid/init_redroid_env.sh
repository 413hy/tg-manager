#!/usr/bin/env bash
set -Eeuo pipefail

# Multi-distro VPS bootstrap for Docker + redroid + ADB + Appium + Telegram X
# Supported families: Alpine, Debian/Ubuntu, RHEL/CentOS Stream/Rocky/AlmaLinux
# Run as root.

SCRIPT_VERSION="2026-04-17-fixed"

# ===== Configurable defaults =====
REDROID_IMAGE="${REDROID_IMAGE:-redroid/redroid:12.0.0_64only-latest}"
REDROID_NAME="${REDROID_NAME:-redroid12}"
REDROID_DATA_DIR="${REDROID_DATA_DIR:-/var/lib/redroid/data}"
REDROID_HOST_ADB_PORT="${REDROID_HOST_ADB_PORT:-5555}"

INSTALL_DOCKER="${INSTALL_DOCKER:-1}"
INSTALL_ADB="${INSTALL_ADB:-1}"
INSTALL_JAVA="${INSTALL_JAVA:-1}"
INSTALL_NODE="${INSTALL_NODE:-1}"
INSTALL_APPIUM="${INSTALL_APPIUM:-1}"
START_REDROID_NOW="${START_REDROID_NOW:-1}"
INSTALL_TELEGRAM_X_NOW="${INSTALL_TELEGRAM_X_NOW:-1}"
START_APPIUM_NOW="${START_APPIUM_NOW:-0}"

ANDROID_SDK_ROOT_DIR="${ANDROID_SDK_ROOT_DIR:-/opt/android-sdk}"
APPIUM_LOG="${APPIUM_LOG:-/var/log/appium.log}"
APPIUM_BIND_ADDR="${APPIUM_BIND_ADDR:-127.0.0.1}"
APPIUM_PORT="${APPIUM_PORT:-4723}"

TELEGRAM_X_ASSET_NAME_REGEX="${TELEGRAM_X_ASSET_NAME_REGEX:-^Telegram-X-.*\.apk$}"
TELEGRAM_X_DOWNLOAD_DIR="${TELEGRAM_X_DOWNLOAD_DIR:-/opt/redroid/apk}"
TELEGRAM_X_APK_PATH="${TELEGRAM_X_APK_PATH:-$TELEGRAM_X_DOWNLOAD_DIR/telegram-x-latest.apk}"

# ===== Helpers =====
log() { printf '\033[1;32m[+] %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
err() { printf '\033[1;31m[-] %s\033[0m\n' "$*"; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    err "Required command not found: $1"
    exit 1
  }
}

require_root() {
  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    err "Please run as root"
    exit 1
  fi
}

normalize_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    armv7l|armv7) echo "armhf" ;;
    *) echo "unknown" ;;
  esac
}

ver_ge() {
  # returns 0 if $1 >= $2
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

source_os_release() {
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
  else
    err "/etc/os-release not found"
    exit 1
  fi
}

get_init_system() {
  if command -v systemctl >/dev/null 2>&1; then
    echo "systemd"
  elif command -v rc-update >/dev/null 2>&1; then
    echo "openrc"
  else
    echo "unknown"
  fi
}

pkg_install_apt() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends "$@"
}

pkg_install_dnf() {
  dnf install -y "$@"
}

pkg_install_apk() {
  apk add --no-cache "$@"
}

enable_service() {
  local svc="$1"
  case "$INIT_SYSTEM" in
    systemd)
      systemctl enable "$svc" >/dev/null 2>&1 || true
      systemctl restart "$svc"
      ;;
    openrc)
      rc-update add "$svc" default >/dev/null 2>&1 || true
      service "$svc" restart || service "$svc" start
      ;;
    *)
      warn "Unknown init system; start service manually: $svc"
      ;;
  esac
}

install_common_packages() {
  case "$DISTRO_FAMILY" in
    deb)
      pkg_install_apt ca-certificates curl gnupg jq unzip bash tar gzip coreutils grep sed gawk procps util-linux iproute2 lsof kmod
      ;;
    rpm)
      pkg_install_dnf ca-certificates curl gnupg2 jq unzip bash tar gzip coreutils grep sed gawk procps-ng util-linux iproute lsof kmod which findutils shadow-utils
      ;;
    alpine)
      ensure_alpine_community_repo
      pkg_install_apk ca-certificates curl jq unzip bash tar gzip coreutils grep sed gawk procps util-linux iproute2 lsof kmod shadow
      ;;
  esac
}

ensure_alpine_community_repo() {
  if ! grep -Eq '^[^#].*/community$' /etc/apk/repositories; then
    if grep -Eq '^#.*community$' /etc/apk/repositories; then
      sed -i 's|^#\(.*community\)$|\1|' /etc/apk/repositories
    else
      local branch="${VERSION_ID:-}"
      [ -n "$branch" ] || branch="$(cut -d. -f1,2 /etc/alpine-release 2>/dev/null || true)"
      [ -n "$branch" ] || branch="v3.21"
      printf 'https://dl-cdn.alpinelinux.org/alpine/%s/community\n' "$branch" >> /etc/apk/repositories
    fi
  fi
}

install_docker() {
  [ "$INSTALL_DOCKER" = "1" ] || return 0
  log "Installing Docker"

  case "$DISTRO_FAMILY" in
    deb)
      pkg_install_apt ca-certificates curl gnupg
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL "https://download.docker.com/linux/${ID}/gpg" | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      chmod a+r /etc/apt/keyrings/docker.gpg
      local codename="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"
      if [ -z "$codename" ]; then
        codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
      fi
      printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/%s %s stable\n' \
        "$(dpkg --print-architecture)" "$ID" "$codename" > /etc/apt/sources.list.d/docker.list
      apt-get update -y
      apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      ;;
    rpm)
      if [ "$ID" = "centos" ] || [[ "${ID_LIKE:-}" == *centos* ]]; then
        dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
      else
        dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
      fi
      dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      ;;
    alpine)
      pkg_install_apk docker docker-cli-compose
      ;;
  esac

  enable_service docker
  docker version >/dev/null 2>&1 || {
    err "Docker installed but daemon is not responding"
    exit 1
  }
}

install_java() {
  [ "$INSTALL_JAVA" = "1" ] || return 0
  log "Installing Java runtime"
  case "$DISTRO_FAMILY" in
    deb)
      pkg_install_apt openjdk-21-jre-headless || pkg_install_apt openjdk-17-jre-headless || pkg_install_apt default-jre-headless
      ;;
    rpm)
      pkg_install_dnf java-21-openjdk-headless || pkg_install_dnf java-17-openjdk-headless || pkg_install_dnf java-17-openjdk
      ;;
    alpine)
      pkg_install_apk openjdk21-jre-headless || pkg_install_apk openjdk17-jre-headless
      ;;
  esac
}

install_node() {
  [ "$INSTALL_NODE" = "1" ] || return 0
  log "Installing Node.js and npm"

  case "$DISTRO_FAMILY" in
    deb)
      curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
      apt-get install -y nodejs
      ;;
    rpm)
      curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
      dnf install -y nodejs
      ;;
    alpine)
      pkg_install_apk nodejs npm || pkg_install_apk nodejs-current npm
      ;;
  esac

  need_cmd node
  need_cmd npm

  local nv
  nv="$(node -v | sed 's/^v//')"
  if ! ver_ge "$nv" "20.19.0"; then
    warn "Installed Node.js version is $nv; Appium 3.x recommends >=20.19.0. Appium install may fail on older Alpine repos."
  fi
}

install_adb() {
  [ "$INSTALL_ADB" = "1" ] || return 0
  log "Installing adb / Android platform tools"
  case "$DISTRO_FAMILY" in
    deb)
      pkg_install_apt adb
      ;;
    rpm)
      pkg_install_dnf android-tools
      ;;
    alpine)
      pkg_install_apk android-tools
      ;;
  esac

  install -d "$ANDROID_SDK_ROOT_DIR/platform-tools"
  if command -v adb >/dev/null 2>&1; then
    ln -sf "$(command -v adb)" "$ANDROID_SDK_ROOT_DIR/platform-tools/adb"
  fi
  cat >/etc/profile.d/redroid-android-sdk.sh <<EOF_ENV
export ANDROID_HOME="$ANDROID_SDK_ROOT_DIR"
export ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT_DIR"
export PATH="\$PATH:$ANDROID_SDK_ROOT_DIR/platform-tools"
EOF_ENV
}

install_appium() {
  [ "$INSTALL_APPIUM" = "1" ] || return 0
  log "Installing Appium and UiAutomator2 driver"
  need_cmd npm
  npm i --location=global appium
  if ! appium driver list --installed 2>/dev/null | grep -q 'uiautomator2@'; then
    appium driver install uiautomator2
  else
    log "Appium UiAutomator2 driver already installed; skipping"
  fi

  cat >/usr/local/bin/start-appium-redroid <<'EOF_APP'
#!/usr/bin/env bash
set -euo pipefail
: "${ANDROID_HOME:=/opt/android-sdk}"
: "${ANDROID_SDK_ROOT:=/opt/android-sdk}"
: "${APPIUM_BIND_ADDR:=127.0.0.1}"
: "${APPIUM_PORT:=4723}"
: "${APPIUM_LOG:=/var/log/appium.log}"
nohup env ANDROID_HOME="$ANDROID_HOME" ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" \
  appium server --address "$APPIUM_BIND_ADDR" --port "$APPIUM_PORT" >"$APPIUM_LOG" 2>&1 &
sleep 3
curl -fsS "http://${APPIUM_BIND_ADDR}:${APPIUM_PORT}/status" || true
EOF_APP
  chmod +x /usr/local/bin/start-appium-redroid

  if [ "$START_APPIUM_NOW" = "1" ]; then
    /usr/local/bin/start-appium-redroid
  fi
}

setup_kernel_for_redroid() {
  log "Preparing binder / ashmem prerequisites for redroid"

  modprobe binder_linux devices="binder,hwbinder,vndbinder" 2>/dev/null || true
  modprobe ashmem_linux 2>/dev/null || true

  if [ -f /proc/misc ]; then
    if grep -q '^119 vndbinder$' /proc/misc && [ ! -e /dev/vndbinder ]; then
      mknod /dev/vndbinder c 10 119 || true
    fi
    if grep -q '^120 hwbinder$' /proc/misc && [ ! -e /dev/hwbinder ]; then
      mknod /dev/hwbinder c 10 120 || true
    fi
    if grep -q '^121 binder$' /proc/misc && [ ! -e /dev/binder ]; then
      mknod /dev/binder c 10 121 || true
    fi
  fi

  chmod 666 /dev/binder /dev/hwbinder /dev/vndbinder 2>/dev/null || true

  if [ -d /etc/modules-load.d ]; then
    cat >/etc/modules-load.d/redroid.conf <<'EOF_MOD'
binder_linux
ashmem_linux
EOF_MOD
  fi

  if [ ! -e /dev/binder ]; then
    warn "Binder device not found. redroid may fail unless your kernel already exposes binder via binderfs or modules."
  fi
}

write_redroid_helpers() {
  install -d /usr/local/bin "$REDROID_DATA_DIR" "$TELEGRAM_X_DOWNLOAD_DIR"

  cat >/usr/local/bin/start-redroid <<EOF_RED
#!/usr/bin/env bash
set -euo pipefail
REDROID_IMAGE="\${REDROID_IMAGE:-$REDROID_IMAGE}"
REDROID_NAME="\${REDROID_NAME:-$REDROID_NAME}"
REDROID_DATA_DIR="\${REDROID_DATA_DIR:-$REDROID_DATA_DIR}"
REDROID_HOST_ADB_PORT="\${REDROID_HOST_ADB_PORT:-$REDROID_HOST_ADB_PORT}"
mkdir -p "\$REDROID_DATA_DIR"
docker rm -f "\$REDROID_NAME" >/dev/null 2>&1 || true
docker run -itd --rm --privileged \
  --pull always \
  -v /dev/binder:/dev/binder \
  -v /dev/hwbinder:/dev/hwbinder \
  -v /dev/vndbinder:/dev/vndbinder \
  -v "\$REDROID_DATA_DIR:/data" \
  -p "\$REDROID_HOST_ADB_PORT:5555" \
  --name "\$REDROID_NAME" \
  "\$REDROID_IMAGE"
EOF_RED
  chmod +x /usr/local/bin/start-redroid

  cat >/usr/local/bin/connect-redroid-adb <<EOF_ADB
#!/usr/bin/env bash
set -euo pipefail
PORT="\${1:-$REDROID_HOST_ADB_PORT}"
adb start-server >/dev/null 2>&1 || true
adb connect "127.0.0.1:\$PORT"
adb devices
EOF_ADB
  chmod +x /usr/local/bin/connect-redroid-adb

  cat >/usr/local/bin/install-telegram-x <<'EOF_TGX'
#!/usr/bin/env bash
set -euo pipefail
: "${REDROID_HOST_ADB_PORT:=5555}"
: "${TELEGRAM_X_DOWNLOAD_DIR:=/opt/redroid/apk}"
: "${TELEGRAM_X_APK_PATH:=/opt/redroid/apk/telegram-x-latest.apk}"
: "${TELEGRAM_X_ASSET_NAME_REGEX:=^Telegram-X-.*\.apk$}"
mkdir -p "$TELEGRAM_X_DOWNLOAD_DIR"
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
need curl
need jq
need adb

api_json="$(curl -fsSL https://api.github.com/repos/TGX-Android/Telegram-X/releases/latest)"
asset_url="$(printf '%s' "$api_json" | jq -r --arg re "$TELEGRAM_X_ASSET_NAME_REGEX" '
  .assets
  | map(select(.name | test($re)))
  | sort_by(.name)
  | map(select(.name | test("legacy|lollipop|arm64|armeabi|universal"; "i") | not)) as $preferred
  | if ($preferred|length)>0 then $preferred[0].browser_download_url else .[0].browser_download_url end
')"
if [ -z "$asset_url" ] || [ "$asset_url" = "null" ]; then
  # fallback: prefer the shortest matching APK name (usually the universal/default one)
  asset_url="$(printf '%s' "$api_json" | jq -r --arg re "$TELEGRAM_X_ASSET_NAME_REGEX" '
    .assets
    | map(select(.name | test($re)))
    | sort_by(.name | length)
    | .[0].browser_download_url
  ')"
fi
[ -n "$asset_url" ] && [ "$asset_url" != "null" ] || { echo "Failed to locate Telegram X APK asset URL" >&2; exit 1; }

curl -fL "$asset_url" -o "$TELEGRAM_X_APK_PATH"
adb start-server >/dev/null 2>&1 || true
adb connect "127.0.0.1:${REDROID_HOST_ADB_PORT}" >/dev/null 2>&1 || true
adb -s "127.0.0.1:${REDROID_HOST_ADB_PORT}" install -r "$TELEGRAM_X_APK_PATH"
EOF_TGX
  chmod +x /usr/local/bin/install-telegram-x
}

start_redroid_and_optionally_install_tgx() {
  [ "$START_REDROID_NOW" = "1" ] || return 0
  log "Starting redroid container"
  /usr/local/bin/start-redroid
  sleep 5

  if [ "$INSTALL_ADB" = "1" ]; then
    log "Connecting adb to redroid"
    /usr/local/bin/connect-redroid-adb "$REDROID_HOST_ADB_PORT" || true
  fi

  if [ "$INSTALL_TELEGRAM_X_NOW" = "1" ]; then
    log "Downloading and installing Telegram X into redroid"
    TELEGRAM_X_DOWNLOAD_DIR="$TELEGRAM_X_DOWNLOAD_DIR" \
    TELEGRAM_X_APK_PATH="$TELEGRAM_X_APK_PATH" \
    REDROID_HOST_ADB_PORT="$REDROID_HOST_ADB_PORT" \
    /usr/local/bin/install-telegram-x || warn "Telegram X install failed; you can rerun /usr/local/bin/install-telegram-x later"
  fi
}

print_summary() {
  cat <<EOF_SUM

Bootstrap finished.

Key paths / commands:
  Docker service:         docker
  redroid start:          /usr/local/bin/start-redroid
  redroid adb connect:    /usr/local/bin/connect-redroid-adb $REDROID_HOST_ADB_PORT
  Telegram X install:     /usr/local/bin/install-telegram-x
  Appium start helper:    /usr/local/bin/start-appium-redroid
  Android SDK root:       $ANDROID_SDK_ROOT_DIR
  redroid data dir:       $REDROID_DATA_DIR
  redroid adb port:       $REDROID_HOST_ADB_PORT
  Appium status URL:      http://$APPIUM_BIND_ADDR:$APPIUM_PORT/status

Quick checks:
  docker ps
  adb connect 127.0.0.1:$REDROID_HOST_ADB_PORT
  adb devices
  java -version
  node -v && npm -v
  appium -v

EOF_SUM
}

main() {
  require_root
  source_os_release
  ARCH="$(normalize_arch)"
  INIT_SYSTEM="$(get_init_system)"

  case "$ID" in
    ubuntu|debian)
      DISTRO_FAMILY="deb"
      ;;
    centos|rhel|rocky|almalinux)
      DISTRO_FAMILY="rpm"
      ;;
    alpine)
      DISTRO_FAMILY="alpine"
      ;;
    *)
      if [[ "${ID_LIKE:-}" == *debian* ]]; then
        DISTRO_FAMILY="deb"
      elif [[ "${ID_LIKE:-}" == *rhel* ]] || [[ "${ID_LIKE:-}" == *fedora* ]]; then
        DISTRO_FAMILY="rpm"
      else
        err "Unsupported distro family: ID=$ID ID_LIKE=${ID_LIKE:-unknown}"
        exit 1
      fi
      ;;
  esac

  log "Detected: ID=$ID VERSION_ID=${VERSION_ID:-unknown} ARCH=$ARCH INIT=$INIT_SYSTEM"

  install_common_packages
  install_docker
  install_java
  install_node
  install_adb
  install_appium
  setup_kernel_for_redroid
  write_redroid_helpers
  start_redroid_and_optionally_install_tgx
  print_summary
}

main "$@"
