/** In-memory stand-in for the Python backend, behind the same `suiteCall` boundary.
 *  Response shapes follow backend/src/suite_backend/ipc/handlers/*. Only the commands
 *  the UI sends are implemented; anything else throws like the real allowlist would. */

type Rec = {
  id: string;
  name: string | null;
  source_format: string | null;
  sampling_rate: number | null;
  duration: number | null;
  streams: Array<{ id: string; modality: string; sfreq: number | null; n_channels: number }>;
  validation_ok: boolean | null;
  validation_errors: number;
  validation_warnings: number;
  sync_group_ids: string[];
};
type Run = { id: string; name: string; recordings: Rec[] };
type Session = { id: string; name: string; runs: Run[] };
type Subject = { id: string; label: string; metadata: Record<string, unknown>; sessions: Session[] };

export type FakeStudy = {
  id: string;
  name: string;
  task_name: string | null;
  created_at: string;
  subjects: Subject[];
  epochsets: Array<{ id: string; name: string; recording_id: string; n_trials: number; event_names: string[]; tmin: number; tmax: number; created_at: string }>;
  plans: Array<{ id: string; name: string; version: number; created_at: string; steps: Array<{ operation: string; parameters?: Record<string, unknown> }> }>;
  datasets: Array<{ id: string; name: string; source: string; n_samples: number; n_features: number; label_names: string[]; modalities: string[]; created_at: string }>;
  splits: Array<{
    id: string;
    dataset_id: string;
    method: string;
    train_indices: number[];
    val_indices: number[];
    test_indices: number[];
    train_subjects: string[];
    test_subjects: string[];
    leakage_check: { ok: boolean; warnings: string[] };
    parameters: Record<string, unknown>;
    created_at: string;
  }>;
  experiments: Array<{
    id: string;
    template_id: string | null;
    input_artifact_id: string | null;
    metrics: Record<string, unknown> | null;
    model: { model_id?: string } | null;
    split_id: string | null;
    leakage_check: { ok?: boolean; warnings?: string[] } | null;
    created_at: string;
  }>;
  annotations: Array<{ id: string; recording_id: string; start: number; end: number }>;
  badChannels: Record<string, string[]>;
};

export type Call = { command: string; params: Record<string, any> };
type Handler = (p: Record<string, any>) => unknown;

const CHANNELS = ["Fz", "Cz", "Pz"];

export class FakeBackend {
  studies: FakeStudy[] = [];
  calls: Call[] = [];
  /** command → transport-level failure (what a Rust/IPC error looks like: a rejected string). */
  transportErrors: Record<string, string> = {};
  /** command → `{status:"error", message}` returned inside a successful reply. */
  statusErrors: Record<string, string> = {};
  /** command → promise the handler waits on before answering (to hold an operation "running"). */
  gates: Partial<Record<string, Promise<void>>> = {};
  /** Per-call failure hook; return a message to fail that call at transport level. */
  failWhen: ((c: Call) => string | null) | null = null;
  inspect: Record<string, Record<string, unknown>> = {};
  private seq = 0;
  private clock = Date.parse("2026-01-01T00:00:00Z");

  id(prefix: string): string {
    this.seq += 1;
    return `${prefix}_${String(this.seq).padStart(4, "0")}`;
  }

  now(): string {
    this.clock += 60_000;
    return new Date(this.clock).toISOString();
  }

  callsOf(command: string): Call[] {
    return this.calls.filter((c) => c.command === command);
  }

  /** Hold `command` until the returned release() is called. */
  hold(command: string): () => void {
    let release!: () => void;
    this.gates[command] = new Promise<void>((r) => (release = r));
    return () => {
      delete this.gates[command];
      release();
    };
  }

  /** Calls not yet answered. Tests wait for this to reach 0. */
  inflight = 0;

  async call(command: string, params: Record<string, any> = {}): Promise<unknown> {
    this.inflight += 1;
    try {
      return await this.answer(command, params);
    } finally {
      this.inflight -= 1;
    }
  }

