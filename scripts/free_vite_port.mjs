#!/usr/bin/env node
/** Free the Vite/Tauri dev port if a stale process is holding it. */
import { IS_WINDOWS, run } from "./dev_env.mjs";

const port = process.argv[2] ?? "5173";

function listeningPids() {
  if (IS_WINDOWS) {
    // netstat state names are localized, so match listeners by their 0.0.0.0:0 / [::]:0 peer.
    const { stdout } = run("netstat", ["-ano"], { capture: true });
    return stdout
      .split(/\r?\n/)
      .map((line) => line.trim().split(/\s+/))
      .filter(([proto, local, remote]) =>
        /^TCP/i.test(proto ?? "") && local?.endsWith(`:${port}`) && /^(0\.0\.0\.0|\[::\]):0$/.test(remote ?? ""),
      )
      .map((cols) => cols.at(-1));
  }
  const { stdout } = run("lsof", [`-tiTCP:${port}`, "-sTCP:LISTEN"], { capture: true });
  return stdout.split(/\s+/);
}

const pids = [...new Set(listeningPids())].filter((pid) => /^\d+$/.test(pid) && pid !== "0" && Number(pid) !== process.pid);
if (pids.length) {
  console.log(`Freeing port ${port} (pids: ${pids.join(" ")})`);
  for (const pid of pids) {
    if (IS_WINDOWS) run("taskkill", ["/PID", pid, "/F"], { capture: true });
    else {
      try {
        process.kill(Number(pid), "SIGKILL");
      } catch {
        /* already gone */
      }
    }
  }
  await new Promise((done) => setTimeout(done, 300));
}
