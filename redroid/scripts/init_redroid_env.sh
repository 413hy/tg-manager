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

INSTALL_DOCKER="${INSTALL_DOCKER:-1}"
INSTALL_ADB="${INSTALL_ADB:-1}"
INSTALL_JAVA="${INSTALL_JAVA:-1}"
INSTALL_NODE="${INSTALL_NODE:-1}"
INSTALL_APPIUM="${INSTALL_APPIUM:-1}"
SETUP_KERNEL="${SETUP_KERNEL:-1}"
INSTALL_SYSTEMD="${INSTALL_SYSTEMD:-1}"
START_REDROID_NOW="${START_REDROID_NOW:-0}"
START_APPIUM_NOW="${START_APPIUM_NOW:-0}"
INSTALL_TELEGRAM_X_NOW="${INSTALL_TELEGRAM_X_NOW:-0}"

source_os_release() {
  [ -r /etc/os-release ] || die "/etc/os-release not found"
  # shellcheck disable=SC1091
  . /etc/os-release
}

detect_family() {
  case "$ID" in
    ubuntu|debian) echo deb ;;
    centos|rhel|rocky|almalinux|fedora) echo rpm ;;
    alpine) echo alpine ;;
    *)
      case "${ID_LIKE:-}" in
        *debian*) echo deb ;;
        *rhel*|*fedora*) echo rpm ;;
        *) die "Unsupported distro: ID=$ID ID_LIKE=${ID_LIKE:-unknown}" ;;
      esac
      ;;
  esac
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

ensure_common_packages() {
  case "$DISTRO_FAMILY" in
    deb) pkg_install_apt ca-certificates curl gnupg jq unzip bash tar gzip coreutils grep sed gawk procps util-linux iproute2 lsof kmod netcat-openbsd ;;
    rpm) pkg_install_dnf ca-certificates curl gnupg2 jq unzip bash tar gzip coreutils grep sed gawk procps-ng util-linux iproute lsof kmod which findutils shadow-utils nc ;;
    alpine)
      if ! grep -Eq '^[^#].*/community$' /etc/apk/repositories; then
        sed -i 's|^#\(.*community\)$|\1|' /etc/apk/repositories 2>/dev/null || true
      fi
      pkg_install_apk ca-certificates curl jq unzip bash tar gzip coreutils grep sed gawk procps util-linux iproute2 lsof kmod shadow netcat-openbsd
      ;;
  esac
}

enable_service() {
  local svc="$1"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable "$svc" >/dev/null 2>&1 || true
    systemctl restart "$svc"
  elif command -v rc-update >/dev/null 2>&1; then
    rc-update add "$svc" default >/dev/null 2>&1 || true
    service "$svc" restart || service "$svc" start
  else
    warn "Unknown init system; start service manually: $svc"
  fi
}

install_docker() {
  [ "$INSTALL_DOCKER" = "1" ] || return 0
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    log "Docker is already available"
    return 0
  fi

  log "Installing Docker"
  case "$DISTRO_FAMILY" in
    deb)
      pkg_install_apt ca-certificates curl gnupg
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL "https://download.docker.com/linux/${ID}/gpg" | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
      chmod a+r /etc/apt/keyrings/docker.gpg
      codename="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"
      [ -n "$codename" ] || die "Unable to detect apt codename"
      printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/%s %s stable\n' \
        "$(dpkg --print-architecture)" "$ID" "$codename" > /etc/apt/sources.list.d/docker.list
      apt-get update -y
      apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      ;;
    rpm)
      need_cmd dnf
      dnf -y install dnf-plugins-core || true
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
}

install_java() {
  [ "$INSTALL_JAVA" = "1" ] || return 0
  command -v java >/dev/null 2>&1 && { log "Java is already available"; return 0; }
  log "Installing Java"
  case "$DISTRO_FAMILY" in
    deb) pkg_install_apt openjdk-21-jre-headless || pkg_install_apt openjdk-17-jre-headless || pkg_install_apt default-jre-headless ;;
    rpm) pkg_install_dnf java-21-openjdk-headless || pkg_install_dnf java-17-openjdk-headless || pkg_install_dnf java-17-openjdk ;;
    alpine) pkg_install_apk openjdk21-jre-headless || pkg_install_apk openjdk17-jre-headless ;;
  esac
}

