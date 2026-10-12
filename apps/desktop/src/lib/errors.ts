/** Turn raw IPC/backend failures into something a researcher can act on.
 *  The raw text is always kept in `detail` so nothing is hidden. */

export type FriendlyError = {
  title: string;
  hint?: string;
  detail: string;
};

/** Backend handlers sometimes report failure inside a successful IPC reply:
 *  `{ status: "error" | "not_implemented", message }`. Treat those as failures. */
export function backendFailure(result: unknown): string | null {
  if (!result || typeof result !== "object") return null;
  const r = result as { status?: unknown; message?: unknown };
  if (r.status === "error" || r.status === "not_implemented") {
    return typeof r.message === "string" && r.message
      ? r.message
      : `backend reported status "${String(r.status)}"`;
  }
  return null;
}

function rawMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  try {
    return JSON.stringify(e);
  } catch {
    return String(e);
  }
}

export function describeError(e: unknown): FriendlyError {
  const detail = rawMessage(e);
  const m = detail.toLowerCase();

  if (m.includes("tauri ipc is not available")) {
    return {
      title: "The desktop runtime is not available",
      hint: "Open the NeuroTendrils Suite desktop window (npm run tauri:dev), not a browser tab.",
      detail,
    };
  }
  if (m.includes("command not allowlisted")) {
    return {
      title: "This action is not enabled in this desktop build",
      hint: "Rebuild the desktop app so its command allowlist matches the backend.",
      detail,
    };
  }
  if (
    m.includes("python backend not running") ||
    m.includes("ipc connect") ||
    m.includes("connection refused") ||
    m.includes("no such file or directory (os error 2)")
  ) {
    return {
      title: "The analysis backend is not running",
      hint: "Restart the app. If it persists, run ./scripts/ensure_dev.sh and check the terminal output.",
      detail,
    };
  }
  if (
    m.includes("ipc read") &&
    (m.includes("timed out") || m.includes("temporarily unavailable") || m.includes("would block"))
  ) {
    return {
      title: "The backend did not answer within 120 seconds",
      hint: "Long operations may still finish in the background. Wait, then press Refresh to see the result.",
      detail,
    };
  }
  if (m.startsWith("invalid params")) {
    return {
      title: "The backend rejected the request parameters",
      hint: "Check the values you entered. Full validation details are below.",
      detail,
    };
  }
  if (m.includes("no epochset") || m.includes("create epochs first")) {
    return {
      title: "No epochs exist for this recording yet",
      hint: "In NeuroFlow → Plan, create epochs from events, then try again.",
      detail,
    };
  }
  if (m.includes("<2 classes") || m.includes("multi-condition")) {
    return {
      title: "Training needs at least two classes",
      hint: "Build the dataset from epochs that contain two or more event conditions.",
      detail,
    };
  }
  if (m.includes("no trained model") || m === "no model" || m.includes("no model to export")) {
    return {
      title: "This experiment has no trained model",
      hint: "Train the experiment first.",
      detail,
    };
  }
  if (m.includes("not found")) {
    return {
      title: "The requested item no longer exists",
      hint: "Press Refresh. It may have been removed from the workspace on disk.",
      detail,
    };
  }
  if (m.includes("unsupported") || m.includes("unknown format") || m.includes("cannot read")) {
    return {
      title: "This file could not be read",
      hint: "Supported EEG formats: FIF, EDF, BDF, GDF, EEGLAB .set, BrainVision .vhdr, CNT, MAT, and delimited text.",
      detail,
    };
  }
  return { title: "The operation failed", detail };
}

/** `import.inspect` reports unreadable files inside a successful reply
 *  (`status: "unreadable" | "error"` plus `error`). Turn that into an error. */
export function inspectProblem(info: { status?: string; error?: string; format?: string } | null | undefined): FriendlyError | null {
  if (!info) return null;
  const bad = info.status === "unreadable" || info.status === "error" || !!info.error;
  if (!bad) return null;
  const detail = info.error || `inspection status: ${info.status}`;
  if (/no importer can handle/i.test(detail)) {
    return {
      title: "This file type isn’t supported, or the file doesn’t exist",
      hint: "Check the path. Supported EEG formats: FIF, EDF, BDF, GDF, EEGLAB .set, BrainVision .vhdr, CNT, MAT, and delimited text.",
      detail,
    };
  }
  return {
    title: `The ${info.format ? info.format.toUpperCase() + " " : ""}file couldn’t be read`,
    hint: "It may be damaged, incomplete, or not actually in this format. Try re-exporting it from the acquisition software.",
    detail,
  };
}
