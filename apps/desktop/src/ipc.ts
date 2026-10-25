import { invoke, isTauri } from "@tauri-apps/api/core";

function hasTauriInternals(): boolean {
  const internals = (window as Window & {
    __TAURI_INTERNALS__?: { invoke?: unknown };
  }).__TAURI_INTERNALS__;
  return typeof internals?.invoke === "function";
}

/** Wait briefly for the Tauri IPC bridge (dev WebView can race on first paint). */
export async function waitForSuiteRuntime(timeoutMs = 8000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (isTauri() && hasTauriInternals()) return;
    await new Promise((r) => setTimeout(r, 50));
  }
  throw new Error(
    "Tauri IPC is not available. Run `npm run tauri:dev` and use the NeuroTendrils Suite desktop window — not a browser tab on localhost:5173.",
  );
}

/** Allowlisted Suite command bridge. UI never sends free-form code. */
export async function suiteCall<T = unknown>(
  command: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  if (!hasTauriInternals()) {
    await waitForSuiteRuntime();
  }
  return invoke<T>("suite_call", { command, params });
}

/** Call one of the Rust robot-driver commands (`robot_*`, see src-tauri/src/robot). */
export async function robotCall<T = unknown>(command: string, args: Record<string, unknown> = {}): Promise<T> {
  if (!hasTauriInternals()) {
    await waitForSuiteRuntime();
  }
  return invoke<T>(command, args);
}
