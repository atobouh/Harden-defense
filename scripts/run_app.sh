#!/usr/bin/env bash
# Lance le collecteur de logs + le dashboard.   ./scripts/run_app.sh   (Ctrl+C pour tout arrêter)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
trap 'kill 0' EXIT INT TERM
"$PY" -m harden.collector &
"$PY" -m harden.dashboard &
wait
