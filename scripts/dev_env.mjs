/** Shared helpers for the cross-platform (macOS, Linux, Windows) dev scripts. */
import { spawnSync } from "node:child_process";
import { closeSync, openSync, readSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const IS_WINDOWS = process.platform === "win32";
export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const VENV = join(ROOT, ".venv");
export const VENV_PYTHON = IS_WINDOWS ? join(VENV, "Scripts", "python.exe") : join(VENV, "bin", "python");
export const BINARIES = join(ROOT, "apps/desktop/src-tauri/binaries");
/** Marks the dev placeholder sidecar; the desktop shell skips files that contain it. */
export const STUB_MARKER = "SUITE_DEV_SIDECAR_STUB";

/** process.env with rustup's cargo bin first on PATH (GUI-launched shells often lack it). */
export function cargoEnv() {
  const env = { ...process.env };
  // Windows spells it "Path"; adding a second "PATH" key would be ambiguous.
  const key = Object.keys(env).find((k) => k.toUpperCase() === "PATH") ?? "PATH";
  env[key] = [join(homedir(), ".cargo", "bin"), env[key]].filter(Boolean).join(delimiter);
  return env;
}

function quote(arg) {
  return /[\s"]/.test(arg) ? `"${arg.replace(/"/g, '\\"')}"` : arg;
}

/**
 * Run a command, inheriting stdio unless `capture` is set. On Windows, bare command
 * names go through the shell so `.cmd` shims (npm bins, flutter) resolve.
 */
export function run(command, args = [], { capture = false, env = cargoEnv(), cwd } = {}) {
  const shell = IS_WINDOWS && !/[\\/]/.test(command);
  const options = { cwd, env, stdio: capture ? "pipe" : "inherit", encoding: "utf8" };
  const result = shell
    ? spawnSync([command, ...args].map(quote).join(" "), { ...options, shell: true })
    : spawnSync(command, args, options);
  return { ok: !result.error && result.status === 0, status: result.status ?? 1, stdout: result.stdout ?? "" };
}

/** Run a step and exit with its status if it fails. */
export function runOrExit(command, args, options) {
  const result = run(command, args, options);
  if (!result.ok) {
    console.error(`Failed: ${command} ${args.join(" ")}`);
    process.exit(result.status || 1);
  }
  return result;
}

/** The base Python (3.11+) used to create the venv, as [command, ...args]. */
export function findBasePython() {
  const candidates = IS_WINDOWS ? [["python"], ["py", "-3"], ["python3"]] : [["python3"], ["python"]];
  const probe = "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)";
  for (const [command, ...args] of candidates) {
    if (run(command, [...args, "-c", probe], { capture: true }).ok) return [command, ...args];
  }
  console.error(
    "Python 3.11 or newer was not found on PATH." +
      (IS_WINDOWS ? ' Install it from python.org and tick "Add python.exe to PATH".' : ""),
  );
  process.exit(1);
}

/** rustc's host triple, e.g. aarch64-apple-darwin or x86_64-pc-windows-msvc. */
export function rustHost() {
  const result = run("rustc", ["-vV"], { capture: true });
  const host = result.ok && /^host:\s*(\S+)/m.exec(result.stdout)?.[1];
  if (!host) {
    console.error("rustc not found. Install Rust from https://rustup.rs and open a new terminal.");
    process.exit(1);
  }
  return host;
}

/** Path Tauri's externalBin expects for this host (Windows adds .exe). */
export function sidecarPath(host = rustHost()) {
  return join(BINARIES, `suite-backend-${host}${IS_WINDOWS ? ".exe" : ""}`);
}

/** True if the file starts with the dev placeholder marker (only the head is read). */
export function isDevStub(path) {
  let fd;
  try {
    fd = openSync(path, "r");
    const head = Buffer.alloc(256);
    return head.subarray(0, readSync(fd, head, 0, head.length, 0)).includes(STUB_MARKER);
  } catch {
    return false;
  } finally {
    if (fd !== undefined) closeSync(fd);
  }
}
