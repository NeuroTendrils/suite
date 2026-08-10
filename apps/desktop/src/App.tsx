import { useEffect, useState } from "react";
import { suiteCall, waitForSuiteRuntime } from "./ipc";
import "./App.css";

type StudySummary = {
  id: string;
  name: string;
  schema_version?: number;
  subjects: Array<{ id: string; label: string; sessions: unknown[] }>;
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
        }>;
      }>;
    }>;
  }>;
};

/**
 * Phase 1 utilitarian shell — Study structure only.
 * EEGLAB chrome removed; manager/viewer UI comes in later phases.
 */
function App() {
  const [status, setStatus] = useState("starting…");
  const [error, setError] = useState<string | null>(null);
  const [studies, setStudies] = useState<StudySummary[]>([]);
  const [studyName, setStudyName] = useState("Motor Imagery");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tree, setTree] = useState<Tree | null>(null);
  const [subjectLabel, setSubjectLabel] = useState("S001");
  const [subjectMeta, setSubjectMeta] = useState('{"age": null, "group": ""}');
  const [log, setLog] = useState("");

  function appendLog(msg: string) {
    setLog((p) => `${msg}\n${p}`.slice(0, 3000));
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
      if (id) {
        const t = await suiteCall<Tree>("studies.tree", { study_id: id });
        setTree(t);
      } else {
        setTree(null);
      }
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
    appendLog(`created study ${s.id} schema=${s.schema_version ?? "?"}`);
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
    const res = await suiteCall<any>("subjects.add", {
      study_id: selectedId,
      label: subjectLabel,
      metadata,
    });
    appendLog(`added subject ${res.subject.label}`);
    await refresh();
  }

  async function addSession() {
    if (!selectedId || !tree?.subjects[0]) return;
    const sub = tree.subjects[0];
    await suiteCall("sessions.add", {
      study_id: selectedId,
      subject_id: sub.id,
      name: `session-${sub.sessions.length + 1}`,
    });
    appendLog(`added session under ${sub.label}`);
    await refresh();
  }

  async function listStreams() {
    if (!selectedId) return;
    const res = await suiteCall<{ streams: Array<{ id: string; modality: string }> }>(
      "streams.list",
      { study_id: selectedId },
    );
    appendLog(`streams: ${res.streams.map((s) => `${s.modality}:${s.id}`).join(", ") || "(none)"}`);
  }

  return (
    <div className="app">
      <header>
        <h1>NeuroTendrils Suite</h1>
        <span className="muted">{status}</span>
      </header>
      <p className="muted">
        Phase 1 — Study structure (Subject → Session → Run → Recording → DataStream). Utilitarian UI
        only.
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
        <section>
          <h2>Structure</h2>
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
              placeholder='subject metadata JSON e.g. {"group":"A"}'
            />
            <button onClick={() => void addSubject()}>Add subject</button>
            <button onClick={() => void addSession()}>Add session</button>
            <button onClick={() => void listStreams()}>List streams</button>
          </div>
          <pre className="log">{tree ? JSON.stringify(tree, null, 2) : "—"}</pre>
        </section>
      )}

      <section>
        <h3>Log</h3>
        <pre className="log">{log || "—"}</pre>
      </section>
    </div>
  );
}

export default App;
