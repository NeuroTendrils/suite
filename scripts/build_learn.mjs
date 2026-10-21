#!/usr/bin/env node
/** Bundle the existing Flutter learner into the one desktop distribution. */
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "apps/neurolearn/app");
const target = join(root, "apps/desktop/public/learn");
const stamp = join(target, "desktop-build.json");
const args = ["build", "web", "--release", "--base-href", "/learn/", "--no-web-resources-cdn", "--csp"];

function hashInputs() {
  const hash = createHash("sha256").update(JSON.stringify(args));
  function visit(path) {
    for (const entry of readdirSync(path, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const file = join(path, entry.name);
      if (entry.isDirectory()) visit(file);
      else hash.update(relative(source, file)).update(readFileSync(file));
    }
  }
  for (const directory of ["lib", "assets", "web"]) visit(join(source, directory));
  for (const file of ["pubspec.yaml", "pubspec.lock"]) hash.update(readFileSync(join(source, file)));
  return hash.digest("hex");
}

const inputHash = hashInputs();
let current = false;
try {
  const build = JSON.parse(readFileSync(stamp, "utf8"));
  current = build.app === "neurolearn" && build.version === 1 && build.inputHash === inputHash &&
    ["index.html", "flutter_bootstrap.js", "main.dart.js", "canvaskit/canvaskit.wasm", "assets/assets/packs/bci-foundations/course.json"]
      .every((file) => existsSync(join(target, file)));
} catch { /* Missing or stale output is rebuilt below. */ }

if (current) {
  console.log("Embedded NeuroLearn is up to date.");
} else if (process.argv.includes("--check")) {
  console.error("Embedded NeuroLearn is missing or stale. Run npm run build:learn at the repository root.");
  process.exitCode = 1;
} else {
  console.log("Building NeuroLearn for the desktop app (including offline renderer assets)…");
  const result = spawnSync(process.platform === "win32" ? "flutter.bat" : "flutter", args, {
    cwd: source,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.error || result.status !== 0) {
    console.error(result.error?.message ?? "Flutter web build failed.");
    console.error("Install Flutter on PATH, then run npm run build:learn. The previous bundled learner has been retained.");
    process.exitCode = 1;
  } else {
    // Only generated output is replaced, after a successful build. Source and progress are untouched.
    rmSync(target, { recursive: true, force: true });
    mkdirSync(target, { recursive: true });
    cpSync(join(source, "build/web"), target, { recursive: true });
    for (const file of ["SourceSans3-OFL.txt", "Fraunces-OFL.txt"]) {
      cpSync(join(source, "assets/fonts", file), join(target, file));
    }
    // pub get may update the lock during a build; record the final input state.
    writeFileSync(stamp, JSON.stringify({ app: "neurolearn", version: 1, inputHash: hashInputs() }, null, 2) + "\n");
    console.log("NeuroLearn bundled into apps/desktop/public/learn.");
  }
}
