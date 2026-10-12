/** Pure helpers for study state. No React, no IPC — unit-tested in tests/. */

export type ManagerStream = {
  id: string;
  name: string | null;
  modality: string;
  sfreq: number | null;
  n_channels: number;
  units: string | null;
  normalized: boolean;
};

export type ManagerRec = {
  id: string;
  name: string | null;
  source_format: string | null;
  sampling_rate: number | null;
  duration: number | null;
  channel_count?: number | null;
  modalities: string[];
  stream_ids: string[];
  streams: ManagerStream[];
  preprocessing_state?: string | null;
  validation_ok: boolean | null;
  validation_errors: number;
  validation_warnings: number;
  sync_group_ids: string[];
  sync_confidence: number | null;
};

export type Manager = {
  study_id: string;
  name: string;
  schema_version: number;
  task_name?: string | null;
  subjects: Array<{
    id: string;
    label: string;
    metadata: Record<string, unknown>;
    sessions: Array<{
      id: string;
      name: string;
      runs: Array<{
        id: string;
        name: string;
        recordings: ManagerRec[];
      }>;
    }>;
  }>;
  totals: { subjects: number; streams: number; recordings: number };
};

export type RecordingRow = {
  rec: ManagerRec;
  subjectId: string;
  subjectLabel: string;
  sessionId: string;
  sessionName: string;
  runId: string;
  runName: string;
};

export function flattenRecordings(manager: Manager | null): RecordingRow[] {
  if (!manager) return [];
  const out: RecordingRow[] = [];
  for (const sub of manager.subjects) {
    for (const ses of sub.sessions) {
      for (const run of ses.runs) {
        for (const rec of run.recordings) {
          out.push({
            rec,
            subjectId: sub.id,
            subjectLabel: sub.label,
            sessionId: ses.id,
            sessionName: ses.name,
            runId: run.id,
            runName: run.name,
          });
        }
      }
    }
  }
  return out;
}

export function findRecording(manager: Manager | null, id: string | null): RecordingRow | null {
  if (!id) return null;
  return flattenRecordings(manager).find((r) => r.rec.id === id) ?? null;
}

/** Human label for a recording: subject · session/run · modalities. */
export function recordingLabel(row: RecordingRow): string {
  const mods = row.rec.modalities.length ? row.rec.modalities.join(" + ") : "no streams";
  return `${row.subjectLabel} · ${row.sessionName}/${row.runName} · ${mods}`;
}

export function validateStudyName(
  name: string,
  existing: Array<{ name: string }>,
): { ok: boolean; error?: string; warning?: string } {
  const trimmed = name.trim();
  if (!trimmed) return { ok: false, error: "Enter a study name." };
  if (trimmed.length > 120) return { ok: false, error: "Use 120 characters or fewer." };
  if (existing.some((s) => s.name.trim().toLowerCase() === trimmed.toLowerCase())) {
    return { ok: true, warning: "A study with this name already exists. Studies are tracked by ID, so both will be kept." };
  }
  return { ok: true };
}

export function validateSubjectLabel(
  label: string,
  existing: Array<{ label: string }>,
): { ok: boolean; error?: string } {
  const trimmed = label.trim();
  if (!trimmed) return { ok: false, error: "Enter a subject label, e.g. S001." };
  if (existing.some((s) => s.label === trimmed)) {
    return { ok: false, error: `Subject ${trimmed} already exists.` };
  }
  return { ok: true };
}

/** Parse optional JSON object metadata. Empty input is an empty object. */
export function parseMetadata(
  text: string,
): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  if (!text.trim()) return { ok: true, value: {} };
  try {
    const v: unknown = JSON.parse(text);
    if (!v || typeof v !== "object" || Array.isArray(v)) {
      return { ok: false, error: 'Metadata must be a JSON object, e.g. {"age": 24}.' };
    }
    return { ok: true, value: v as Record<string, unknown> };
  } catch {
    return { ok: false, error: 'Metadata is not valid JSON. Example: {"age": 24, "handedness": "R"}.' };
  }
}

/** Positive finite number from a text field, or an error message. */
export function parsePositive(text: string, what: string): { ok: true; value: number } | { ok: false; error: string } {
  const v = Number(text.trim());
  if (!text.trim() || !Number.isFinite(v) || v <= 0) {
    return { ok: false, error: `${what} must be a positive number.` };
  }
  return { ok: true, value: v };
}

/** Validation/test fractions for a split: each in (0, 1), sum < 1. */
export function validateSplitFractions(
  valText: string,
  testText: string,
): { ok: true; val: number; test: number } | { ok: false; error: string } {
  const val = Number(valText);
  const test = Number(testText);
  if (!Number.isFinite(val) || val < 0 || val >= 1) {
    return { ok: false, error: "Validation fraction must be between 0 and 1." };
  }
  if (!Number.isFinite(test) || test <= 0 || test >= 1) {
    return { ok: false, error: "Test fraction must be greater than 0 and less than 1." };
  }
  if (val + test >= 1) {
    return { ok: false, error: "Validation + test must leave data for training (sum below 1)." };
  }
  return { ok: true, val, test };
}

