#!/usr/bin/env node
/** Build a PyInstaller sidecar binary for Tauri to spawn (no system Python required at runtime). */
import { chmodSync, mkdirSync, rmSync } from "node:fs";
import { basename, join } from "node:path";
import { BINARIES, IS_WINDOWS, ROOT, runOrExit, sidecarPath, VENV_PYTHON } from "./dev_env.mjs";

runOrExit(process.execPath, [join(ROOT, "scripts/ensure_dev.mjs")]);
// Do not run ensure_sidecar_stub here — we replace it with a frozen binary.
runOrExit(VENV_PYTHON, ["-m", "pip", "install", "-U", "pyinstaller>=6.0"]);

const out = sidecarPath();
// PyInstaller appends .exe itself on Windows.
const name = basename(out).replace(/\.exe$/, "");
mkdirSync(BINARIES, { recursive: true });

console.log(`Building sidecar: ${out}`);
const backend = join(ROOT, "backend");
rmSync(join(backend, "build/sidecar"), { recursive: true, force: true });
rmSync(join(backend, "dist/sidecar"), { recursive: true, force: true });
runOrExit(
  VENV_PYTHON,
  [
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name", name,
    "--distpath", BINARIES,
    "--workpath", join(backend, "build/sidecar"),
    "--specpath", join(backend, "build/sidecar"),
    "--paths", join(backend, "src"),
    "--collect-all", "mne",
    "--collect-all", "pydantic",
    "--hidden-import", "suite_backend",
    "--hidden-import", "suite_backend.ipc.handlers",
    join(backend, "src/suite_backend/__main__.py"),
  ],
  { cwd: backend },
);

if (!IS_WINDOWS) chmodSync(out, 0o755);
console.log(`Sidecar ready: ${out}`);
console.log("Tauri will prefer this binary over the venv when present.");
