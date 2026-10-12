import { useEffect, useRef, useState } from "react";
import { describeError } from "../lib/errors";
import type { Busy, LogEntry, Notice } from "../components/ui";

/** User-facing operation state: the one running task, the notice bar, and the activity log. */
export function useOperations() {
  const [busy, setBusy] = useState<Busy | null>(null);
  const busyRef = useRef(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const logSeq = useRef(0);

  function log(level: LogEntry["level"], text: string, detail?: string) {
    logSeq.current += 1;
    const entry: LogEntry = { id: logSeq.current, at: Date.now(), level, text, detail };
    setLogEntries((prev) => [entry, ...prev].slice(0, 300));
  }

  function showError(context: string, e: unknown) {
    const f = describeError(e);
    setNotice({ kind: "error", title: `${context}: ${f.title}`, hint: f.hint, detail: f.detail });
    log("error", `${context} failed — ${f.title}`, f.detail);
  }

  /** Run one user-initiated operation. Only one runs at a time; the backend
   *  serializes calls anyway, so a second click would only queue a duplicate. */
  async function task<T>(label: string, fn: () => Promise<T>, done?: string | ((r: T) => string)): Promise<T | null> {
    if (busyRef.current) {
      setNotice({ kind: "info", title: "Another operation is still running", hint: "Wait for it to finish, then try again." });
      return null;
    }
    busyRef.current = true;
    setBusy({ label, startedAt: Date.now() });
    try {
      const r = await fn();
      const msg = typeof done === "function" ? done(r) : done;
      log("success", msg || `${label} — done`);
      if (msg) setNotice({ kind: "success", title: msg });
      return r;
    } catch (e) {
      showError(label, e);
      return null;
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  }

  // Confirmations fade on their own; errors and warnings stay until dismissed.
  useEffect(() => {
    if (!notice || (notice.kind !== "success" && notice.kind !== "info")) return;
    const t = window.setTimeout(() => setNotice((n) => (n === notice ? null : n)), 6000);
    return () => window.clearTimeout(t);
  }, [notice]);

  return {
    busy,
    notice,
    setNotice,
    logEntries,
    clearLog: () => setLogEntries([]),
    log,
    showError,
    task,
  };
}

export type Operations = ReturnType<typeof useOperations>;