  private async answer(command: string, params: Record<string, any>): Promise<unknown> {
    const c = { command, params: JSON.parse(JSON.stringify(params)) };
    this.calls.push(c);
    // Real IPC replies arrive after React has had a chance to render; answering in a
    // microtask would hide ordering bugs (e.g. selecting an id before the reload lands).
    await new Promise((r) => setTimeout(r, 1));
    if (this.gates[command]) await this.gates[command];
    const viaHook = this.failWhen?.(c);
    if (viaHook) throw viaHook;
    if (this.transportErrors[command]) throw this.transportErrors[command];
    if (this.statusErrors[command]) return { status: "error", message: this.statusErrors[command] };
    const h = this.handlers[command];
    if (!h) throw `unknown command: ${command}`;
    return h(params);
  }

  // ── Seeding helpers (bypass the call log) ──────────────────────────────────
  addStudy(name: string, task_name: string | null = null): FakeStudy {
    const s: FakeStudy = {
      id: this.id("study"),
      name,
      task_name,
      created_at: this.now(),
      subjects: [],
      epochsets: [],
      plans: [],
      datasets: [],
      splits: [],
      experiments: [],
      annotations: [],
      badChannels: {},
    };
    this.studies.push(s);
    return s;
  }

  addSubject(study: FakeStudy, label: string, metadata: Record<string, unknown> = {}): Subject {
    const sub: Subject = {
      id: this.id("sub"),
      label,
      metadata,
      sessions: [{ id: this.id("ses"), name: "ses-01", runs: [{ id: this.id("run"), name: "run-01", recordings: [] }] }],
    };
    study.subjects.push(sub);
    return sub;
  }

  addRecording(study: FakeStudy, subject: Subject, extra: Partial<Rec> = {}): Rec {
    const rec: Rec = {
      id: this.id("rec"),
      name: null,
      source_format: "fif",
      sampling_rate: 250,
      duration: 30,
      streams: [{ id: this.id("stream"), modality: "eeg", sfreq: 250, n_channels: CHANNELS.length }],
      validation_ok: null,
      validation_errors: 0,
      validation_warnings: 0,
      sync_group_ids: [],
      ...extra,
    };
    subject.sessions[0].runs[0].recordings.push(rec);
    return rec;
  }

  addEpochset(study: FakeStudy, recording_id: string, event_names = ["A", "B"]) {
    const e = { id: this.id("epo"), name: "epochs", recording_id, n_trials: 12, event_names, tmin: -0.2, tmax: 0.8, created_at: this.now() };
    study.epochsets.push(e);
    return e;
  }

  addDataset(study: FakeStudy, name = "dataset") {
    const d = { id: this.id("ds"), name, source: "epochs", n_samples: 12, n_features: 30, label_names: ["A", "B"], modalities: ["eeg"], created_at: this.now() };
    study.datasets.push(d);
    return d;
  }

  addSplit(study: FakeStudy, dataset_id: string) {
    const s = {
      id: this.id("split"),
      dataset_id,
      method: "stratified_trial",
      train_indices: [0, 1, 2, 3, 4, 5, 6, 7],
      val_indices: [8],
      test_indices: [9, 10, 11],
      train_subjects: [],
      test_subjects: [],
      leakage_check: { ok: true, warnings: [] },
      parameters: { seed: 0 },
      created_at: this.now(),
    };
    study.splits.push(s);
    return s;
  }

  addExperiment(study: FakeStudy, dataset_id: string, split_id: string, model: { model_id?: string } | null = {}) {
    const x = {
      id: this.id("exp"),
      template_id: "eegnet",
      input_artifact_id: dataset_id,
      metrics: model?.model_id ? { train_accuracy: 1 } : {},
      model,
      split_id,
      leakage_check: { ok: true, warnings: [] },
      created_at: this.now(),
    };
    study.experiments.push(x);
    return x;
  }

