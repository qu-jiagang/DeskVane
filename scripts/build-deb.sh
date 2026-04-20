#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
BUILD_ROOT="${DIST_DIR}/deb-build"
APP_DIR="/opt/deskvane"
PYTHON_BIN="${PYTHON:-python3}"

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'Missing required command: %s\n' "$1" >&2
        exit 1
    }
}

need_cmd "$PYTHON_BIN"
need_cmd dpkg-deb

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    printf '%s -m pip is required to build the .deb package.\n' "$PYTHON_BIN" >&2
    exit 1
fi

readarray -t PKG_INFO < <(
    "$PYTHON_BIN" - <<'PY'
from pathlib import Path
import re

text = Path("pyproject.toml").read_text(encoding="utf-8")

def find_value(key: str) -> str:
    match = re.search(rf'^{key}\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit(f"Unable to read {key} from pyproject.toml")
    return match.group(1)

print(find_value("name"))
print(find_value("version"))
PY
)

PACKAGE_NAME="${PKG_INFO[0]}"
PACKAGE_VERSION="${PKG_INFO[1]}"
PACKAGE_ARCH="$(dpkg --print-architecture)"
PACKAGE_BASENAME="${PACKAGE_NAME}_${PACKAGE_VERSION}_${PACKAGE_ARCH}"
PKG_ROOT="${BUILD_ROOT}/${PACKAGE_BASENAME}"

rm -rf "$PKG_ROOT"
mkdir -p \
    "${PKG_ROOT}/DEBIAN" \
    "${PKG_ROOT}${APP_DIR}/lib" \
    "${PKG_ROOT}${APP_DIR}/bin" \
    "${PKG_ROOT}/usr/bin" \
    "${PKG_ROOT}/usr/share/applications" \
    "${PKG_ROOT}/usr/share/icons/hicolor/scalable/apps" \
    "${PKG_ROOT}/usr/share/icons/hicolor/512x512/apps"

"$PYTHON_BIN" -m pip install \
    --upgrade \
    --no-compile \
    --no-warn-script-location \
    --target "${PKG_ROOT}${APP_DIR}/lib" \
    "$ROOT_DIR"

cat > "${PKG_ROOT}${APP_DIR}/bin/deskvane" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/opt/deskvane"
export PYTHONPATH="${APP_DIR}/lib${PYTHONPATH:+:${PYTHONPATH}}"
exec /usr/bin/python3 -m deskvane "$@"
EOF
chmod 0755 "${PKG_ROOT}${APP_DIR}/bin/deskvane"

cat > "${PKG_ROOT}/usr/bin/deskvane" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec /opt/deskvane/bin/deskvane "$@"
EOF
chmod 0755 "${PKG_ROOT}/usr/bin/deskvane"

sed \
    -e "s/__VERSION__/${PACKAGE_VERSION}/g" \
    -e "s/__ARCH__/${PACKAGE_ARCH}/g" \
    "${ROOT_DIR}/packaging/debian/control.template" > "${PKG_ROOT}/DEBIAN/control"

install -m 0644 "${ROOT_DIR}/packaging/deskvane.desktop" \
    "${PKG_ROOT}/usr/share/applications/deskvane.desktop"
install -m 0644 "${ROOT_DIR}/deskvane/assets/deskvane-icon.svg" \
    "${PKG_ROOT}/usr/share/icons/hicolor/scalable/apps/deskvane.svg"
install -m 0644 "${ROOT_DIR}/deskvane/assets/deskvane-icon.png" \
    "${PKG_ROOT}/usr/share/icons/hicolor/512x512/apps/deskvane.png"
install -m 0755 "${ROOT_DIR}/packaging/debian/postinst" "${PKG_ROOT}/DEBIAN/postinst"
install -m 0755 "${ROOT_DIR}/packaging/debian/postrm" "${PKG_ROOT}/DEBIAN/postrm"

mkdir -p "$DIST_DIR"
dpkg-deb --root-owner-group --build "$PKG_ROOT" "${DIST_DIR}/${PACKAGE_BASENAME}.deb"

printf 'Built package: %s\n' "${DIST_DIR}/${PACKAGE_BASENAME}.deb"
