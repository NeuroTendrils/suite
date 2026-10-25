#!/usr/bin/env node
/**
 * Ensure Tauri's externalBin path exists for dev. The placeholder is not run: the desktop
 * shell skips it and starts the repo venv instead. `build_sidecar.mjs` replaces it with a
 * real PyInstaller binary for shipping.
 */
import { chmodSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { BINARIES, IS_WINDOWS, isDevStub, sidecarPath, STUB_MARKER, VENV_PYTHON } from "./dev_env.mjs";

// Venv only — do NOT run ensure_dev.mjs (avoids recursion).
if (!existsSync(VENV_PYTHON)) {
  console.error("Missing venv. Run node scripts/ensure_dev.mjs first.");
  process.exit(1);
}

const out = sidecarPath();
mkdirSync(BINARIES, { recursive: true });

// Keep a real frozen binary if already built.
if (existsSync(out) && !isDevStub(out)) {
  console.log(`Using existing sidecar binary: ${out}`);
  process.exit(0);
}

if (IS_WINDOWS) {
  writeFileSync(out, `${STUB_MARKER}\r\nPlaceholder for Tauri externalBin; not an executable.\r\n`);
} else {
  writeFileSync(out, `#!/usr/bin/env bash\n# ${STUB_MARKER}\nset -euo pipefail\nexec "${VENV_PYTHON}" -m suite_backend "$@"\n`);
  chmodSync(out, 0o755);
}
console.log(`Dev sidecar stub ready: ${out}`);
