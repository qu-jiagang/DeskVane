#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/midea/GithubRepository/DeskVane"
DEPS_DIR="${ROOT_DIR}/.deskvane-deps"

export PYTHONPATH="${ROOT_DIR}:${DEPS_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
cd "$ROOT_DIR"
exec /usr/bin/python3 -m deskvane "$@"
