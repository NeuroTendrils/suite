import { suiteCall } from "../ipc";
import { backendFailure } from "./errors";

/** Call the backend; a `{status: "error"}` reply is raised as a failure.
 *  Use this for user-initiated commands. Read-only list loads call `suiteCall` directly. */
export async function exec<T = any>(command: string, params: Record<string, unknown> = {}): Promise<T> {
  const res = await suiteCall<T>(command, params);
  const fail = backendFailure(res);
  if (fail) throw new Error(fail);
  return res;
}
