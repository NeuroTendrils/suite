#!/usr/bin/env bash
# Ensure Tauri externalBin path exists for dev (thin wrapper → venv).
# `build_sidecar.sh` replaces this with a real PyInstaller binary for shipping.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Venv only — do NOT call ensure_dev.sh (avoids recursion).
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing venv. Run ./scripts/ensure_dev.sh first." >&2
  exit 1
fi

export PATH="$HOME/.cargo/bin:$PATH"
TARGET="$(rustc -vV 2>/dev/null | awk '/^host:/{print $2}')"
if [[ -z "${TARGET}" ]]; then
  echo "rustc not found; source \$HOME/.cargo/env first" >&2
  exit 1
fi

OUT_DIR="$ROOT/apps/desktop/src-tauri/binaries"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/suite-backend-${TARGET}"

# Keep a real frozen binary if already built.
if [[ -f "$OUT" ]] && ! grep -q 'SUITE_DEV_SIDECAR_STUB' "$OUT" 2>/dev/null; then
  echo "Using existing sidecar binary: $OUT"
  exit 0
fi

cat > "$OUT" <<EOF
#!/usr/bin/env bash
# SUITE_DEV_SIDECAR_STUB
set -euo pipefail
exec "$PY" -m suite_backend "\$@"
EOF
chmod +x "$OUT"
echo "Dev sidecar stub ready: $OUT"
