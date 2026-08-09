import { useEffect, useMemo, useState, type ReactNode } from "react";
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
          channels?: Array<{ name: string; type?: string; location?: unknown }>;
        }>;
      }>;
    }>;
  }>;
};

type ColumnSpec = { index: number; name: string; role: string };
type MenuId = "file" | "edit" | "tools" | "plot" | "study" | "datasets" | "help" | null;
type Dialog =
  | null
  | "import_ascii"
  | "channel_locations"
  | "dataset_info"
  | "extract_epochs"
  | "run_ica"
  | "create_study";

type ActiveRec = {
  subject: Study["subjects"][number];
  session: Study["subjects"][number]["sessions"][number];
  run: Study["subjects"][number]["sessions"][number]["runs"][number];
  recording: Study["subjects"][number]["sessions"][number]["runs"][number]["recordings"][number];
};

const MONTAGES = [
  "standard_1020",
  "standard_1005",
  "biosemi16",
  "biosemi32",
  "biosemi64",
  "easycap-M1",
  "easycap-M10",
  "GSN-HydroCel-32",
  "GSN-HydroCel-64_1.0",
];

function App() {
  const [status, setStatus] = useState("starting…");
  const [error, setError] = useState<string | null>(null);
  const [menu, setMenu] = useState<MenuId>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [studies, setStudies] = useState<Study[]>([]);
  const [studyName, setStudyName] = useState("Motor Imagery");
  const [selectedStudyId, setSelectedStudyId] = useState<string | null>(null);
  const [subjectLabel, setSubjectLabel] = useState("S001");
  const [importPath, setImportPath] = useState("");
  const [importSfreq, setImportSfreq] = useState("128");
  const [importTranspose, setImportTranspose] = useState(false);
  const [importMontage, setImportMontage] = useState("");
  const [importInspect, setImportInspect] = useState<any>(null);
  const [importColumns, setImportColumns] = useState<ColumnSpec[]>([]);
  const [recordingDetail, setRecordingDetail] = useState<any>(null);
  const [signal, setSignal] = useState<any>(null);
  const [viewStart, setViewStart] = useState(0);
  const [viewDuration, setViewDuration] = useState(5);
  const [scale, setScale] = useState(25);
  const [erp, setErp] = useState<any>(null);
  const [ica, setIca] = useState<any>(null);
  const [rejectedIcs, setRejectedIcs] = useState<number[]>([]);
  const [panel, setPanel] = useState<"scroll" | "erp" | "ica" | "empty">("empty");
  const [epochEvent, setEpochEvent] = useState("");
  const [epochLimits, setEpochLimits] = useState("-1 2");
  const [log, setLog] = useState("");

  const selectedStudy = useMemo(
    () => studies.find((s) => s.id === selectedStudyId) ?? null,
    [studies, selectedStudyId],
  );

  const active: ActiveRec | null = useMemo(() => {
    if (!selectedStudy) return null;
    for (const subject of selectedStudy.subjects) {
      for (const session of subject.sessions) {
        for (const run of session.runs) {
          for (const recording of run.recordings) {
            return { subject, session, run, recording };
          }
        }
      }
    }
    return null;
  }, [selectedStudy]);

  const channels = recordingDetail?.channels ?? active?.recording.channels ?? [];
  const hasLocations = channels.some((c: any) => c?.location);
  const nFrames = useMemo(() => {
    const sr = active?.recording.sampling_rate;
    const dur = active?.recording.duration;
    if (!sr || !dur) return null;
    return Math.round(sr * dur);
  }, [active]);

  function appendLog(msg: string) {
    setLog((prev) => `${msg}\n${prev}`.slice(0, 3500));
  }

  async function refresh() {
    try {
      await waitForSuiteRuntime();
      const health = await suiteCall<{ status: string; version: string }>("health");
      setStatus(`backend ${health.status} v${health.version}`);
      const listed = await suiteCall<{ studies: Study[] }>("studies.list");
      setStudies(listed.studies);
      if (!selectedStudyId && listed.studies[0]) setSelectedStudyId(listed.studies[0].id);
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
    if (!selectedStudyId || !active) {
      setRecordingDetail(null);
      return;
    }
    void suiteCall("recordings.inspect", {
      study_id: selectedStudyId,
      recording_id: active.recording.id,
    })
      .then((d) => setRecordingDetail(d))
      .catch(() => setRecordingDetail(null));
  }, [selectedStudyId, active?.recording.id]);

  function closeMenus() {
    setMenu(null);
  }

  function openDialog(d: Dialog) {
    closeMenus();
    setDialog(d);
  }

  async function createStudy() {
    const study = await suiteCall<Study>("studies.create", { name: studyName });
    setSelectedStudyId(study.id);
    appendLog(`created study ${study.id}`);
    setDialog(null);
    await refresh();
  }

  async function browseAscii() {
    const selected = await open({
      multiple: false,
      title: "Import ASCII / float file",
      filters: [
        { name: "ASCII / text", extensions: ["txt", "csv", "tsv", "asc"] },
        { name: "EEG recordings", extensions: ["fif", "edf", "bdf", "set", "vhdr", "txt", "csv"] },
      ],
    });
    if (typeof selected !== "string" || !selected) return;
    setImportPath(selected);
    try {
      const inspected = await suiteCall<any>("import.inspect", { path: selected });
      setImportInspect(inspected);
      const cols: ColumnSpec[] = Array.isArray(inspected.columns)
        ? inspected.columns.map((c: any) => ({
            index: Number(c.index),
            name: String(c.name ?? `ch${Number(c.index) + 1}`),
            role: String(c.role ?? "eeg"),
          }))
        : [];
      setImportColumns(cols);
      if (Array.isArray(inspected.montages) && inspected.montages[0] && !importMontage) {
        /* leave montage blank until user chooses — like EEGLAB Channel locations: No */
      }
      appendLog(`inspected ${inspected.n_cols} columns × ${inspected.n_rows} samples`);
    } catch (e) {
      setImportInspect(null);
      setImportColumns([]);
      setError(String(e));
    }
  }

  async function importAscii() {
    if (!selectedStudyId || !importPath) {
      setError("Choose a file and create/select a study first");
      return;
    }
    const hz = Number(importSfreq);
    if (!Number.isFinite(hz) || hz <= 0) {
      setError("Sampling rate (Hz) is required");
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
        subject = added.subject;
      }
      const session = subject.sessions[0];
      const run = session.runs[0];
      const isText = /\.(txt|csv|tsv|asc)$/i.test(importPath);
      const payload: Record<string, unknown> = {
        study_id: selectedStudyId,
        subject_id: subject.id,
        session_id: session.id,
        run_id: run.id,
        path: importPath,
      };
      if (isText) {
        payload.sfreq = hz;
        payload.transpose = importTranspose;
        if (importMontage) payload.montage = importMontage;
        if (importColumns.length) payload.column_selection = importColumns;
      }
      const res = await suiteCall<any>("import.recording", payload);
      appendLog(`imported ${res.recording.id}`);
      setDialog(null);
      setPanel("scroll");
      await refresh();
      setViewStart(0);
      await loadSignal(0);
    } catch (e) {
      setError(String(e));
    }
  }

  async function loadSignal(start = viewStart) {
    if (!selectedStudyId || !active) return;
    const res = await suiteCall("recordings.signal_window", {
      study_id: selectedStudyId,
      recording_id: active.recording.id,
      start,
      duration: viewDuration,
      max_points: 2500,
    });
    setSignal(res);
    setViewStart(start);
    setPanel("scroll");
    appendLog(`scroll window @ ${start}s`);
  }

  async function rejectWindow() {
    if (!selectedStudyId || !active) return;
    await suiteCall("annotations.create", {
      study_id: selectedStudyId,
      recording_id: active.recording.id,
      kind: "continuous",
      label: "artifact",
      start: viewStart,
      end: viewStart + Math.min(1.5, viewDuration),
      action: "mark_bad",
    });
    appendLog(`REJECT marked ${viewStart}–${viewStart + Math.min(1.5, viewDuration)}s`);
  }

  async function applyMontage() {
    if (!selectedStudyId || !active || !importMontage) {
      setError("Pick a standard montage first");
      return;
    }
    // Montage on already-imported data: re-import path not available; store preference via channel edit on next text import.
    // For existing recordings, surface locations from inspect if already set; otherwise instruct re-import with montage.
    if (hasLocations) {
      appendLog("channel locations already present");
      setDialog(null);
      return;
    }
    setError(
      "Apply montage on Import (File → Import data → ASCII) or re-import with a montage selected. Edit → Channel locations sets the montage used at import.",
    );
    setDialog(null);
    setDialog("import_ascii");
  }

  async function runIca() {
    if (!selectedStudyId || !active) return;
    const res = await suiteCall<any>("ica.components.list", {
      study_id: selectedStudyId,
      recording_id: active.recording.id,
      n_components: active.recording.channel_count || 15,
    });
    setIca(res);
    setRejectedIcs([]);
    setPanel("ica");
    setDialog(null);
    appendLog(`ICA listed ${res.n_components} components`);
  }

  async function commitIcaRejects() {
    if (!selectedStudyId || !active || !rejectedIcs.length) return;
    await suiteCall("ica.component.set_rejection", {
      study_id: selectedStudyId,
      recording_id: active.recording.id,
      component_indices: rejectedIcs,
      action: "reject",
    });
    appendLog(`rejected ICs: ${rejectedIcs.join(", ")}`);
  }

  async function plotErp() {
    if (!selectedStudyId || !active) return;
    const res = await suiteCall("erp.compute", {
      study_id: selectedStudyId,
      recording_id: active.recording.id,
    });
    setErp(res);
    setPanel("erp");
    closeMenus();
    appendLog("computed ERP");
  }

  async function createFilterPlan() {
    if (!selectedStudyId) return;
    await suiteCall("plans.create", {
      study_id: selectedStudyId,
      name: "bandpass 1-40",
      steps: [{ op: "filter_bandpass", params: { l_freq: 1, h_freq: 40 } }],
    });
    appendLog("created filter plan");
    closeMenus();
  }

  const filename =
    recordingDetail?.source_files?.[0] ||
    active?.recording.id ||
    "(no dataset)";

  return (
    <div className="app" onClick={closeMenus}>
      <div className="titlebar">
        <h1>NeuroTendrils Suite — NeuroFlow</h1>
      </div>

      <nav className="menubar" onClick={(e) => e.stopPropagation()}>
        {(
          [
            ["file", "File"],
            ["edit", "Edit"],
            ["tools", "Tools"],
            ["plot", "Plot"],
            ["study", "Study"],
            ["datasets", "Datasets"],
            ["help", "Help"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            className={menu === id ? "open" : ""}
            onClick={() => setMenu(menu === id ? null : id)}
          >
            {label}
          </button>
        ))}

        {menu === "file" && (
          <div className="menu-flyout" style={{ left: 4 }}>
            <button onClick={() => openDialog("import_ascii")}>
              Import data ▸ From ASCII/float file…
            </button>
            <button disabled>Import event info ▸ From ASCII file…</button>
            <div className="sep" />
            <button onClick={() => openDialog("create_study")}>Create study…</button>
            <button
              onClick={() => {
                closeMenus();
                void refresh();
              }}
            >
              Load / refresh studies
            </button>
          </div>
        )}
        {menu === "edit" && (
          <div className="menu-flyout" style={{ left: 48 }}>
            <button onClick={() => openDialog("dataset_info")}>Dataset info</button>
            <button onClick={() => openDialog("channel_locations")}>Channel locations…</button>
            <div className="sep" />
            <button
              disabled={!active}
              onClick={() => {
                closeMenus();
                void loadSignal(viewStart);
              }}
            >
              Select data (scroll)
            </button>
            <button
              disabled={!active}
              onClick={() => {
                closeMenus();
                void rejectWindow();
              }}
            >
              Edit events & mark bad…
            </button>
          </div>
        )}
        {menu === "tools" && (
          <div className="menu-flyout" style={{ left: 96 }}>
            <button disabled={!selectedStudyId} onClick={() => void createFilterPlan()}>
              Filter the data…
            </button>
            <button disabled>Change sampling rate…</button>
            <button disabled>Re-reference…</button>
            <div className="sep" />
            <button
              disabled={!active}
              onClick={() => {
                closeMenus();
                setPanel("scroll");
                void loadSignal(viewStart);
              }}
            >
              Reject continuous data by eye…
            </button>
            <button disabled={!active} onClick={() => openDialog("extract_epochs")}>
              Extract epochs…
            </button>
            <div className="sep" />
            <button disabled={!active} onClick={() => openDialog("run_ica")}>
              Run ICA…
            </button>
            <button
              disabled={!ica}
              onClick={() => {
                closeMenus();
                setPanel("ica");
              }}
            >
              Reject components by map…
            </button>
          </div>
        )}
        {menu === "plot" && (
          <div className="menu-flyout" style={{ left: 150 }}>
            <button
              disabled={!active}
              onClick={() => {
                closeMenus();
                void loadSignal(viewStart);
              }}
            >
              Channel data (scroll)
            </button>
            <button disabled={!active} onClick={() => void plotErp()}>
              Channel ERPs
            </button>
            <button disabled>Channel locations</button>
            <button disabled>ERP map series</button>
            <div className="sep" />
            <button
              disabled={!ica}
              onClick={() => {
                closeMenus();
                setPanel("ica");
              }}
            >
              Component maps
            </button>
          </div>
        )}
        {menu === "study" && (
          <div className="menu-flyout" style={{ left: 200 }}>
            <button onClick={() => openDialog("create_study")}>Create study…</button>
            {studies.map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  setSelectedStudyId(s.id);
                  closeMenus();
                }}
              >
                {s.name}
              </button>
            ))}
          </div>
        )}
        {menu === "datasets" && (
          <div className="menu-flyout" style={{ left: 250 }}>
            {active ? (
              <button disabled>
                #1: {active.recording.source_format || "dataset"} ({active.recording.channel_count} ch)
              </button>
            ) : (
              <button disabled>(no dataset loaded)</button>
            )}
          </div>
        )}
        {menu === "help" && (
          <div className="menu-flyout" style={{ left: 320 }}>
            <button
              onClick={() => {
                closeMenus();
                appendLog("Help: EEGLAB-inspired workflow — Import → Edit channels/montage → Scroll/Reject → Tools → Plot");
              }}
            >
              About NeuroFlow
            </button>
          </div>
        )}
      </nav>

      {error && <div className="error">{error}</div>}

      <div className="workspace">
        <aside className="dataset-info">
          <h2>
            {active
              ? `#1: Continuous EEG Data`
              : selectedStudy
                ? `Study: ${selectedStudy.name}`
                : "No dataset"}
          </h2>
          {active ? (
            <dl>
              <dt>Filename</dt>
              <dd title={String(filename)}>{String(filename).split(/[/\\]/).pop()}</dd>
              <dt>Channels per frame</dt>
              <dd>{active.recording.channel_count ?? "—"}</dd>
              <dt>Frames per epoch</dt>
              <dd>{nFrames ?? "—"}</dd>
              <dt>Epochs</dt>
              <dd>1</dd>
              <dt>Events</dt>
              <dd>{recordingDetail?.events?.length ?? 0}</dd>
              <dt>Sampling rate (Hz)</dt>
              <dd>{active.recording.sampling_rate ?? "—"}</dd>
              <dt>Epoch start (sec)</dt>
              <dd>0.000</dd>
              <dt>Epoch end (sec)</dt>
              <dd>{active.recording.duration?.toFixed?.(3) ?? "—"}</dd>
              <dt>Reference</dt>
              <dd>unknown</dd>
              <dt>Channel locations</dt>
              <dd>{hasLocations ? "Yes" : "No"}</dd>
              <dt>ICA weights</dt>
              <dd>{ica ? "Yes" : "No"}</dd>
              <dt>Dataset size</dt>
              <dd>
                {importInspect?.file_size_bytes
                  ? `${(importInspect.file_size_bytes / 1e6).toFixed(1)} Mb (source)`
                  : "—"}
              </dd>
              <dt>Subject</dt>
              <dd>{active.subject.label}</dd>
            </dl>
          ) : (
            <p className="empty">
              File → Import data → From ASCII/float file…
              <br />
              Then Edit → Channel locations, Plot → Channel data (scroll), Tools → Reject / ICA.
            </p>
          )}
        </aside>

        <section className="main-panel">
          {panel === "scroll" && (
            <div className="scroll-view">
              <div className="panel-title">Scroll channel activities</div>
              <div className="scroll-canvas">
                <SignalSketch signal={signal} scale={scale} />
              </div>
              <div className="scroll-controls">
                <button
                  onClick={() => void loadSignal(Math.max(0, viewStart - viewDuration * 5))}
                >
                  {"<<"}
                </button>
                <button onClick={() => void loadSignal(Math.max(0, viewStart - viewDuration))}>
                  {"<"}
                </button>
                <input
                  type="number"
                  value={viewStart}
                  onChange={(e) => setViewStart(Number(e.target.value))}
                  onBlur={() => void loadSignal(viewStart)}
                />
                <button onClick={() => void loadSignal(viewStart + viewDuration)}>{">"}</button>
                <button onClick={() => void loadSignal(viewStart + viewDuration * 5)}>
                  {">>"}
                </button>
                <label>
                  win{" "}
                  <input
                    type="number"
                    value={viewDuration}
                    min={1}
                    onChange={(e) => setViewDuration(Number(e.target.value) || 5)}
                  />
                  s
                </label>
                <label>
                  scale{" "}
                  <input
                    type="number"
                    value={scale}
                    onChange={(e) => setScale(Number(e.target.value) || 25)}
                  />
                </label>
                <span className="muted">
                  {signal?.channels?.length ?? 0} ch · {signal?.times?.length ?? 0} pts
                </span>
                <button className="reject" onClick={() => void rejectWindow()}>
                  REJECT
                </button>
              </div>
            </div>
          )}
          {panel === "erp" && (
            <>
              <div className="panel-title">Channel ERPs</div>
              <pre style={{ padding: 12, margin: 0, fontSize: 12 }}>
                {JSON.stringify(
                  { status: erp?.status, nave: erp?.nave, n_ch: erp?.channels?.length },
                  null,
                  2,
                )}
              </pre>
            </>
          )}
          {panel === "ica" && (
            <>
              <div className="panel-title">Reject components by map</div>
              <div className="ica-grid">
                {(ica?.components || []).map((c: any) => (
                  <button
                    key={c.index}
                    type="button"
                    className={`ica-tile ${rejectedIcs.includes(c.index) ? "rejected" : ""}`}
                    onClick={() =>
                      setRejectedIcs((prev) =>
                        prev.includes(c.index)
                          ? prev.filter((x) => x !== c.index)
                          : [...prev, c.index],
                      )
                    }
                  >
                    <div className="idx">{c.index + 1}</div>
                    <div className="topo-placeholder" />
                  </button>
                ))}
              </div>
              <div className="scroll-controls">
                <button onClick={() => setRejectedIcs([])}>Cancel marks</button>
                <button className="reject" onClick={() => void commitIcaRejects()}>
                  OK / reject selected
                </button>
              </div>
            </>
          )}
          {panel === "empty" && (
            <>
              <div className="panel-title">Workspace</div>
              <p className="muted" style={{ padding: 16 }}>
                Import a recording to open the scroll viewer. Menus follow the EEGLAB workflow from
                the info slides (import → channel locations → scroll/reject → tools → plot).
              </p>
            </>
          )}
        </section>
      </div>

      <footer className="statusline">
        <span>{status}</span>
        <span>Study: {selectedStudy?.name ?? "—"}</span>
        <span className="muted">{log.split("\n")[0] || "Ready"}</span>
      </footer>

      {dialog === "create_study" && (
        <Modal title="Create study" onClose={() => setDialog(null)}>
          <label>
            Study name
            <input value={studyName} onChange={(e) => setStudyName(e.target.value)} />
          </label>
          <div className="actions">
            <button onClick={() => setDialog(null)}>Cancel</button>
            <button onClick={() => void createStudy()}>Ok</button>
          </div>
        </Modal>
      )}

      {dialog === "import_ascii" && (
        <Modal title="Import ASCII/float file — pop_importdata()" onClose={() => setDialog(null)}>
          <label>
            Subject label
            <input value={subjectLabel} onChange={(e) => setSubjectLabel(e.target.value)} />
          </label>
          <div className="row">
            <button type="button" onClick={() => void browseAscii()}>
              Browse…
            </button>
            <span className="muted" style={{ flex: 1 }}>
              {importPath || "No file selected"}
            </span>
          </div>
          <label>
            Sampling rate (Hz)
            <input value={importSfreq} onChange={(e) => setImportSfreq(e.target.value)} />
          </label>
          <label>
            Data orientation
            <select
              value={importTranspose ? "channels_rows" : "samples_rows"}
              onChange={(e) => setImportTranspose(e.target.value === "channels_rows")}
            >
              <option value="samples_rows">Rows = time samples, columns = channels</option>
              <option value="channels_rows">Rows = channels, columns = time samples</option>
            </select>
          </label>
          <label>
            Channel locations (montage)
            <select value={importMontage} onChange={(e) => setImportMontage(e.target.value)}>
              <option value="">None (Channel locations: No)</option>
              {MONTAGES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <p className="muted">
            Set each column’s role (EEG / EOG / stim / misc / ignore). No fixed channel count —
            use whatever your file has.
          </p>
          {importColumns.length > 0 && (
            <div className="chan-table-wrap">
              <table className="chan-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Label</th>
                    <th>Type / role</th>
                  </tr>
                </thead>
                <tbody>
                  {importColumns.map((col, rowIdx) => (
                    <tr key={col.index}>
                      <td>{col.index + 1}</td>
                      <td>
                        <input
                          value={col.name}
                          onChange={(e) => {
                            const name = e.target.value;
                            setImportColumns((cols) =>
                              cols.map((c, i) => (i === rowIdx ? { ...c, name } : c)),
                            );
                          }}
                        />
                      </td>
                      <td>
                        <select
                          value={col.role}
                          onChange={(e) => {
                            const role = e.target.value;
                            setImportColumns((cols) =>
                              cols.map((c, i) => (i === rowIdx ? { ...c, role } : c)),
                            );
                          }}
                        >
                          <option value="eeg">EEG</option>
                          <option value="misc">EOG / misc</option>
                          <option value="stim">Stim / marker</option>
                          <option value="time">Time (skip)</option>
                          <option value="ignore">Ignore</option>
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {importInspect && (
            <p className="muted">
              Detected {importInspect.n_cols} columns × {importInspect.n_rows} samples
              {importInspect.file_size_bytes
                ? ` · ${(importInspect.file_size_bytes / 1e6).toFixed(0)} Mb`
                : ""}
            </p>
          )}
          <div className="actions">
            <button onClick={() => setDialog(null)}>Cancel</button>
            <button onClick={() => void importAscii()} disabled={!importPath || !selectedStudyId}>
              Ok
            </button>
          </div>
        </Modal>
      )}

      {dialog === "channel_locations" && (
        <Modal title="Import channel locations" onClose={() => setDialog(null)}>
          <p className="muted">
            Choose a standard montage. Labels in the channel editor should match electrode names
            (e.g. Fz, Cz). Applied at ASCII import.
          </p>
          <label>
            Standard montage
            <select value={importMontage} onChange={(e) => setImportMontage(e.target.value)}>
              <option value="">None</option>
              {MONTAGES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <p className="muted">
            Current dataset: Channel locations = {hasLocations ? "Yes" : "No"}
          </p>
          <div className="actions">
            <button onClick={() => setDialog(null)}>Cancel</button>
            <button onClick={() => void applyMontage()}>Ok</button>
          </div>
        </Modal>
      )}

      {dialog === "dataset_info" && (
        <Modal title="Dataset info" onClose={() => setDialog(null)}>
          <pre style={{ fontSize: 12, margin: 0, whiteSpace: "pre-wrap" }}>
            {JSON.stringify(
              {
                study: selectedStudy?.name,
                recording: active?.recording,
                channels: channels.map((c: any) => ({
                  name: c.name,
                  type: c.type,
                  has_loc: Boolean(c.location),
                })),
              },
              null,
              2,
            )}
          </pre>
          <div className="actions">
            <button onClick={() => setDialog(null)}>Ok</button>
          </div>
        </Modal>
      )}

      {dialog === "extract_epochs" && (
        <Modal title="Extract data epochs — pop_epoch()" onClose={() => setDialog(null)}>
          <label>
            Time-locking event type(s)
            <input value={epochEvent} onChange={(e) => setEpochEvent(e.target.value)} placeholder="[] = all" />
          </label>
          <label>
            Epoch limits [start end] (sec)
            <input value={epochLimits} onChange={(e) => setEpochLimits(e.target.value)} />
          </label>
          <p className="muted">Epoch extraction plan stub — stores intent; full executor later.</p>
          <div className="actions">
            <button onClick={() => setDialog(null)}>Cancel</button>
            <button
              onClick={() => {
                appendLog(`epoch intent: event=${epochEvent || "all"} limits=${epochLimits}`);
                setDialog(null);
              }}
            >
              Ok
            </button>
          </div>
        </Modal>
      )}

      {dialog === "run_ica" && (
        <Modal title="Run ICA decomposition — pop_runica()" onClose={() => setDialog(null)}>
          <label>
            ICA algorithm
            <select defaultValue="runica">
              <option value="runica">runica (MNE FastICA)</option>
            </select>
          </label>
          <label>
            Channel types / indices
            <input defaultValue="eeg" />
          </label>
          <div className="actions">
            <button onClick={() => setDialog(null)}>Cancel</button>
            <button onClick={() => void runIca()}>Ok</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <div className="body">{children}</div>
      </div>
    </div>
  );
}

function SignalSketch({ signal, scale }: { signal: any; scale: number }) {
  const width = 900;
  const rowH = 22;
  const data: number[][] = signal?.data || [];
  const names: string[] = signal?.channels || [];
  const times: number[] = signal?.times || [];
  if (!data.length || !times.length) {
    return <p className="muted">No scroll data — Plot → Channel data (scroll)</p>;
  }
  const height = Math.max(180, data.length * rowH + 20);
  const amp = scale || 25;
  return (
    <svg className="sketch" viewBox={`0 0 ${width} ${height}`} width="100%" height={height}>
      {data.map((ch, ci) => {
        const y0 = 16 + ci * rowH + rowH / 2;
        const pts = ch
          .map((v, i) => {
            const x = (i / (ch.length - 1 || 1)) * (width - 70) + 60;
            const y = y0 - (v / amp) * (rowH * 0.45);
            return `${x},${y}`;
          })
          .join(" ");
        return (
          <g key={ci}>
            <text x={4} y={y0 + 4} fontSize={10} fill="#333">
              {names[ci] ?? ci + 1}
            </text>
            <polyline fill="none" stroke="#1a4a8a" strokeWidth="1" points={pts} />
          </g>
        );
      })}
    </svg>
  );
}

export default App;
