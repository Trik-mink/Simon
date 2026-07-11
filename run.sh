#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -x "$HOME/miniconda3/bin/python3" ]; then
  PYTHON="$HOME/miniconda3/bin/python3"
else
  PYTHON="python3"
fi

cd "$ROOT_DIR"

# Keyboard controls are the safe default. Enable the glove explicitly with:
#   GLOVE_BLE=true ./run.sh
export GLOVE_BLE="${GLOVE_BLE:-false}"

exec "$PYTHON" -m projected_copilot.app "$@"
