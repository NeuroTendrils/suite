import { invoke } from "@tauri-apps/api/core";

/** Allowlisted Suite command bridge. UI never sends free-form code. */
export async function suiteCall<T = unknown>(
  command: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  return invoke<T>("suite_call", { command, params });
}
