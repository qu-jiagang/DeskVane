#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/midea/GithubRepository/DeskVane"
DEPS_DIR="${ROOT_DIR}/.deskvane-deps"

export DESKVANE_RUNTIME_PORT="${DESKVANE_RUNTIME_PORT:-37656}"
export DESKVANE_DISABLE_HOTKEYS=1
export DESKVANE_DISABLE_TRAY=1
export PYTHONPATH="${ROOT_DIR}:${DEPS_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

cd "$ROOT_DIR"
exec /usr/bin/python3 -m deskvane "$@"
