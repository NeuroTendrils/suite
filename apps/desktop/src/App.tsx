import { useEffect, useMemo, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { suiteCall, waitForSuiteRuntime } from "./ipc";
import "./App.css";

type StudySummary = {
  id: string;
  name: string;
  schema_version?: number;
  subjects: Array<{ id: string; label: string }>;
};

type ManagerStream = {
  id: string;
  name: string | null;
  modality: string;
  sfreq: number | null;
  n_channels: number;
  units: string | null;
  normalized: boolean;
};

type ManagerRec = {
  id: string;
  name: string | null;
  source_format: string | null;
  sampling_rate: number | null;
  duration: number | null;
  modalities: string[];
  stream_ids: string[];
  streams: ManagerStream[];
  validation_ok: boolean | null;
  validation_errors: number;
  validation_warnings: number;
  sync_group_ids: string[];
  sync_confidence: number | null;
};

type Manager = {
  study_id: string;
  name: string;
  schema_version: number;
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

type InspectInfo = {
  format?: string;
  status?: string;
  self_describing?: boolean;
  required_config?: string[];
  sfreq?: number;
  candidates?: Array<{ key: string; shape: number[] }>;
  suggested_data_key?: string;
  suggested_modality?: string;
  warnings?: string[];
  columns?: Array<{ index: number; name: string; role: string }>;
};

type SyncGroup = {
  id: string;
  recording_id: string;
  reference_stream_id: string;
  method: string;
  links: Array<{
    stream_id: string;
    offset_sec: number;
    method: string;
    manual: boolean;
    quality: Record<string, unknown>;
  }>;
  quality: Record<string, unknown>;
};

type Timeline = {
  recording_id: string;
  start: number;
  duration: number;
  streams: Array<{
    stream_id: string;
    modality: string;
    name: string | null;
    offset_sec: number;
    channels: string[];
    times: number[];
    data: number[][];
    error?: string;
  }>;
  events: Array<{ name: string; timestamp: number; modality?: string }>;
  sync: { sync_group_id: string; method: string } | null;
};

type Tab = "import" | "sync" | "validate" | "timeline";

function sparkline(times: number[], values: number[], w = 420, h = 48): string {
  if (!times.length || !values.length) return "";
  const minT = times[0];
  const maxT = times[times.length - 1] || minT + 1;
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const spanV = maxV - minV || 1;
  const pts = values
    .map((v, i) => {
      const x = ((times[i] - minT) / (maxT - minT || 1)) * (w - 4) + 2;
      const y = h - 2 - ((v - minV) / spanV) * (h - 4);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return pts;
}

function App() {
  const [status, setStatus] = useState("starting…");
  const [error, setError] = useState<string | null>(null);
  const [studies, setStudies] = useState<StudySummary[]>([]);
  const [studyName, setStudyName] = useState("Motor Imagery");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [manager, setManager] = useState<Manager | null>(null);
  const [selectedRecId, setSelectedRecId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("import");
  const [subjectLabel, setSubjectLabel] = useState("S001");
  const [subjectMeta, setSubjectMeta] = useState("{}");
  const [importPath, setImportPath] = useState("");
  const [inspect, setInspect] = useState<InspectInfo | null>(null);
  const [sfreq, setSfreq] = useState("250");
  const [dataKey, setDataKey] = useState("");
  const [transpose, setTranspose] = useState(false);
  const [montage, setMontage] = useState("");
  const [columns, setColumns] = useState<Array<{ index: number; name: string; role: string }>>(
    [],
  );
  const [extPath, setExtPath] = useState("");
  const [extInspect, setExtInspect] = useState<InspectInfo | null>(null);
  const [extModality, setExtModality] = useState("gyroscope");
  const [extSfreq, setExtSfreq] = useState("100");
  const [extUnits, setExtUnits] = useState("");
  const [extRecordingId, setExtRecordingId] = useState("");
  const [syncMethod, setSyncMethod] = useState("shared_triggers");
  const [syncGroups, setSyncGroups] = useState<SyncGroup[]>([]);
  const [offsetEdits, setOffsetEdits] = useState<Record<string, string>>({});
  const [validationJson, setValidationJson] = useState("");
  const [tlStart, setTlStart] = useState("0");
  const [tlDur, setTlDur] = useState("5");
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [log, setLog] = useState("");

  function appendLog(msg: string) {
    setLog((p) => `${msg}\n${p}`.slice(0, 4000));
  }

  const selectedRec: ManagerRec | null = useMemo(() => {
    if (!manager || !selectedRecId) return null;
    for (const sub of manager.subjects) {
      for (const ses of sub.sessions) {
        for (const run of ses.runs) {
          const rec = run.recordings.find((r) => r.id === selectedRecId);
          if (rec) return rec;
        }
      }
    }
    return null;
  }, [manager, selectedRecId]);

  async function loadManager(studyId: string) {
    const mgr = await suiteCall<Manager>("studies.manager", { study_id: studyId });
    setManager(mgr);
    if (selectedRecId) {
      const still =
        mgr.subjects.some((s) =>
          s.sessions.some((ses) =>
            ses.runs.some((r) => r.recordings.some((rec) => rec.id === selectedRecId)),
          ),
        ) ?? false;
      if (!still) setSelectedRecId(null);
    }
    return mgr;
  }

  async function refresh() {
    try {
      await waitForSuiteRuntime();
      const health = await suiteCall<{ status: string; version: string }>("health");
      setStatus(`backend ${health.status} v${health.version}`);
      const listed = await suiteCall<{ studies: StudySummary[] }>("studies.list");
      setStudies(listed.studies);
      const id = selectedId ?? listed.studies[0]?.id ?? null;
      if (!selectedId && id) setSelectedId(id);
      if (id) await loadManager(id);
      else setManager(null);
      setError(null);
    } catch (e) {
      setError(String(e));
      setStatus("offline");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (selectedRecId && selectedId) {
      void suiteCall<{ sync_groups: SyncGroup[] }>("sync.list", {
        study_id: selectedId,
        recording_id: selectedRecId,
      })
        .then((r) => setSyncGroups(r.sync_groups))
        .catch(() => setSyncGroups([]));
    } else {
      setSyncGroups([]);
    }
  }, [selectedRecId, selectedId, manager]);

  async function createStudy() {
    const s = await suiteCall<StudySummary>("studies.create", { name: studyName });
    setSelectedId(s.id);
    appendLog(`created study ${s.id}`);
    await refresh();
  }

  async function selectStudy(id: string) {
    setSelectedId(id);
    setSelectedRecId(null);
    setTimeline(null);
    await loadManager(id);
  }

  async function addSubject() {
    if (!selectedId) return;
    let metadata: Record<string, unknown> = {};
    try {
      metadata = JSON.parse(subjectMeta || "{}");
    } catch {
      setError("Subject metadata must be valid JSON");
      return;
    }
    await suiteCall("subjects.add", {
      study_id: selectedId,
      label: subjectLabel,
      metadata,
    });
    appendLog(`added subject ${subjectLabel}`);
    await refresh();
  }

  async function ensureSubjectSession() {
    if (!selectedId) throw new Error("no study");
    let study = await suiteCall<any>("studies.get", { study_id: selectedId });
    let subject =
      study.subjects.find((s: any) => s.label === subjectLabel) ?? study.subjects[0];
    if (!subject) {
      const added = await suiteCall<any>("subjects.add", {
        study_id: selectedId,
        label: subjectLabel || "S001",
      });
      subject = added.subject;
      study = await suiteCall<any>("studies.get", { study_id: selectedId });
      subject = study.subjects.find((s: any) => s.id === subject.id) ?? study.subjects[0];
    }
    return { subject, session: subject.sessions[0], run: subject.sessions[0].runs[0] };
  }

  async function browseImport() {
    const selected = await open({
      multiple: false,
      title: "Import EEG recording",
      filters: [
        {
          name: "EEG",
          extensions: [
            "fif",
            "edf",
            "bdf",
            "gdf",
            "set",
            "vhdr",
            "cnt",
            "mat",
            "txt",
            "csv",
            "tsv",
            "asc",
          ],
        },
      ],
    });
    if (typeof selected !== "string" || !selected) return;
    setImportPath(selected);
    try {
      const info = await suiteCall<InspectInfo>("import.inspect", { path: selected });
      setInspect(info);
      if (info.suggested_data_key) setDataKey(info.suggested_data_key);
      if (typeof info.sfreq === "number") setSfreq(String(info.sfreq));
      if (Array.isArray(info.columns)) {
        setColumns(
          info.columns.map((c) => ({
            index: Number(c.index),
            name: String(c.name),
            role: String(c.role ?? "eeg"),
          })),
        );
      } else setColumns([]);
      appendLog(`inspect ${info.format}: ${info.status}`);
    } catch (e) {
      setInspect(null);
      setError(String(e));
    }
  }

  async function importRecording() {
    if (!selectedId || !importPath) {
      setError("Select a study and file first");
      return;
    }
    try {
      const { subject, session, run } = await ensureSubjectSession();
      const payload: Record<string, unknown> = {
        study_id: selectedId,
        subject_id: subject.id,
        session_id: session.id,
        run_id: run.id,
        path: importPath,
      };
      const needs = new Set(inspect?.required_config || []);
      if (needs.has("sfreq") || inspect?.status === "needs_config") {
        const hz = Number(sfreq);
        if (!Number.isFinite(hz) || hz <= 0) {
          setError("This format requires sampling rate (Hz)");
          return;
        }
        payload.sfreq = hz;
      }
      if (needs.has("data_key")) {
        if (!dataKey) {
          setError("MAT import requires data_key");
          return;
        }
        payload.data_key = dataKey;
      }
      if (transpose) payload.transpose = true;
      if (montage) payload.montage = montage;
      if (columns.length) payload.column_selection = columns;
      const res = await suiteCall<any>("import.recording", payload);
      setSelectedRecId(res.recording.id);
      appendLog(`imported EEG ${res.recording.id}`);
      setError(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function browseExternal() {
    const selected = await open({
      multiple: false,
      title: "Import external modality",
      filters: [{ name: "Streams", extensions: ["txt", "csv", "tsv", "asc", "mat", "npy"] }],
    });
    if (typeof selected !== "string" || !selected) return;
    setExtPath(selected);
    try {
      const info = await suiteCall<InspectInfo>("import.stream.inspect", { path: selected });
      setExtInspect(info);
      if (info.suggested_modality) setExtModality(info.suggested_modality);
      appendLog(`stream inspect ${info.format}`);
    } catch (e) {
      setExtInspect(null);
      setError(String(e));
    }
  }

  async function importExternalStream() {
    if (!selectedId || !extPath) {
      setError("Select study and external file");
      return;
    }
    const hz = Number(extSfreq);
    if (!Number.isFinite(hz) || hz <= 0) {
      setError("External stream requires sfreq (Hz)");
      return;
    }
    try {
      const { subject, session, run } = await ensureSubjectSession();
      const payload: Record<string, unknown> = {
        study_id: selectedId,
        subject_id: subject.id,
        session_id: session.id,
        run_id: run.id,
        path: extPath,
        modality: extModality,
        sfreq: hz,
      };
      if (extUnits) payload.units = extUnits;
      const attach = extRecordingId || selectedRecId || "";
      if (attach) payload.recording_id = attach;
      const res = await suiteCall<any>("import.stream", payload);
      setSelectedRecId(res.recording.id);
      appendLog(`imported ${res.stream.modality} → ${res.recording.id}`);
      setError(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function createSync() {
    if (!selectedId || !selectedRecId) {
      setError("Select a recording first");
      return;
    }
    try {
      const res = await suiteCall<{ sync_group: SyncGroup }>("sync.create", {
        study_id: selectedId,
        recording_id: selectedRecId,
        method: syncMethod,
      });
      appendLog(`sync ${res.sync_group.id} method=${res.sync_group.method}`);
      setError(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function applyOffset(syncGroupId: string, streamId: string) {
    if (!selectedId) return;
    const raw = offsetEdits[streamId] ?? "0";
    const offset = Number(raw);
    if (!Number.isFinite(offset)) {
      setError("offset must be a number (seconds)");
      return;
    }
    try {
      await suiteCall("sync.set_offset", {
        study_id: selectedId,
        sync_group_id: syncGroupId,
        stream_id: streamId,
        offset_sec: offset,
      });
      appendLog(`offset ${streamId.slice(0, 8)}… = ${offset}s`);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function runValidate(scope: "recording" | "study") {
    if (!selectedId) return;
    try {
      if (scope === "study") {
        const report = await suiteCall<any>("validate.study", { study_id: selectedId });
        setValidationJson(JSON.stringify(report, null, 2));
        appendLog(`validate study ok=${report.ok}`);
      } else {
        if (!selectedRecId) {
          setError("Select a recording to validate");
          return;
        }
        const report = await suiteCall<any>("validate.recording", {
          study_id: selectedId,
          recording_id: selectedRecId,
        });
        setValidationJson(JSON.stringify(report, null, 2));
        appendLog(
          `validate recording ok=${report.ok} errors=${report.blocking_errors?.length ?? 0} warns=${report.warnings?.length ?? 0}`,
        );
      }
      setError(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function loadTimeline() {
    if (!selectedId || !selectedRecId) {
      setError("Select a recording");
      return;
    }
    try {
      const tl = await suiteCall<Timeline>("recordings.timeline", {
        study_id: selectedId,
        recording_id: selectedRecId,
        start: Number(tlStart) || 0,
        duration: Number(tlDur) || 5,
        max_points: 400,
      });
      setTimeline(tl);
      appendLog(
        `timeline ${tl.streams.length} streams · sync=${tl.sync?.method ?? "none"}`,
      );
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  const needsConfig = inspect?.status === "needs_config" || inspect?.self_describing === false;

  const recordingOptions =
    manager?.subjects.flatMap((sub) =>
      sub.sessions.flatMap((ses) =>
        ses.runs.flatMap((run) =>
          run.recordings.map((rec) => ({
            id: rec.id,
            label: `${sub.label}/${ses.name}/${run.name} · ${rec.modalities.join("+") || "?"} · ${rec.id.slice(0, 10)}`,
          })),
        ),
      ),
    ) ?? [];

  return (
    <div className="app">
      <header>
        <h1>NeuroTendrils Suite</h1>
        <span className="muted">{status}</span>
        <button type="button" onClick={() => void refresh()}>
          Refresh
        </button>
      </header>
      {error && <div className="error">{error}</div>}

      <div className="layout">
        <aside className="sidebar">
          <h2>Studies</h2>
          <div className="row">
            <input value={studyName} onChange={(e) => setStudyName(e.target.value)} />
            <button type="button" onClick={() => void createStudy()}>
              Create
            </button>
          </div>
          <ul className="study-list">
            {studies.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className={s.id === selectedId ? "active" : ""}
                  onClick={() => void selectStudy(s.id)}
                >
                  {s.name}
                  <span className="muted"> v{s.schema_version ?? 1}</span>
                </button>
              </li>
            ))}
          </ul>

          {manager && (
            <>
              <h2>
                Manager{" "}
                <span className="muted">
                  {manager.totals.subjects}s / {manager.totals.recordings}r /{" "}
                  {manager.totals.streams}str
                </span>
              </h2>
              <div className="row">
                <input
                  value={subjectLabel}
                  onChange={(e) => setSubjectLabel(e.target.value)}
                  placeholder="S001"
                  style={{ width: 70 }}
                />
                <input
                  value={subjectMeta}
                  onChange={(e) => setSubjectMeta(e.target.value)}
                  placeholder="{}"
                  style={{ flex: 1, minWidth: 0 }}
                />
                <button type="button" onClick={() => void addSubject()}>
                  +subj
                </button>
              </div>
              <div className="tree">
                {manager.subjects.map((sub) => (
                  <div key={sub.id} className="tree-sub">
                    <div className="tree-label">{sub.label}</div>
                    {sub.sessions.map((ses) =>
                      ses.runs.map((run) =>
                        run.recordings.map((rec) => (
                          <button
                            key={rec.id}
                            type="button"
                            className={`tree-rec ${rec.id === selectedRecId ? "active" : ""}`}
                            onClick={() => {
                              setSelectedRecId(rec.id);
                              setExtRecordingId(rec.id);
                            }}
                          >
                            <div>
                              {(rec.modalities.length ? rec.modalities : ["?"]).join("+")} ·{" "}
                              {rec.source_format ?? "—"}
                            </div>
                            <div className="muted tiny">
                              {rec.id.slice(0, 12)} · {rec.streams.length} streams
                              {rec.validation_ok === true
                                ? " · ok"
                                : rec.validation_ok === false
                                  ? " · FAIL"
                                  : ""}
                              {rec.sync_group_ids.length
                                ? ` · sync~${(rec.sync_confidence ?? 0).toFixed(2)}`
                                : " · no sync"}
                            </div>
                          </button>
                        )),
                      ),
                    )}
                    {!sub.sessions.some((s) => s.runs.some((r) => r.recordings.length)) && (
                      <div className="muted tiny">no recordings</div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>

        <main className="main">
          {!selectedId && <p className="muted">Create or select a study.</p>}
          {selectedId && (
            <>
              <div className="tabs">
                {(
                  [
                    ["import", "Import"],
                    ["sync", "Sync"],
                    ["validate", "Validate"],
                    ["timeline", "Timeline"],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    className={tab === id ? "active" : ""}
                    onClick={() => setTab(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {selectedRec && (
                <p className="rec-banner">
                  Recording <code>{selectedRec.id.slice(0, 16)}</code> ·{" "}
                  {selectedRec.modalities.join(", ") || "no modalities"} ·{" "}
                  {selectedRec.streams.length} streams
                </p>
              )}

              {tab === "import" && (
                <section>
                  <h2>Import EEG</h2>
                  <div className="row">
                    <button type="button" onClick={() => void browseImport()}>
                      Browse…
                    </button>
                    <input
                      style={{ flex: 1 }}
                      value={importPath}
                      onChange={(e) => setImportPath(e.target.value)}
                      placeholder="FIF/EDF/… or TXT/CSV/MAT"
                    />
                    <button
                      type="button"
                      onClick={() => void importRecording()}
                      disabled={!importPath}
                    >
                      Import EEG
                    </button>
                  </div>
                  {inspect && (
                    <div className="box">
                      <p>
                        <strong>{inspect.format}</strong> · {inspect.status}
                      </p>
                      {needsConfig && (
                        <div className="row">
                          <label>
                            sfreq{" "}
                            <input
                              style={{ width: 70 }}
                              value={sfreq}
                              onChange={(e) => setSfreq(e.target.value)}
                            />
                          </label>
                          {(inspect.format === "mat" ||
                            inspect.required_config?.includes("data_key")) && (
                            <label>
                              data_key{" "}
                              <select
                                value={dataKey}
                                onChange={(e) => setDataKey(e.target.value)}
                              >
                                <option value="">(choose)</option>
                                {(inspect.candidates || []).map((c) => (
                                  <option key={c.key} value={c.key}>
                                    {c.key} {JSON.stringify(c.shape)}
                                  </option>
                                ))}
                              </select>
                            </label>
                          )}
                          <label>
                            <input
                              type="checkbox"
                              checked={transpose}
                              onChange={(e) => setTranspose(e.target.checked)}
                            />{" "}
                            transpose
                          </label>
                          <label>
                            montage{" "}
                            <input
                              value={montage}
                              onChange={(e) => setMontage(e.target.value)}
                              placeholder="optional"
                            />
                          </label>
                        </div>
                      )}
                      {columns.length > 0 && (
                        <div className="chan-table-wrap">
                          <table className="chan-table">
                            <thead>
                              <tr>
                                <th>#</th>
                                <th>Label</th>
                                <th>Role</th>
                              </tr>
                            </thead>
                            <tbody>
                              {columns.map((col, i) => (
                                <tr key={col.index}>
                                  <td>{col.index + 1}</td>
                                  <td>
                                    <input
                                      value={col.name}
                                      onChange={(e) => {
                                        const name = e.target.value;
                                        setColumns((cols) =>
                                          cols.map((c, j) => (j === i ? { ...c, name } : c)),
                                        );
                                      }}
                                    />
                                  </td>
                                  <td>
                                    <select
                                      value={col.role}
                                      onChange={(e) => {
                                        const role = e.target.value;
                                        setColumns((cols) =>
                                          cols.map((c, j) => (j === i ? { ...c, role } : c)),
                                        );
                                      }}
                                    >
                                      <option value="eeg">EEG</option>
                                      <option value="misc">misc</option>
                                      <option value="stim">stim</option>
                                      <option value="time">time</option>
                                      <option value="ignore">ignore</option>
                                    </select>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}

                  <h2>Import external stream</h2>
                  <div className="row">
                    <button type="button" onClick={() => void browseExternal()}>
                      Browse…
                    </button>
                    <input
                      style={{ flex: 1 }}
                      value={extPath}
                      onChange={(e) => setExtPath(e.target.value)}
                      placeholder="gyro/ECG/… CSV/MAT/NPY"
                    />
                    <button
                      type="button"
                      onClick={() => void importExternalStream()}
                      disabled={!extPath}
                    >
                      Import stream
                    </button>
                  </div>
                  <div className="row">
                    <label>
                      modality{" "}
                      <select
                        value={extModality}
                        onChange={(e) => setExtModality(e.target.value)}
                      >
                        {[
                          "gyroscope",
                          "accelerometer",
                          "ecg",
                          "emg",
                          "eog",
                          "eye_tracking",
                          "motion",
                          "behavioral",
                          "trigger",
                          "gsr",
                          "respiration",
                          "misc",
                        ].map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      sfreq{" "}
                      <input
                        style={{ width: 70 }}
                        value={extSfreq}
                        onChange={(e) => setExtSfreq(e.target.value)}
                      />
                    </label>
                    <label>
                      units{" "}
                      <input
                        style={{ width: 80 }}
                        value={extUnits}
                        onChange={(e) => setExtUnits(e.target.value)}
                      />
                    </label>
                    <label>
                      attach to{" "}
                      <select
                        value={extRecordingId || selectedRecId || ""}
                        onChange={(e) => setExtRecordingId(e.target.value)}
                      >
                        <option value="">(new recording)</option>
                        {recordingOptions.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {extInspect && (
                    <p className="muted">
                      {extInspect.format} · suggested={extInspect.suggested_modality ?? "—"}
                    </p>
                  )}
                </section>
              )}

              {tab === "sync" && (
                <section>
                  <h2>Synchronization</h2>
                  <p className="muted">
                    Never assumes streams are aligned from similar start times. Use triggers,
                    timestamps, or manual offsets.
                  </p>
                  {!selectedRecId && <p className="muted">Select a recording in the manager.</p>}
                  {selectedRecId && (
                    <>
                      <div className="row">
                        <label>
                          method{" "}
                          <select
                            value={syncMethod}
                            onChange={(e) => setSyncMethod(e.target.value)}
                          >
                            <option value="shared_triggers">shared_triggers</option>
                            <option value="timestamps">timestamps</option>
                            <option value="manual_offset">manual_offset</option>
                          </select>
                        </label>
                        <button type="button" onClick={() => void createSync()}>
                          Create SyncGroup
                        </button>
                      </div>
                      {selectedRec && (
                        <ul className="plain">
                          {selectedRec.streams.map((s) => (
                            <li key={s.id}>
                              {s.modality} · {s.sfreq ?? "?"} Hz · {s.n_channels} ch ·{" "}
                              <code>{s.id.slice(0, 10)}</code>
                            </li>
                          ))}
                        </ul>
                      )}
                      {syncGroups.map((g) => (
                        <div key={g.id} className="box">
                          <p>
                            <strong>{g.id.slice(0, 14)}</strong> · {g.method} · assumed_sync=
                            {String(g.quality?.assumed_synchronized ?? false)} · conf=
                            {Number(g.quality?.mean_confidence ?? 0).toFixed(2)}
                          </p>
                          <table className="chan-table">
                            <thead>
                              <tr>
                                <th>stream</th>
                                <th>method</th>
                                <th>offset (s)</th>
                                <th></th>
                              </tr>
                            </thead>
                            <tbody>
                              {g.links.map((l) => (
                                <tr key={l.stream_id}>
                                  <td>
                                    <code>{l.stream_id.slice(0, 10)}</code>
                                    {l.manual ? " *" : ""}
                                  </td>
                                  <td>{l.method}</td>
                                  <td>
                                    <input
                                      style={{ width: 80 }}
                                      value={
                                        offsetEdits[l.stream_id] ?? String(l.offset_sec)
                                      }
                                      onChange={(e) =>
                                        setOffsetEdits((m) => ({
                                          ...m,
                                          [l.stream_id]: e.target.value,
                                        }))
                                      }
                                    />
                                  </td>
                                  <td>
                                    <button
                                      type="button"
                                      onClick={() => void applyOffset(g.id, l.stream_id)}
                                    >
                                      Set
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ))}
                      {!syncGroups.length && (
                        <p className="muted">No SyncGroups yet for this recording.</p>
                      )}
                    </>
                  )}
                </section>
              )}

              {tab === "validate" && (
                <section>
                  <h2>Validation</h2>
                  <div className="row">
                    <button type="button" onClick={() => void runValidate("recording")}>
                      Validate recording
                    </button>
                    <button type="button" onClick={() => void runValidate("study")}>
                      Validate study
                    </button>
                  </div>
                  {selectedRec && (
                    <p className="muted">
                      cached: ok={String(selectedRec.validation_ok)} · errors=
                      {selectedRec.validation_errors} · warnings=
                      {selectedRec.validation_warnings}
                    </p>
                  )}
                  <pre className="log">{validationJson || "Run validation to see report."}</pre>
                </section>
              )}

              {tab === "timeline" && (
                <section>
                  <h2>Multimodal timeline</h2>
                  <div className="row">
                    <label>
                      start{" "}
                      <input
                        style={{ width: 60 }}
                        value={tlStart}
                        onChange={(e) => setTlStart(e.target.value)}
                      />
                    </label>
                    <label>
                      duration{" "}
                      <input
                        style={{ width: 60 }}
                        value={tlDur}
                        onChange={(e) => setTlDur(e.target.value)}
                      />
                    </label>
                    <button type="button" onClick={() => void loadTimeline()}>
                      Load window
                    </button>
                  </div>
                  {timeline && (
                    <>
                      <p className="muted">
                        {timeline.start}–{(timeline.start + timeline.duration).toFixed(2)}s ·
                        sync={timeline.sync?.method ?? "none"} · events=
                        {timeline.events.length}
                      </p>
                      {timeline.streams.map((st) => {
                        const ch0 = st.data[0] || [];
                        const pts = sparkline(st.times, ch0);
                        return (
                          <div key={st.stream_id} className="track">
                            <div className="track-head">
                              <strong>{st.modality}</strong> · offset={st.offset_sec.toFixed(3)}s
                              · {st.channels[0] ?? "ch0"}
                              {st.error ? ` · ERR ${st.error}` : ""}
                            </div>
                            {pts ? (
                              <svg width={420} height={48} className="spark">
                                <polyline
                                  fill="none"
                                  stroke="#222"
                                  strokeWidth={1}
                                  points={pts}
                                />
                              </svg>
                            ) : (
                              <div className="muted tiny">no samples in window</div>
                            )}
                          </div>
                        );
                      })}
                      {timeline.events.length > 0 && (
                        <div className="box">
                          <strong>Events</strong>
                          <ul className="plain">
                            {timeline.events.slice(0, 40).map((e, i) => (
                              <li key={`${e.timestamp}-${i}`}>
                                {e.timestamp.toFixed(3)}s · {e.name} · {e.modality ?? ""}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </>
                  )}
                </section>
              )}
            </>
          )}

          <section>
            <h3>Log</h3>
            <pre className="log">{log || "—"}</pre>
          </section>
        </main>
      </div>
    </div>
  );
}

export default App;
