import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { suiteCall, waitForSuiteRuntime } from "./ipc";
import "./App.css";

type StudySummary = {
  id: string;
  name: string;
  schema_version?: number;
  subjects: Array<{
    id: string;
    label: string;
    sessions: Array<{
      id: string;
      name: string;
      runs: Array<{ id: string; name: string; recordings: unknown[] }>;
    }>;
  }>;
};

type Tree = {
  study_id: string;
  name: string;
  schema_version: number;
  stream_count: number;
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
        recordings: Array<{
          id: string;
          modalities: string[];
          stream_ids: string[];
          channel_count?: number;
          sampling_rate?: number;
          source_format?: string;
        }>;
      }>;
    }>;
  }>;
};

type InspectInfo = {
  format?: string;
  status?: string;
  self_describing?: boolean;
  required_config?: string[];
  optional_config?: string[];
  sfreq?: number;
  n_channels?: number;
  n_cols?: number;
  n_rows?: number;
  candidates?: Array<{ key: string; shape: number[] }>;
  suggested_data_key?: string;
  warnings?: string[];
  columns?: Array<{ index: number; name: string; role: string }>;
  error?: string;
};

function App() {
  const [status, setStatus] = useState("starting…");
  const [error, setError] = useState<string | null>(null);
  const [studies, setStudies] = useState<StudySummary[]>([]);
  const [studyName, setStudyName] = useState("Motor Imagery");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tree, setTree] = useState<Tree | null>(null);
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
  const [extInspect, setExtInspect] = useState<InspectInfo & { suggested_modality?: string } | null>(
    null,
  );
  const [extModality, setExtModality] = useState("gyroscope");
  const [extSfreq, setExtSfreq] = useState("100");
  const [extUnits, setExtUnits] = useState("");
  const [extRecordingId, setExtRecordingId] = useState("");
  const [log, setLog] = useState("");

  function appendLog(msg: string) {
    setLog((p) => `${msg}\n${p}`.slice(0, 3500));
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
      if (id) setTree(await suiteCall<Tree>("studies.tree", { study_id: id }));
      else setTree(null);
      setError(null);
    } catch (e) {
      setError(String(e));
      setStatus("offline");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function createStudy() {
    const s = await suiteCall<StudySummary>("studies.create", { name: studyName });
    setSelectedId(s.id);
    appendLog(`created study ${s.id}`);
    await refresh();
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
      } else {
        setColumns([]);
      }
      appendLog(
        `inspect ${info.format}: status=${info.status} self_describing=${info.self_describing}`,
      );
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
      let study = await suiteCall<StudySummary>("studies.get", { study_id: selectedId });
      let subject = study.subjects.find((s) => s.label === subjectLabel) ?? study.subjects[0];
      if (!subject) {
        const added = await suiteCall<any>("subjects.add", {
          study_id: selectedId,
          label: subjectLabel || "S001",
        });
        subject = added.subject;
        study = await suiteCall<StudySummary>("studies.get", { study_id: selectedId });
        subject = study.subjects.find((s) => s.id === subject.id) ?? study.subjects[0];
      }
      const session = subject.sessions[0];
      const run = session.runs[0];
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
          setError("MAT import requires data_key (array variable name)");
          return;
        }
        payload.data_key = dataKey;
      }
      if (transpose) payload.transpose = true;
      if (montage) payload.montage = montage;
      if (columns.length) payload.column_selection = columns;

      const res = await suiteCall<any>("import.recording", payload);
      appendLog(
        `imported recording ${res.recording.id} stream=${res.stream?.id} format=${res.recording.source_format}`,
      );
      setError(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  const needsConfig = inspect?.status === "needs_config" || !inspect?.self_describing;

  const recordingOptions =
    tree?.subjects.flatMap((sub) =>
      sub.sessions.flatMap((ses) =>
        ses.runs.flatMap((run) =>
          run.recordings.map((rec) => ({
            id: rec.id,
            label: `${sub.label}/${ses.name}/${run.name} · ${rec.id.slice(0, 12)} · ${(rec.modalities || []).join("+") || "?"}`,
          })),
        ),
      ),
    ) ?? [];

  async function browseExternal() {
    const selected = await open({
      multiple: false,
      title: "Import external modality stream",
      filters: [{ name: "Streams", extensions: ["txt", "csv", "tsv", "asc", "mat", "npy"] }],
    });
    if (typeof selected !== "string" || !selected) return;
    setExtPath(selected);
    try {
      const info = await suiteCall<InspectInfo & { suggested_modality?: string }>(
        "import.stream.inspect",
        { path: selected },
      );
      setExtInspect(info);
      if (info.suggested_modality) setExtModality(info.suggested_modality);
      appendLog(`stream inspect ${info.format}: suggested_modality=${info.suggested_modality ?? "—"}`);
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
      let study = await suiteCall<StudySummary>("studies.get", { study_id: selectedId });
      let subject = study.subjects.find((s) => s.label === subjectLabel) ?? study.subjects[0];
      if (!subject) {
        const added = await suiteCall<any>("subjects.add", {
          study_id: selectedId,
          label: subjectLabel || "S001",
        });
        subject = added.subject;
        study = await suiteCall<StudySummary>("studies.get", { study_id: selectedId });
        subject = study.subjects.find((s) => s.id === subject.id) ?? study.subjects[0];
      }
      const session = subject.sessions[0];
      const run = session.runs[0];
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
      if (extRecordingId) payload.recording_id = extRecordingId;
      const res = await suiteCall<any>("import.stream", payload);
      appendLog(
        `imported ${res.stream.modality} stream ${res.stream.id} on recording ${res.recording.id}`,
      );
      setError(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="app">
      <header>
        <h1>NeuroTendrils Suite</h1>
        <span className="muted">{status}</span>
      </header>
      <p className="muted">
        Phase 3 — External modality streams (gyro/accel/ECG/…). Explicit modality + sfreq; attach to
        a recording or create a new one.
      </p>
      {error && <div className="error">{error}</div>}

      <section>
        <h2>Studies</h2>
        <div className="row">
          <input value={studyName} onChange={(e) => setStudyName(e.target.value)} />
          <button onClick={() => void createStudy()}>Create study</button>
          <button onClick={() => void refresh()}>Refresh</button>
        </div>
        <ul>
          {studies.map((s) => (
            <li key={s.id}>
              <button
                className={s.id === selectedId ? "active" : ""}
                onClick={() => {
                  setSelectedId(s.id);
                  void suiteCall<Tree>("studies.tree", { study_id: s.id }).then(setTree);
                }}
              >
                {s.name} · v{s.schema_version ?? 1} · {s.subjects.length} subjects
              </button>
            </li>
          ))}
        </ul>
      </section>

      {selectedId && (
        <>
          <section>
            <h2>Subjects</h2>
            <div className="row">
              <input
                value={subjectLabel}
                onChange={(e) => setSubjectLabel(e.target.value)}
                placeholder="subject label"
              />
              <input
                style={{ flex: 1 }}
                value={subjectMeta}
                onChange={(e) => setSubjectMeta(e.target.value)}
                placeholder='subject metadata JSON'
              />
              <button onClick={() => void addSubject()}>Add subject</button>
            </div>
          </section>

          <section>
            <h2>Import EEG</h2>
            <div className="row">
              <button onClick={() => void browseImport()}>Browse…</button>
              <input
                style={{ flex: 1 }}
                value={importPath}
                onChange={(e) => setImportPath(e.target.value)}
                placeholder="FIF/EDF/BDF/GDF/SET/VHDR/CNT or TXT/CSV/MAT"
              />
              <button onClick={() => void importRecording()} disabled={!importPath}>
                Import
              </button>
            </div>
            {inspect && (
              <div className="inspect-box">
                <p>
                  <strong>{inspect.format}</strong> · status=<code>{inspect.status}</code> ·
                  self_describing=<code>{String(inspect.self_describing)}</code>
                </p>
                {inspect.required_config && inspect.required_config.length > 0 && (
                  <p className="muted">
                    required_config: {inspect.required_config.join(", ")}
                  </p>
                )}
                {inspect.warnings?.length ? (
                  <p className="muted">{inspect.warnings.join(" · ")}</p>
                ) : null}
                {needsConfig && (
                  <div className="row">
                    <label>
                      sfreq (Hz){" "}
                      <input
                        style={{ width: 80 }}
                        value={sfreq}
                        onChange={(e) => setSfreq(e.target.value)}
                      />
                    </label>
                    {(inspect.format === "mat" || inspect.required_config?.includes("data_key")) && (
                      <label>
                        data_key{" "}
                        <select value={dataKey} onChange={(e) => setDataKey(e.target.value)}>
                          <option value="">(choose array)</option>
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
                      transpose (rows=channels)
                    </label>
                    <label>
                      montage{" "}
                      <input
                        value={montage}
                        onChange={(e) => setMontage(e.target.value)}
                        placeholder="optional e.g. standard_1020"
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
          </section>

          <section>
            <h2>Import external stream</h2>
            <div className="row">
              <button onClick={() => void browseExternal()}>Browse…</button>
              <input
                style={{ flex: 1 }}
                value={extPath}
                onChange={(e) => setExtPath(e.target.value)}
                placeholder="gyro/accel/ECG/… CSV/TXT/MAT/NPY"
              />
              <button onClick={() => void importExternalStream()} disabled={!extPath}>
                Import stream
              </button>
            </div>
            <div className="row">
              <label>
                modality{" "}
                <select value={extModality} onChange={(e) => setExtModality(e.target.value)}>
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
                sfreq (Hz){" "}
                <input
                  style={{ width: 80 }}
                  value={extSfreq}
                  onChange={(e) => setExtSfreq(e.target.value)}
                />
              </label>
              <label>
                units{" "}
                <input
                  style={{ width: 100 }}
                  value={extUnits}
                  onChange={(e) => setExtUnits(e.target.value)}
                  placeholder="optional"
                />
              </label>
              <label>
                attach to recording{" "}
                <select
                  value={extRecordingId}
                  onChange={(e) => setExtRecordingId(e.target.value)}
                >
                  <option value="">(create new recording)</option>
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
                {extInspect.format} · suggested_modality={extInspect.suggested_modality ?? "—"} ·{" "}
                {(extInspect.warnings || []).slice(0, 2).join(" · ")}
              </p>
            )}
          </section>

          <section>
            <h2>Study tree</h2>
            <pre className="log">{tree ? JSON.stringify(tree, null, 2) : "—"}</pre>
          </section>
        </>
      )}

      <section>
        <h3>Log</h3>
        <pre className="log">{log || "—"}</pre>
      </section>
    </div>
  );
}

export default App;