install_node() {
  [ "$INSTALL_NODE" = "1" ] || return 0
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    log "Node.js and npm are already available"
    return 0
  fi
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
}

install_adb() {
  [ "$INSTALL_ADB" = "1" ] || return 0
  if command -v adb >/dev/null 2>&1; then
    log "adb is already available"
  else
    log "Installing adb"
    case "$DISTRO_FAMILY" in
      deb) pkg_install_apt adb ;;
      rpm) pkg_install_dnf android-tools ;;
      alpine) pkg_install_apk android-tools ;;
    esac
  fi
  install -d "$ANDROID_SDK_ROOT_DIR/platform-tools"
  ln -sf "$(command -v adb)" "$ANDROID_SDK_ROOT_DIR/platform-tools/adb"
  cat >/etc/profile.d/redroid-android-sdk.sh <<EOF_ENV
export ANDROID_HOME="$ANDROID_SDK_ROOT_DIR"
export ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT_DIR"
export PATH="\$PATH:$ANDROID_SDK_ROOT_DIR/platform-tools"
EOF_ENV
}

install_appium() {
  [ "$INSTALL_APPIUM" = "1" ] || return 0
  need_cmd npm
  if command -v appium >/dev/null 2>&1; then
    log "Appium is already available"
  else
    log "Installing Appium"
    npm i --location=global appium
  fi
  if ! appium driver list --installed 2>/dev/null | grep -q 'uiautomator2@'; then
    appium driver install uiautomator2
  fi
}

install_systemd_units() {
  [ "$INSTALL_SYSTEMD" = "1" ] || return 0
  command -v systemctl >/dev/null 2>&1 || { warn "systemd not found; skipping service install"; return 0; }
  log "Installing systemd units"
  install -m 0644 "$PROJECT_DIR/systemd/redroid-vps.service" /etc/systemd/system/redroid-vps.service
  install -m 0644 "$PROJECT_DIR/systemd/appium-redroid.service" /etc/systemd/system/appium-redroid.service
  systemctl daemon-reload
  systemctl enable redroid-vps.service >/dev/null 2>&1 || true
}

install_cli_links() {
  log "Installing helper command links"
  ln -sf "$PROJECT_DIR/scripts/manage.sh" /usr/local/bin/redroid-manager
  ln -sf "$PROJECT_DIR/scripts/start_redroid.sh" /usr/local/bin/start-redroid
  ln -sf "$PROJECT_DIR/scripts/connect_adb.sh" /usr/local/bin/connect-redroid-adb
  ln -sf "$PROJECT_DIR/scripts/install_telegram_x.sh" /usr/local/bin/install-telegram-x
  ln -sf "$PROJECT_DIR/scripts/start_appium.sh" /usr/local/bin/start-appium-redroid
}

main() {
  source_os_release
  DISTRO_FAMILY="$(detect_family)"
  log "Detected distro family: $DISTRO_FAMILY"
  ensure_common_packages
  install_docker
  install_java
  install_node
  install_adb
  install_appium
  [ "$SETUP_KERNEL" = "1" ] && "$PROJECT_DIR/scripts/setup_kernel.sh"
  install_cli_links
  install_systemd_units

  [ "$START_REDROID_NOW" = "1" ] && "$PROJECT_DIR/scripts/start_redroid.sh"
  [ "$INSTALL_TELEGRAM_X_NOW" = "1" ] && "$PROJECT_DIR/scripts/install_telegram_x.sh"
  [ "$START_APPIUM_NOW" = "1" ] && "$PROJECT_DIR/scripts/start_appium.sh"

  cat <<EOF_SUMMARY

Bootstrap finished.

Config:       $ENV_FILE
Manager:      redroid-manager
Start:        redroid-manager start
Healthcheck:  redroid-manager status
ADB:          ssh -L $REDROID_HOST_ADB_PORT:127.0.0.1:$REDROID_HOST_ADB_PORT root@YOUR_VPS_IP
Appium:       ssh -L $APPIUM_PORT:127.0.0.1:$APPIUM_PORT root@YOUR_VPS_IP

EOF_SUMMARY
}

main "$@"
