import { useEffect, useMemo, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { suiteCall, waitForSuiteRuntime } from "./ipc";
import "./App.css";

type Study = {
  id: string;
  name: string;
  subjects: Array<{
    id: string;
    label: string;
    sessions: Array<{
      id: string;
      name: string;
      runs: Array<{
        id: string;
        name: string;
        recordings: Array<{
          id: string;
          source_format?: string;
          sampling_rate?: number;
          channel_count?: number;
          duration?: number;
        }>;
      }>;
    }>;
  }>;
};

type Template = { id: string; name: string; status?: string };

type Tab = "home" | "neuroflow" | "neurostudio" | "hub";

function App() {
  const [tab, setTab] = useState<Tab>("home");
  const [status, setStatus] = useState("starting…");
  const [error, setError] = useState<string | null>(null);
  const [studies, setStudies] = useState<Study[]>([]);
  const [studyName, setStudyName] = useState("Motor Imagery");
  const [selectedStudyId, setSelectedStudyId] = useState<string | null>(null);
  const [importPath, setImportPath] = useState("");
  const [subjectLabel, setSubjectLabel] = useState("S001");
  const [signal, setSignal] = useState<any>(null);
  const [erp, setErp] = useState<any>(null);
  const [ica, setIca] = useState<any>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [log, setLog] = useState<string>("");

  const selectedStudy = useMemo(
    () => studies.find((s) => s.id === selectedStudyId) ?? null,
    [studies, selectedStudyId],
  );

  const firstRecording = useMemo(() => {
    if (!selectedStudy) return null;
    for (const sub of selectedStudy.subjects) {
      for (const ses of sub.sessions) {
        for (const run of ses.runs) {
          for (const rec of run.recordings) {
            return { subject: sub, session: ses, run, recording: rec };
          }
        }
      }
    }
    return null;
  }, [selectedStudy]);

  async function refresh() {
    try {
      await waitForSuiteRuntime();
      const health = await suiteCall<{ status: string; version: string }>("health");
      setStatus(`backend ${health.status} v${health.version}`);
      const listed = await suiteCall<{ studies: Study[] }>("studies.list");
      setStudies(listed.studies);
      if (!selectedStudyId && listed.studies[0]) {
        setSelectedStudyId(listed.studies[0].id);
      }
      const t = await suiteCall<{ templates: Template[] }>("neurostudio.templates.list");
      setTemplates(t.templates);
      setError(null);
    } catch (e) {
      setError(String(e));
      setStatus("offline");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  function appendLog(msg: string) {
    setLog((prev) => `${msg}\n${prev}`.slice(0, 4000));
  }

  async function createStudy() {
    const study = await suiteCall<Study>("studies.create", { name: studyName });
    appendLog(`created study ${study.id}`);
    setSelectedStudyId(study.id);
    await refresh();
  }

  async function addSubject() {
    if (!selectedStudyId) return;
    const res = await suiteCall<any>("subjects.add", {
      study_id: selectedStudyId,
      label: subjectLabel,
    });
    appendLog(`added subject ${res.subject.label}`);
    await refresh();
  }

  async function browseRecording() {
    try {
      const selected = await open({
        multiple: false,
        title: "Select EEG recording",
        filters: [
          {
            name: "EEG recordings",
            extensions: ["fif", "edf", "bdf", "set", "vhdr"],
          },
        ],
      });
      if (typeof selected === "string" && selected) {
        setImportPath(selected);
        appendLog(`selected file ${selected}`);
      }
    } catch (e) {
      setError(String(e));
    }
  }

  async function importRecording() {
    if (!selectedStudyId || !importPath) {
      setError("Choose a recording file first (Browse…)");
      return;
    }
    try {
      const study = await suiteCall<Study>("studies.get", { study_id: selectedStudyId });
      let subject = study.subjects.find((s) => s.label === subjectLabel) ?? study.subjects[0];
      if (!subject) {
        const added = await suiteCall<any>("subjects.add", {
          study_id: selectedStudyId,
          label: subjectLabel || "S001",
        });
        appendLog(`auto-added subject ${added.subject.label}`);
        subject = added.subject;
      }
      const session = subject.sessions[0];
      const run = session.runs[0];
      const res = await suiteCall<any>("import.recording", {
        study_id: selectedStudyId,
        subject_id: subject.id,
        session_id: session.id,
        run_id: run.id,
        path: importPath,
      });
      appendLog(`imported recording ${res.recording.id}`);
      setError(null);
      await refresh();
      setTab("neuroflow");
    } catch (e) {
      setError(String(e));
    }
  }

  async function loadSignal() {
    if (!selectedStudyId || !firstRecording) return;
    const res = await suiteCall("recordings.signal_window", {
      study_id: selectedStudyId,
      recording_id: firstRecording.recording.id,
      start: 0,
      duration: 5,
      max_points: 2000,
    });
    setSignal(res);
    appendLog("loaded signal window");
  }

  async function markArtifact() {
    if (!selectedStudyId || !firstRecording) return;
    await suiteCall("annotations.create", {
      study_id: selectedStudyId,
      recording_id: firstRecording.recording.id,
      kind: "continuous",
      label: "artifact",
      start: 1.0,
      end: 1.5,
      action: "mark_bad",
    });
    appendLog("manual artifact annotation stored");
  }

  async function loadErp() {
    if (!selectedStudyId || !firstRecording) return;
    const res = await suiteCall("erp.compute", {
      study_id: selectedStudyId,
      recording_id: firstRecording.recording.id,
    });
    setErp(res);
    appendLog("computed ERP");
  }

  async function loadIca() {
    if (!selectedStudyId || !firstRecording) return;
    const res = await suiteCall("ica.components.list", {
      study_id: selectedStudyId,
      recording_id: firstRecording.recording.id,
      n_components: 8,
    });
    setIca(res);
    appendLog("listed ICA components");
  }

  async function rejectIc0() {
    if (!selectedStudyId || !firstRecording) return;
    await suiteCall("ica.component.set_rejection", {
      study_id: selectedStudyId,
      recording_id: firstRecording.recording.id,
      component_indices: [0],
      action: "reject",
    });
    appendLog("manual ICA reject IC0 stored");
  }

  async function createPlan() {
    if (!selectedStudyId) return;
    const plan = await suiteCall<any>("plans.create", {
      study_id: selectedStudyId,
      name: "Basic clean",
      steps: [
        { operation: "filter_bandpass", parameters: { l_freq: 1, h_freq: 40 } },
        { operation: "filter_notch", parameters: { freqs: [60] } },
      ],
    });
    appendLog(`created plan ${plan.id}`);
  }

  async function runAugmentStub() {
    if (!selectedStudyId || !firstRecording) return;
    const res = await suiteCall("augmentation.run", {
      study_id: selectedStudyId,
      recording_id: firstRecording.recording.id,
    });
    appendLog(`augmentation: ${JSON.stringify(res)}`);
  }

  return (
    <div className="app">
      <header>
        <strong>NeuroTendrils Suite</strong>
        <span className="muted">{status}</span>
      </header>
      <nav>
        {(["home", "neuroflow", "neurostudio", "hub"] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
        <button onClick={() => void refresh()}>refresh</button>
      </nav>
      {error && <pre className="error">{error}</pre>}

      {tab === "home" && (
        <section>
          <h2>Studies</h2>
          <p className="muted">
            1) Create or select a study → 2) open <strong>neuroflow</strong> → 3) Browse… a recording
            file (.fif / .edf / .set / .vhdr).
          </p>
          <div className="row">
            <input value={studyName} onChange={(e) => setStudyName(e.target.value)} />
            <button onClick={() => void createStudy()}>Create study</button>
            {selectedStudyId && (
              <button onClick={() => setTab("neuroflow")}>Open NeuroFlow →</button>
            )}
          </div>
          <ul>
            {studies.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => {
                    setSelectedStudyId(s.id);
                    setTab("neuroflow");
                  }}
                >
                  {s.name} ({s.subjects.length} subjects) — {s.id}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {tab === "neuroflow" && (
        <section>
          <h2>NeuroFlow</h2>
          <p className="muted">
            Import a recording here, then inspect signal / ERP / ICA. Utilitarian UI only.
          </p>
          {!selectedStudy && <p>Select or create a study on Home first.</p>}
          {selectedStudy && (
            <>
              <p>
                Study: <code>{selectedStudy.name}</code>
              </p>
              <h3>1. Subject</h3>
              <div className="row">
                <input
                  value={subjectLabel}
                  onChange={(e) => setSubjectLabel(e.target.value)}
                  placeholder="subject label e.g. S001"
                />
                <button onClick={() => void addSubject()}>Add subject</button>
              </div>
              <h3>2. Select dataset / recording</h3>
              <div className="row">
                <button onClick={() => void browseRecording()}>Browse…</button>
                <input
                  style={{ flex: 1 }}
                  value={importPath}
                  onChange={(e) => setImportPath(e.target.value)}
                  placeholder="No file selected — click Browse…"
                />
                <button onClick={() => void importRecording()} disabled={!importPath}>
                  Import into study
                </button>
              </div>
              <h3>3. Inspect</h3>
              <div className="row">
                <button disabled={!firstRecording} onClick={() => void loadSignal()}>
                  Load signal window
                </button>
                <button disabled={!firstRecording} onClick={() => void markArtifact()}>
                  Manual reject 1–1.5s
                </button>
                <button disabled={!firstRecording} onClick={() => void loadErp()}>
                  ERP
                </button>
                <button disabled={!firstRecording} onClick={() => void loadIca()}>
                  ICA list
                </button>
                <button disabled={!firstRecording} onClick={() => void rejectIc0()}>
                  Reject IC0
                </button>
                <button onClick={() => void createPlan()}>Create filter plan</button>
                <button disabled={!firstRecording} onClick={() => void runAugmentStub()}>
                  Augment stub
                </button>
              </div>
              {firstRecording && (
                <p>
                  Recording {firstRecording.recording.id} — {firstRecording.recording.source_format}{" "}
                  {firstRecording.recording.sampling_rate}Hz{" "}
                  {firstRecording.recording.channel_count}ch
                </p>
              )}
              {signal && (
                <div>
                  <h3>Signal window</h3>
                  <p>
                    channels: {signal.channels?.length} · points: {signal.times?.length} · events:{" "}
                    {signal.events?.length}
                  </p>
                  <SignalSketch signal={signal} />
                </div>
              )}
              {erp && (
                <div>
                  <h3>ERP</h3>
                  <pre>{JSON.stringify({ status: erp.status, nave: erp.nave, n_ch: erp.channels?.length }, null, 2)}</pre>
                </div>
              )}
              {ica && (
                <div>
                  <h3>ICA</h3>
                  <pre>
                    {JSON.stringify(
                      {
                        n_components: ica.n_components,
                        components: (ica.components || []).map((c: any) => c.index),
                      },
                      null,
                      2,
                    )}
                  </pre>
                </div>
              )}
            </>
          )}
        </section>
      )}

      {tab === "neurostudio" && (
        <section>
          <h2>NeuroStudio</h2>
          <p className="muted">Template catalog stubs (EEGNet, …). Training not implemented yet.</p>
          <ul>
            {templates.map((t) => (
              <li key={t.id}>
                {t.name} <code>{t.id}</code> [{t.status}]
              </li>
            ))}
          </ul>
        </section>
      )}

      {tab === "hub" && (
        <section>
          <h2>Hub / Teams</h2>
          <p>Not available locally. Cloud sharing is future-only (interfaces exist in backend).</p>
        </section>
      )}

      <section>
        <h3>Log</h3>
        <pre className="log">{log || "—"}</pre>
      </section>
    </div>
  );
}

function SignalSketch({ signal }: { signal: any }) {
  const width = 720;
  const height = 180;
  const data: number[][] = signal.data || [];
  const times: number[] = signal.times || [];
  if (!data.length || !times.length) return null;
  const ch = data[0];
  const min = Math.min(...ch);
  const max = Math.max(...ch);
  const span = max - min || 1;
  const points = ch
    .map((v, i) => {
      const x = (i / (ch.length - 1 || 1)) * width;
      const y = height - ((v - min) / span) * (height - 8) - 4;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} className="sketch">
      <polyline fill="none" stroke="#222" strokeWidth="1" points={points} />
    </svg>
  );
}

export default App;
