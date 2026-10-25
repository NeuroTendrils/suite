#!/usr/bin/env node
/** Ensure the repo-root Python venv exists and suite_backend is importable. */
import { existsSync } from "node:fs";
import { join } from "node:path";
import { findBasePython, ROOT, run, runOrExit, VENV, VENV_PYTHON } from "./dev_env.mjs";

if (!existsSync(VENV_PYTHON)) {
  console.log(`Creating Python venv at ${VENV}`);
  const [python, ...args] = findBasePython();
  runOrExit(python, [...args, "-m", "venv", VENV]);
}

if (!run(VENV_PYTHON, ["-c", "import suite_backend"], { capture: true }).ok) {
  console.log("Installing suite-backend into venv");
  runOrExit(VENV_PYTHON, ["-m", "pip", "install", "-U", "pip"]);
  runOrExit(VENV_PYTHON, ["-m", "pip", "install", "-e", `${join(ROOT, "backend")}[dev]`]);
}

const version = runOrExit(VENV_PYTHON, ["-c", "import suite_backend; print(suite_backend.__version__)"], {
  capture: true,
}).stdout.trim();
console.log(`Dev Python ready: ${VENV_PYTHON} (${version})`);
