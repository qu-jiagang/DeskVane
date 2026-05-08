#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/midea/GithubRepository/DeskVane"
BINARY="${ROOT_DIR}/src-tauri/target/release/deskvane"
LOG_FILE="/tmp/deskvane-tauri-source.log"
FRONTEND_DIST="${ROOT_DIR}/frontend/dist/index.html"

{
  printf '\n[%s] starting DeskVane Tauri source\n' "$(date -Is)"
  printf 'DISPLAY=%s WAYLAND_DISPLAY=%s XDG_CURRENT_DESKTOP=%s\n' "${DISPLAY:-}" "${WAYLAND_DISPLAY:-}" "${XDG_CURRENT_DESKTOP:-}"
} >>"$LOG_FILE"

cd "$ROOT_DIR"
export PATH="/home/midea/.cargo/bin:${PATH}"

if [[ ! -f "$FRONTEND_DIST" ]] || find frontend/src frontend/index.html -newer "$FRONTEND_DIST" -print -quit | grep -q .; then
  npm --prefix frontend run build >>"$LOG_FILE" 2>&1
fi

if [[ ! -x "$BINARY" ]] || find src-tauri/src src-tauri/Cargo.toml src-tauri/tauri.conf.json frontend/dist -newer "$BINARY" -print -quit | grep -q .; then
  cargo tauri build --no-bundle >>"$LOG_FILE" 2>&1
fi

set +e
"$BINARY" "$@" >>"$LOG_FILE" 2>&1
status=$?
set -e
printf '[%s] DeskVane Tauri exited with status %s\n' "$(date -Is)" "$status" >>"$LOG_FILE"
exit "$status"
