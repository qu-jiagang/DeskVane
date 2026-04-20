#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
DIST_DIR="${DIST_DIR:-${ROOT_DIR}/dist/pyinstaller}"
APP_NAME="${DESKVANE_APP_NAME:-DeskVane}"
DMG_PATH="${DMG_PATH:-${ROOT_DIR}/dist/${APP_NAME}.dmg}"
ICON_FILE="${DESKVANE_ICON_FILE:-}"
PYTHON_BIN="${PYTHON:-python3}"

usage() {
    cat <<EOF
Usage: ./scripts/build-macos.sh [options]

Options:
  --python <path>    Python interpreter to use
  --icon <path>      Optional .icns file for the app bundle
  --onefile          Build a single-file executable instead of .app
  --help             Show this help message
EOF
}

ONEFILE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)
            PYTHON_BIN="$2"
            shift 2
            ;;
        --icon)
            ICON_FILE="$2"
            shift 2
            ;;
        --onefile)
            ONEFILE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown option: %s\n' "$1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
    printf 'This script is intended to run on macOS.\n' >&2
    exit 1
fi

BUILD_ARGS=(--target-os macos --python "$PYTHON_BIN")
if [[ -n "$ICON_FILE" ]]; then
    BUILD_ARGS+=(--icon "$ICON_FILE")
fi
if [[ "$ONEFILE" == "1" ]]; then
    BUILD_ARGS+=(--onefile)
fi

"${ROOT_DIR}/scripts/build-pyinstaller.sh" "${BUILD_ARGS[@]}"

if [[ "$ONEFILE" == "1" ]]; then
    exit 0
fi

APP_PATH="${DIST_DIR}/${APP_NAME}.app"
if [[ ! -d "$APP_PATH" ]]; then
    printf 'Expected app bundle was not created: %s\n' "$APP_PATH" >&2
    exit 1
fi

if ! command -v hdiutil >/dev/null 2>&1; then
    printf 'Built app bundle: %s\n' "$APP_PATH"
    printf 'Skipping DMG creation because hdiutil is unavailable. See packaging/macos/README.md\n'
    exit 0
fi

mkdir -p "$(dirname "$DMG_PATH")"
rm -f "$DMG_PATH"
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$APP_PATH" \
    -ov \
    -format UDZO \
    "$DMG_PATH" >/dev/null

printf 'Built app bundle: %s\n' "$APP_PATH"
printf 'Built DMG: %s\n' "$DMG_PATH"
