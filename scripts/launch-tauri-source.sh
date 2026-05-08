#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/midea/GithubRepository/DeskVane"
LOG_FILE="/tmp/deskvane-tauri-source-launcher.log"

{
  printf '\n[%s] launching DeskVane Tauri source wrapper\n' "$(date -Is)"
  printf 'DISPLAY=%s WAYLAND_DISPLAY=%s XDG_CURRENT_DESKTOP=%s\n' "${DISPLAY:-}" "${WAYLAND_DISPLAY:-}" "${XDG_CURRENT_DESKTOP:-}"
} >>"$LOG_FILE"

setsid "${ROOT_DIR}/scripts/run-tauri-source.sh" >>"$LOG_FILE" 2>&1 < /dev/null &
