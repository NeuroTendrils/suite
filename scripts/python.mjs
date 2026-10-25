#!/usr/bin/env node
/** Run a stdlib-only Python script with whichever python is installed (python3, python, py). */
import { findBasePython, run } from "./dev_env.mjs";

const [python, ...args] = findBasePython();
process.exit(run(python, [...args, ...process.argv.slice(2)]).status);
