#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
VENV_BIN_DIR="${VENV_DIR}/bin"
VENV_PYTHON="${VENV_BIN_DIR}/python"
VENV_PIP="${VENV_BIN_DIR}/pip"
VENV_APP="${VENV_BIN_DIR}/deskvane"
LAUNCHER_DIR="${HOME}/.local/bin"
LAUNCHER_PATH="${LAUNCHER_DIR}/deskvane"

AUTO_START=false
COPY_DESKTOP=false
INSTALL_SYSTEM_DEPS=true

usage() {
    cat <<'EOF'
Usage: ./scripts/install.sh [options]

Options:
  --autostart         Install autostart desktop entry.
  --desktop           Copy launcher to ~/Desktop/.
  --skip-system-deps  Do not auto-install apt packages.
  -h, --help          Show this help.

This installer is intended for Debian/Ubuntu-like systems.
It will create .venv, install DeskVane, create ~/.local/bin/deskvane,
and register a desktop entry.
EOF
}

log() {
    printf '[install] %s\n' "$*"
}

have_cmd() {
    command -v "$1" >/dev/null 2>&1
}

need_sudo() {
    [ "$(id -u)" -ne 0 ]
}

apt_install() {
    if need_sudo; then
        sudo apt-get install -y "$@"
    else
        apt-get install -y "$@"
    fi
}

install_system_deps() {
    if ! have_cmd apt-get; then
        log "Skipping system dependency install: apt-get not found."
        return
    fi

    local packages=(
        python3-venv
        python3-tk
        libnotify-bin
        xclip
        python3-gi
        gir1.2-ayatanaappindicator3-0.1
    )

    log "Installing system packages: ${packages[*]}"
    if need_sudo && ! have_cmd sudo; then
        log "sudo not found. Re-run as root, install dependencies manually, or pass --skip-system-deps."
        exit 1
    fi

    if need_sudo; then
        sudo apt-get update
    else
        apt-get update
    fi
    apt_install "${packages[@]}"
}

create_launcher() {
    mkdir -p "$LAUNCHER_DIR"
    cat > "$LAUNCHER_PATH" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${VENV_APP}" "\$@"
EOF
    chmod +x "$LAUNCHER_PATH"
    log "Launcher installed: ${LAUNCHER_PATH}"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --autostart) AUTO_START=true ;;
        --desktop) COPY_DESKTOP=true ;;
        --skip-system-deps) INSTALL_SYSTEM_DEPS=false ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown option: %s\n\n' "$1" >&2
            usage
            exit 1
            ;;
    esac
    shift
done

if $INSTALL_SYSTEM_DEPS; then
    install_system_deps
fi

log "Creating virtual environment: ${VENV_DIR}"
/usr/bin/python3 -m venv --system-site-packages "$VENV_DIR"

log "Upgrading pip tooling"
"$VENV_PIP" install -U pip setuptools wheel

log "Installing DeskVane"
"$VENV_PIP" install "$ROOT_DIR"

create_launcher

DESKTOP_ARGS=()
$AUTO_START && DESKTOP_ARGS+=(--autostart)
$COPY_DESKTOP && DESKTOP_ARGS+=(--desktop)

log "Installing desktop entry"
"${ROOT_DIR}/scripts/install-desktop-entry.sh" "${DESKTOP_ARGS[@]}"

cat <<EOF

DeskVane has been installed.

Launch from terminal:
  ${LAUNCHER_PATH}

Launch from desktop:
  Search for "DeskVane" in your application menu.
EOF