export function validateSeed(text: string): { ok: true; value: number } | { ok: false; error: string } {
  const v = Number(text);
  if (!text.trim() || !Number.isInteger(v) || v < 0) {
    return { ok: false, error: "Seed must be a non-negative integer." };
  }
  return { ok: true, value: v };
}

/** Sort newest-first by ISO `created_at`; items without it keep list order at the end. */
export function newestFirst<T extends { created_at?: string | null }>(items: T[]): T[] {
  return items
    .map((item, i) => ({ item, i, t: item.created_at ? Date.parse(item.created_at) : NaN }))
    .sort((a, b) => {
      const an = Number.isNaN(a.t);
      const bn = Number.isNaN(b.t);
      if (an && bn) return a.i - b.i;
      if (an) return 1;
      if (bn) return -1;
      return b.t - a.t;
    })
    .map((x) => x.item);
}

export type Gate = { ok: true } | { ok: false; reason: string };

/** Prerequisites for the Home actions. */
export function importGate(studySelected: boolean, online: boolean): Gate {
  if (!online) return { ok: false, reason: "The backend is offline." };
  if (!studySelected) return { ok: false, reason: "Create or select a study first." };
  return { ok: true };
}

export function trainGate(studySelected: boolean, online: boolean, recordings: number): Gate {
  if (!online) return { ok: false, reason: "The backend is offline." };
  if (!studySelected) return { ok: false, reason: "Create or select a study first." };
  if (recordings < 1) {
    return { ok: false, reason: "Import at least one recording. Models are trained on epochs from recordings." };
  }
  return { ok: true };
}

/** Next suggested action on Home, derived only from data that exists. */
export function nextStep(manager: Manager | null): { title: string; detail: string; action: "create" | "subject" | "import" | "inspect" } {
  if (!manager) {
    return {
      title: "Create a study",
      detail: "A study groups subjects, sessions, and recordings for one experiment.",
      action: "create",
    };
  }
  const rows = flattenRecordings(manager);
  if (!rows.length) {
    return {
      title: "Import a recording",
      detail: manager.subjects.length
        ? "Add EEG data to this study. The source file is copied in and never modified."
        : "Add EEG data. A subject is created for you, or add subjects first below.",
      action: "import",
    };
  }
  const unvalidated = rows.filter((r) => r.rec.validation_ok == null).length;
  if (unvalidated) {
    return {
      title: "Inspect and validate recordings",
      detail: `${unvalidated} of ${rows.length} recording${rows.length === 1 ? "" : "s"} not yet validated. Open one in NeuroFlow.`,
      action: "inspect",
    };
  }
  return {
    title: "Continue preprocessing or train a model",
    detail: "All recordings have a validation report. Preprocess in NeuroFlow or build datasets in NeuroStudio.",
    action: "inspect",
  };
}

export function formatDuration(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec)) return "—";
  if (sec < 60) return `${sec.toFixed(1)} s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec - m * 60);
  return `${m} min ${s.toString().padStart(2, "0")} s`;
}

/** An experiment is trained only once the backend has recorded a model id.
 *  `model` defaults to `{}` on the backend, which is truthy in JS. */
export function isTrained(x: { model?: { model_id?: string | null } | null } | null | undefined): boolean {
  return !!x?.model?.model_id;
}

export type StepStatus = "done" | "available" | "unavailable";

export type ActivityItem = { at: string; kind: string; label: string; detail?: string };

/** Recent study activity from real backend records only (anything with a `created_at`). */
export function recentActivity(
  sources: {
    epochsets?: Array<{ created_at?: string; name: string; n_trials: number }>;
    datasets?: Array<{ created_at?: string; name: string; n_samples: number; n_features: number }>;
    experiments?: Array<{ created_at?: string; id: string; model?: { model_id?: string | null } | null }>;
    plans?: Array<{ created_at?: string; name: string }>;
  },
  limit = 6,
): ActivityItem[] {
  const out: ActivityItem[] = [];
  for (const e of sources.epochsets ?? []) {
    if (e.created_at) out.push({ at: e.created_at, kind: "Epochs", label: e.name, detail: `${e.n_trials} trials` });
  }
  for (const d of sources.datasets ?? []) {
    if (d.created_at) out.push({ at: d.created_at, kind: "Dataset", label: d.name, detail: `${d.n_samples} × ${d.n_features}` });
  }
  for (const x of sources.experiments ?? []) {
    if (x.created_at) {
      out.push({ at: x.created_at, kind: "Experiment", label: x.id, detail: isTrained(x) ? "trained" : "not trained" });
    }
  }
  for (const p of sources.plans ?? []) {
    if (p.created_at) out.push({ at: p.created_at, kind: "Plan", label: p.name });
  }
  return newestFirst(out.map((a) => ({ ...a, created_at: a.at })))
    .slice(0, limit)
    .map(({ at, kind, label, detail }) => ({ at, kind, label, detail }));
}
