#!/usr/bin/env bash
# Ensure the repo-root Python venv exists and suite_backend is importable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "Creating Python venv at $VENV"
  python3 -m venv "$VENV"
fi

if ! "$PY" -c "import suite_backend" 2>/dev/null; then
  echo "Installing suite-backend into venv"
  "$PY" -m pip install -U pip
  "$PY" -m pip install -e "$ROOT/backend[dev]"
fi

echo "Dev Python ready: $PY ($("$PY" -c 'import suite_backend; print(suite_backend.__version__)'))"