  addPlan(study: FakeStudy, name: string) {
    const p = { id: this.id("plan"), name, version: 1, created_at: this.now(), steps: [{ operation: "filter", parameters: { l_freq: 1 } }] };
    study.plans.push(p);
    return p;
  }

  // ── Lookups ───────────────────────────────────────────────────────────────
  study(id: string): FakeStudy {
    const s = this.studies.find((x) => x.id === id);
    if (!s) throw `study not found: ${id}`;
    return s;
  }

  private recordings(s: FakeStudy) {
    return s.subjects.flatMap((sub) => sub.sessions.flatMap((ses) => ses.runs.flatMap((run) => run.recordings.map((rec) => ({ sub, ses, run, rec })))));
  }

  rec(s: FakeStudy, id: string): Rec {
    const r = this.recordings(s).find((x) => x.rec.id === id);
    if (!r) throw `recording not found: ${id}`;
    return r.rec;
  }

  /** Like the backend: the run must belong to the session, and the session to the subject. */
  private target(s: FakeStudy, p: Record<string, any>): Run {
    const sub = s.subjects.find((x) => x.id === p.subject_id);
    if (!sub) throw `subject not found: ${p.subject_id}`;
    const ses = sub.sessions.find((x) => x.id === p.session_id);
    if (!ses) throw `session ${p.session_id} not found in subject ${sub.id}`;
    const run = ses.runs.find((x) => x.id === p.run_id);
    if (!run) throw `run ${p.run_id} not found in session ${ses.id}`;
    return run;
  }

  private summary(s: FakeStudy) {
    return { id: s.id, name: s.name, task_name: s.task_name, schema_version: 1, created_at: s.created_at, subjects: s.subjects.map((x) => ({ id: x.id, label: x.label })) };
  }

  private manager(s: FakeStudy) {
    return {
      study_id: s.id,
      name: s.name,
      schema_version: 1,
      task_name: s.task_name,
      subjects: s.subjects.map((sub) => ({
        id: sub.id,
        label: sub.label,
        metadata: sub.metadata,
        sessions: sub.sessions.map((ses) => ({
          id: ses.id,
          name: ses.name,
          runs: ses.runs.map((run) => ({
            id: run.id,
            name: run.name,
            recordings: run.recordings.map((r) => ({
              id: r.id,
              name: r.name,
              source_format: r.source_format,
              sampling_rate: r.sampling_rate,
              duration: r.duration,
              channel_count: CHANNELS.length,
              modalities: r.streams.map((st) => st.modality),
              stream_ids: r.streams.map((st) => st.id),
              streams: r.streams.map((st) => ({ ...st, name: null, units: null, normalized: true })),
              preprocessing_state: null,
              validation_ok: r.validation_ok,
              validation_errors: r.validation_errors,
              validation_warnings: r.validation_warnings,
              sync_group_ids: r.sync_group_ids,
              sync_confidence: null,
            })),
          })),
        })),
      })),
      totals: {
        subjects: s.subjects.length,
        streams: this.recordings(s).reduce((n, r) => n + r.rec.streams.length, 0),
        recordings: this.recordings(s).length,
      },
    };
  }

