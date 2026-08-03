#!/usr/bin/env bash
# Build a NeuroTendrils desktop bundle with PyInstaller.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

echo "==> Using $PYTHON"
"$PYTHON" -c "import PyInstaller, PySide6; print('PyInstaller', PyInstaller.__version__); print('PySide6', PySide6.__version__)"

# Ensure app + workers are importable in the build env.
export PYTHONPATH="$ROOT/desktop:$ROOT/workers/neuroflow:$ROOT/workers/neurostudio${PYTHONPATH:+:$PYTHONPATH}"

echo "==> Cleaning previous build output"
rm -rf "$ROOT/build/neurotendrils" "$ROOT/dist/NeuroTendrils" "$ROOT/dist/NeuroTendrils.app"

echo "==> Running PyInstaller"
"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$ROOT/dist" \
  --workpath "$ROOT/build/neurotendrils" \
  "$ROOT/packaging/neurotendrils.spec"

echo "==> Done"
if [[ -d "$ROOT/dist/NeuroTendrils.app" ]]; then
  echo "App bundle: $ROOT/dist/NeuroTendrils.app"
  du -sh "$ROOT/dist/NeuroTendrils.app"
elif [[ -d "$ROOT/dist/NeuroTendrils" ]]; then
  echo "Onedir:     $ROOT/dist/NeuroTendrils"
  du -sh "$ROOT/dist/NeuroTendrils"
fi
