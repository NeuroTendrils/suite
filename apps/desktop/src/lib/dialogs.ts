import { ask } from "@tauri-apps/plugin-dialog";

/** Ask before an action that would drop unapplied rejection marks. Resolves true when there
 *  is nothing to lose or the user chose to discard. Falls back to window.confirm outside Tauri. */
export async function confirmDiscardMarks(pendingCount: number): Promise<boolean> {
  if (!pendingCount) return true;
  const msg = `You have ${pendingCount} unapplied mark${pendingCount === 1 ? "" : "s"} on this recording. Switching will discard ${pendingCount === 1 ? "it" : "them"}. Nothing has been written yet.`;
  try {
    return await ask(msg, {
      title: "Discard unapplied marks?",
      kind: "warning",
      okLabel: "Discard marks",
      cancelLabel: "Keep editing",
    });
  } catch {
    return window.confirm(msg);
  }
}