  handlers: Record<string, Handler> = {
    health: () => ({ status: "ok", version: "test" }),
    "studies.list": () => ({ studies: this.studies.map((s) => this.summary(s)) }),
    "studies.create": (p) => this.summary(this.addStudy(p.name, p.task_name ?? null)),
    "studies.manager": (p) => this.manager(this.study(p.study_id)),
    "subjects.add": (p) => {
      const s = this.study(p.study_id);
      const sub = this.addSubject(s, p.label, p.metadata ?? {});
      return { study_id: s.id, subject: { id: sub.id, label: sub.label }, session_id: sub.sessions[0].id, run_id: sub.sessions[0].runs[0].id };
    },
    "insight.capture": (p) => {
      if (!p.consent_to_record) return { status: "error", message: "Consent required" };
      const path = `/workspace/${p.study_id}/captures/insight.csv`;
      this.inspect[path] = { format: "emotiv_insight", status: "needs_config", self_describing: false, required_config: ["sfreq"], sfreq: 128, warnings: [] };
      return { status: "ok", path, warnings: [], n_samples: p.seconds * 128 };
    },
    "study.export": (p) => ({ status: "ok", path: "/workspace/exports/study.zip", bytes: 1024, deidentified: p.deidentify, include_samples: p.include_samples }),
    "import.inspect": (p) => this.inspect[p.path] ?? { format: "fif", status: "ok", self_describing: true, sfreq: 250, warnings: [] },
    "import.stream.inspect": (p) => this.inspect[p.path] ?? { format: "csv", status: "ok", suggested_modality: "gyroscope", sfreq: 100 },
    "import.recording": (p) => {
      const s = this.study(p.study_id);
      const run = this.target(s, p);
      const rec: Rec = {
        id: this.id("rec"),
        name: null,
        source_format: String(p.path).split(".").pop() ?? null,
        sampling_rate: p.sfreq ?? 250,
        duration: 30,
        streams: [{ id: this.id("stream"), modality: "eeg", sfreq: p.sfreq ?? 250, n_channels: CHANNELS.length }],
        validation_ok: null,
        validation_errors: 0,
        validation_warnings: 0,
        sync_group_ids: [],
      };
      run.recordings.push(rec);
      return { recording: { id: rec.id }, stream: { id: rec.streams[0].id, modality: "eeg" } };
    },
    "import.stream": (p) => {
      const s = this.study(p.study_id);
      const run = this.target(s, p);
      let rec: Rec;
      if (p.recording_id) {
        const found = run.recordings.find((r) => r.id === p.recording_id);
        if (!found) throw `recording ${p.recording_id} not found in run ${run.id}`;
        rec = found;
      } else {
        rec = { id: this.id("rec"), name: null, source_format: null, sampling_rate: null, duration: null, streams: [], validation_ok: null, validation_errors: 0, validation_warnings: 0, sync_group_ids: [] };
        run.recordings.push(rec);
      }
      const st = { id: this.id("stream"), modality: p.modality, sfreq: p.sfreq, n_channels: 3 };
      rec.streams.push(st);
      return { recording: { id: rec.id }, stream: { id: st.id, modality: p.modality } };
    },
    "sync.list": () => ({ sync_groups: [] }),
    "recordings.timeline": (p) => {
      const s = this.study(p.study_id);
      const rec = this.rec(s, p.recording_id);
      const n = 40;
      const times = Array.from({ length: n }, (_, i) => p.start + (i / (n - 1)) * p.duration);
      const bad = s.badChannels[rec.id] ?? [];
      return {
        recording_id: rec.id,
        start: p.start,
        duration: p.duration,
        streams: [
          {
            stream_id: rec.streams[0]?.id ?? "stream",
            modality: "eeg",
            name: null,
            offset_sec: 0,
            channels: CHANNELS,
            channel_status: CHANNELS.map((c) => (bad.includes(c) ? "bad" : "good")),
            times,
            data: CHANNELS.map((_, ci) => times.map((t) => Math.sin(t * (ci + 1)))),
          },
        ],
        events: s.annotations
          .filter((a) => a.recording_id === rec.id)
          .map((a) => ({ name: "BAD_manual", timestamp: a.start, end: a.end, kind: "annotation", artifact: true, id: a.id })),
        sync: null,
      };
    },
    "validate.recording": (p) => {
      const rec = this.rec(this.study(p.study_id), p.recording_id);
      rec.validation_ok = true;
      return { ok: true, blocking_errors: [], warnings: [] };
    },
    "validate.study": () => ({ ok: true, blocking_errors: [], warnings: [] }),
    "artifacts.apply": (p) => {
      const s = this.study(p.study_id);
      const a = { id: this.id("ann"), recording_id: p.recording_id, start: p.suggestion.start, end: p.suggestion.end };
      s.annotations.push(a);
      return { annotation: a };
    },
    "artifacts.revert": (p) => {
      const s = this.study(p.study_id);
      s.annotations = s.annotations.filter((a) => a.id !== p.annotation_id);
      return { reverted: p.annotation_id };
    },
    "channels.update": (p) => {
      const s = this.study(p.study_id);
      const cur = new Set(s.badChannels[p.recording_id] ?? []);
      if (p.bad) cur.add(p.channel_name);
      else cur.delete(p.channel_name);
      s.badChannels[p.recording_id] = [...cur];
      return { recording: { id: p.recording_id } };
    },
    "events.list": () => ({ events: [] }),
    "plans.list": (p) => ({ plans: this.study(p.study_id).plans }),
    "plans.default": (p) => ({ plan: this.addPlan(this.study(p.study_id), "default") }),
    "plans.execute": (p) => ({ plan_id: p.plan_id, artifacts: [{ id: this.id("art"), operation: "filter" }] }),
    "epochs.list": (p) => {
      const s = this.study(p.study_id);
      return { epochsets: s.epochsets.filter((e) => !p.recording_id || e.recording_id === p.recording_id) };
    },
    "epochs.create": (p) => {
      const e = this.addEpochset(this.study(p.study_id), p.recording_id);
      return { epochset: e, n_trials: e.n_trials };
    },
    "features.list": () => ({ featuresets: [] }),
    "analysis.list": () => ({ reports: [] }),
    "datasets.list": (p) => ({ datasets: this.study(p.study_id).datasets }),
    "datasets.build": (p) => ({ dataset: this.addDataset(this.study(p.study_id), `dataset-${p.epochset_id}`) }),
    "datasets.splits.list": (p) => ({ splits: this.study(p.study_id).splits }),
    "datasets.splits.create": (p) => ({ split: this.addSplit(this.study(p.study_id), p.dataset_id) }),
    "neurostudio.experiments.list": (p) => ({ experiments: this.study(p.study_id).experiments }),
    "neurostudio.experiments.create": (p) => {
      const x = this.addExperiment(this.study(p.study_id), p.input_artifact_id, p.split_definition.split_id);
      return { experiment: x, leakage_check: { ok: true, warnings: [] } };
    },
    "neurostudio.train.start": (p) => {
      const x = this.study(p.study_id).experiments.find((e) => e.id === p.experiment_id);
      if (!x) throw `experiment not found: ${p.experiment_id}`;
      x.model = { model_id: `model_${x.id}` };
      return { status: "ok", n_train: 8, classes: ["A", "B"] };
    },
    "neurostudio.infer.run": (p) => {
      const x = this.study(p.study_id).experiments.find((e) => e.id === p.experiment_id);
      if (!x?.model?.model_id) return { status: "error", message: "no model" };
      return {
        status: "ok",
        labels: ["A", "B", "A"],
        proba: [[0.92, 0.08], [0.35, 0.65], [0.97, 0.03]],
        confidence: [0.92, 0.65, 0.97],
        classes: ["A", "B"],
        true_labels: ["A", "A", "A"],
        indices: [9, 10, 11],
        split: p.split ?? "all",
        model_kind: "sklearn",
        template_id: "sklearn_logreg",
        runs_locally: true,
      };
    },
    "neurostudio.eval.run": (p) => {
      const x = this.study(p.study_id).experiments.find((e) => e.id === p.experiment_id);
      if (!x?.model?.model_id) return { status: "error", message: "experiment has no trained model" };
      return {
        status: "ok",
        result: { experiment_id: x.id },
        metrics: { split: p.split, accuracy: 0.75, f1_macro: 0.7, n: 4, classes: ["A", "B"], confusion_matrix: [[2, 0], [1, 1]] },
      };
    },
  };
}
