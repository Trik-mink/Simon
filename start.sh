#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$HOME/miniconda3/bin/python3"

echo "Starting Simon — Projected Copilot"

BACKEND_PID=""
WEB_PID=""

cleanup() {
  if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "$WEB_PID" ]; then
    kill "$WEB_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# FastAPI backend
CAMERA_INDEX=2 "$PYTHON" -m uvicorn server.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# React web panel
(cd "$ROOT_DIR/web" && npm run dev -- --port 5173) &
WEB_PID=$!

sleep 1

# Projector engine (foreground — quit this to stop everything)
export GLOVE_BLE="${GLOVE_BLE:-false}"
"$PYTHON" -m projected_copilot.app --windowed "$@"
