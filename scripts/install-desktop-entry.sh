#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="${SCRIPT_DIR}/.venv/bin/deskvane"
LAUNCHER_BIN="${HOME}/.local/bin/deskvane"
ICON_SRC_SVG="${SCRIPT_DIR}/deskvane/assets/deskvane-icon.svg"
ICON_SRC_PNG="${SCRIPT_DIR}/deskvane/assets/deskvane-icon.png"
APP_ID="deskvane"
DESKTOP_FILE="${APP_ID}.desktop"
APPS_DIR="${HOME}/.local/share/applications"
ICON_THEME_DIR="${HOME}/.local/share/icons/hicolor"
ICON_SCALABLE_DIR="${ICON_THEME_DIR}/scalable/apps"
ICON_BITMAP_DIR="${ICON_THEME_DIR}/512x512/apps"
ICON_INDEX_FILE="${ICON_THEME_DIR}/index.theme"

usage() {
    echo "Usage: $0 [--autostart] [--desktop]"
    echo "  --autostart   Install to ~/.config/autostart/"
    echo "  --desktop     Copy to ~/Desktop/"
    exit 1
}

AUTOSTART=false
DESKTOP=false
for arg in "$@"; do
    case "$arg" in
        --autostart) AUTOSTART=true ;;
        --desktop) DESKTOP=true ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $arg"; usage ;;
    esac
done

EXEC_BIN="$LAUNCHER_BIN"
if [ ! -f "$EXEC_BIN" ]; then
    EXEC_BIN="$VENV_BIN"
fi

if [ ! -f "$EXEC_BIN" ]; then
    echo "Error: launcher not found."
    echo "Please install first: ./scripts/install.sh"
    exit 1
fi

if [ ! -f "$ICON_SRC_SVG" ] || [ ! -f "$ICON_SRC_PNG" ]; then
    echo "Error: icon assets not found under deskvane/assets/."
    exit 1
fi

mkdir -p "$APPS_DIR"
mkdir -p "$ICON_SCALABLE_DIR" "$ICON_BITMAP_DIR"

if [ ! -f "$ICON_INDEX_FILE" ]; then
cat > "$ICON_INDEX_FILE" <<EOF
[Icon Theme]
Name=Hicolor
Comment=Fallback icon theme
Directories=scalable/apps,512x512/apps

[scalable/apps]
Size=64
MinSize=16
MaxSize=1024
Type=Scalable
Context=Applications

[512x512/apps]
Size=512
Type=Fixed
Context=Applications
EOF
fi

cp "$ICON_SRC_SVG" "${ICON_SCALABLE_DIR}/${APP_ID}.svg"
cp "$ICON_SRC_PNG" "${ICON_BITMAP_DIR}/${APP_ID}.png"

cat > "${APPS_DIR}/${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Type=Application
Name=DeskVane
Comment=Linux tray-based aggregation toolbox
Exec=${EXEC_BIN}
Icon=${APP_ID}
Terminal=false
Categories=Utility;
StartupNotify=false
EOF

echo "Installed: ${APPS_DIR}/${DESKTOP_FILE}"
echo "Icon SVG:  ${ICON_SCALABLE_DIR}/${APP_ID}.svg"
echo "Icon PNG:  ${ICON_BITMAP_DIR}/${APP_ID}.png"

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q "${ICON_THEME_DIR}" || true
fi

if $AUTOSTART; then
    AUTOSTART_DIR="${HOME}/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"
    cp "${APPS_DIR}/${DESKTOP_FILE}" "${AUTOSTART_DIR}/${DESKTOP_FILE}"
    echo "Autostart: ${AUTOSTART_DIR}/${DESKTOP_FILE}"
fi

if $DESKTOP; then
    DESKTOP_DIR="${HOME}/Desktop"
    if [ -d "$DESKTOP_DIR" ]; then
        cp "${APPS_DIR}/${DESKTOP_FILE}" "${DESKTOP_DIR}/${DESKTOP_FILE}"
        chmod +x "${DESKTOP_DIR}/${DESKTOP_FILE}"
        echo "Desktop:   ${DESKTOP_DIR}/${DESKTOP_FILE}"
    else
        echo "Warning: ~/Desktop/ not found, skipping."
    fi
fi
