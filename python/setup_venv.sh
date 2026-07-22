#!/usr/bin/env bash
# Create the local Python virtualenv used by NeuroTendrils workers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${NEUROTENDRILS_VENV:-$ROOT/.venv}"
REQUIREMENTS="$ROOT/python/requirements.txt"

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "error: python3 (or python) is required" >&2
  exit 1
fi

echo "Using interpreter: $PYTHON ($("$PYTHON" --version 2>&1))"
echo "Creating venv at: $VENV_DIR"

"$PYTHON" -m venv "$VENV_DIR"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$REQUIREMENTS"

echo
echo "Done. Activate with:"
echo "  source \"$VENV_DIR/bin/activate\""
echo "Or let the NeuroTendrils app discover $VENV_DIR automatically."
