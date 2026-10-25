#!/usr/bin/env node
/** Run a command with rustup's cargo bin on PATH: `node with_cargo.mjs tauri dev`. */
import { run } from "./dev_env.mjs";

const [command, ...args] = process.argv.slice(2);
process.exit(run(command, args).status);
