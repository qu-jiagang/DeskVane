#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON:-python3}"
SPEC_FILE="${ROOT_DIR}/packaging/pyinstaller/deskvane.spec"
DIST_DIR="${DIST_DIR:-${ROOT_DIR}/dist/pyinstaller}"
WORK_DIR="${WORK_DIR:-${ROOT_DIR}/build/pyinstaller}"
APP_NAME="${DESKVANE_APP_NAME:-DeskVane}"
APP_VERSION="$(
    "$PYTHON_BIN" - <<'PY'
from pathlib import Path
import re
text = Path("pyproject.toml").read_text(encoding="utf-8")
match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
if not match:
    raise SystemExit("Unable to read version from pyproject.toml")
print(match.group(1))
PY
)"

TARGET_OS="${DESKVANE_TARGET_OS:-}"
WINDOWED=1
ONEFILE=0
ICON_FILE="${DESKVANE_ICON_FILE:-}"

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'Missing required command: %s\n' "$1" >&2
        exit 1
    }
}

usage() {
    cat <<EOF
Usage: ./scripts/build-pyinstaller.sh [options]

Options:
  --target-os <linux|windows|macos>  Override target platform hint
  --onefile                          Build a single-file executable
  --console                          Keep console window enabled
  --icon <path>                      Optional platform icon file
  --python <path>                    Python interpreter to use
  --dist-dir <path>                  Output directory (default: ${DIST_DIR})
  --work-dir <path>                  PyInstaller work directory (default: ${WORK_DIR})
  -h, --help                         Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target-os)
            TARGET_OS="$2"
            shift 2
            ;;
        --onefile)
            ONEFILE=1
            shift
            ;;
        --console)
            WINDOWED=0
            shift
            ;;
        --icon)
            ICON_FILE="$2"
            shift 2
            ;;
        --python)
            PYTHON_BIN="$2"
            shift 2
            ;;
        --dist-dir)
            DIST_DIR="$2"
            shift 2
            ;;
        --work-dir)
            WORK_DIR="$2"
            shift 2
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

need_cmd "$PYTHON_BIN"

if [[ -z "$TARGET_OS" ]]; then
    case "$(uname -s)" in
        Darwin) TARGET_OS="macos" ;;
        MINGW*|MSYS*|CYGWIN*) TARGET_OS="windows" ;;
        *) TARGET_OS="linux" ;;
    esac
fi

if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
    printf '%s -m PyInstaller is required. Try: %s -m pip install -e .[packaging]\n' "$PYTHON_BIN" "$PYTHON_BIN" >&2
    exit 1
fi

mkdir -p "$DIST_DIR" "$WORK_DIR"

export DESKVANE_APP_NAME="$APP_NAME"
export DESKVANE_APP_VERSION="$APP_VERSION"
export DESKVANE_TARGET_OS="$TARGET_OS"
export DESKVANE_ONEFILE="$ONEFILE"
export DESKVANE_WINDOWED="$WINDOWED"

if [[ -n "$ICON_FILE" ]]; then
    export DESKVANE_ICON_FILE="$ICON_FILE"
fi

"$PYTHON_BIN" -m PyInstaller \
    --noconfirm \
    --clean \
    --distpath "$DIST_DIR" \
    --workpath "$WORK_DIR" \
    "$SPEC_FILE"

if [[ "$TARGET_OS" == "macos" ]]; then
    printf 'Built app bundle: %s\n' "${DIST_DIR}/${APP_NAME}.app"
elif [[ "$ONEFILE" == "1" ]]; then
    printf 'Built executable: %s\n' "${DIST_DIR}/${APP_NAME}"
else
    printf 'Built application directory: %s\n' "${DIST_DIR}/${APP_NAME}"
fi
