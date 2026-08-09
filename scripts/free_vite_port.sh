#!/usr/bin/env bash
# Free the Vite/Tauri dev port if a stale process is holding it.
set -euo pipefail
PORT="${1:-5173}"
if command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${PIDS}" ]]; then
    echo "Freeing port $PORT (pids: $PIDS)"
    # shellcheck disable=SC2086
    kill -9 $PIDS 2>/dev/null || true
    sleep 0.3
  fi
fi
