#!/usr/bin/env bash
# Build a PyInstaller sidecar binary for Tauri to spawn (no system Python required at runtime).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$ROOT/scripts/ensure_dev.sh"

PY="$ROOT/.venv/bin/python"
"$PY" -m pip install -U "pyinstaller>=6.0"

TARGET="$(rustc -vV | awk '/^host:/{print $2}')"
OUT_DIR="$ROOT/apps/desktop/src-tauri/binaries"
mkdir -p "$OUT_DIR"
NAME="suite-backend-${TARGET}"

echo "Building sidecar: $OUT_DIR/$NAME"
cd "$ROOT/backend"
rm -rf build/sidecar dist/sidecar
"$PY" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name "$NAME" \
  --distpath "$OUT_DIR" \
  --workpath "$ROOT/backend/build/sidecar" \
  --specpath "$ROOT/backend/build/sidecar" \
  --paths "$ROOT/backend/src" \
  --collect-all mne \
  --collect-all pydantic \
  --hidden-import suite_backend \
  --hidden-import suite_backend.ipc.handlers \
  "$ROOT/backend/src/suite_backend/__main__.py"

chmod +x "$OUT_DIR/$NAME"
echo "Sidecar ready: $OUT_DIR/$NAME"
echo "Tauri will prefer this binary over the venv when present."
