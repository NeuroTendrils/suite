import type { ReactNode } from "react";
import { Badge, Card, EmptyState, Field, Icon, Reason } from "../../components/ui";
import { ValidationBadge } from "../../components/tables";
import { fmtDate, shortId } from "../../lib/format";
import { formatDuration, importGate, isTrained, nextStep, recentActivity, recordingLabel, trainGate } from "../../lib/study";
import type { FlowStage, StudioStage } from "../../lib/workflow";
import type { Operations } from "../../hooks/useOperations";
import type { StudySession } from "../../hooks/useStudySession";
import type { StudyLists } from "../../hooks/useStudyLists";
import type { StudyForms } from "../../hooks/useStudyForms";

/** Home: the study list, the active study's progress, its recordings and subjects, and recent activity. */
export function HomePage({
  ops,
  session,
  lists,
  forms,
  idle,
  newStudyForm,
  selectStudy,
  openRecording,
  openImport,
  startNewStudy,
  openStudio,
}: {
  ops: Operations;
  session: StudySession;
  lists: StudyLists;
  forms: StudyForms;
  idle: boolean;
  newStudyForm: ReactNode;
  selectStudy: (id: string) => Promise<void>;
  openRecording: (id: string, stage?: FlowStage) => Promise<void>;
  openImport: () => void;
  startNewStudy: () => void;
  openStudio: (stage: StudioStage) => void;
}) {
  const { busy } = ops;
  const {
    conn,
    online,
    studies,
    studiesLoaded,
    selectedId,
    selectedStudy,
    manager,
    managerLoading,
    selectedRecId,
    recRows,
    refresh,
  } = session;
  const { homeData } = lists;
  const {
    newStudyOpen,
    subjectLabel,
    setSubjectLabel,
    subjectMeta,
    setSubjectMeta,
    subjectTouched,
    subjectCheck,
    subjectMetaCheck,
    addSubject,
  } = forms;
  const impGate = importGate(!!selectedId, online);
  const trnGate = trainGate(!!selectedId, online, recRows.length);
  const step = nextStep(manager);
  const validatedCount = recRows.filter((r) => r.rec.validation_ok != null).length;
  // Sync only matters for multi-stream recordings; skip an all-"—" column otherwise.
  const showSyncCol = recRows.some((r) => r.rec.streams.length > 1 || r.rec.sync_group_ids.length > 0);
  const homeTrained = homeData ? homeData.experiments.filter(isTrained).length : null;
  const activity = homeData ? recentActivity(homeData) : [];
  const pipeline: Array<{ module: "home" | "flow" | "studio"; name: string; stats: Array<{ label: string; value: number | null; of?: number }> }> =
    manager
      ? [
          {
            module: "home",
            name: "Study",
            stats: [
              { label: "Subjects", value: manager.totals.subjects },
              { label: "Recordings", value: recRows.length },
            ],
          },
          {
            module: "flow",
            name: "NeuroFlow",
            stats: [
              { label: "Validated", value: validatedCount, of: recRows.length },
              { label: "Epoch sets", value: homeData ? homeData.epochsets.length : null },
            ],
          },
          {
            module: "studio",
            name: "NeuroStudio",
            stats: [
              { label: "Datasets", value: homeData ? homeData.datasets.length : null },
              { label: "Experiments", value: homeData ? homeData.experiments.length : null },
              { label: "Trained", value: homeTrained },
            ],
          },
        ]
      : [];

  const welcome = (
    <section className="welcome" aria-labelledby="welcome-title">
      <div className="welcome-main">
        <span className="eyebrow">Getting started</span>
        <h1 id="welcome-title">Create your first study</h1>
        <p className="welcome-lead">
          A study holds one experiment: its subjects, their EEG recordings, and everything derived from them. Nothing
          leaves this computer, and imported source files are never modified.
        </p>
        {newStudyForm}
      </div>
      <ol className="welcome-steps" aria-label="How the suite fits together">
        <li className="mod-home">
          <span className="welcome-icon">
            <Icon name="home" size={18} />
          </span>
          <div>
            <strong>Home — organize</strong>
            <span>Create studies and subjects. Track what has been recorded, processed, and modeled.</span>
          </div>
        </li>
        <li className="mod-flow">
          <span className="welcome-icon">
            <Icon name="flow" size={18} />
          </span>
          <div>
            <strong>NeuroFlow — process each recording</strong>
            <span>Import EEG, inspect channels, reject artifacts, run a preprocessing plan, and cut epochs around events.</span>
          </div>
        </li>
        <li className="mod-studio">
          <span className="welcome-icon">
            <Icon name="studio" size={18} />
          </span>
          <div>
            <strong>NeuroStudio — model across the study</strong>
            <span>Turn epochs into datasets, split them without leakage, train and evaluate models, export results.</span>
          </div>
        </li>
      </ol>
    </section>
  );

  return (
    <>
      {!studiesLoaded && conn.state !== "offline" && <p className="loading">Loading studies…</p>}
      {conn.state === "offline" && !studiesLoaded && (
        <EmptyState
          icon="alert"
          title="Can’t reach the analysis backend"
          actions={
            <button type="button" className="btn btn-primary" onClick={() => void refresh()}>
              Retry connection
            </button>
          }
        >
          Studies are stored by the backend, so they can’t be listed until it is running. The message above has the
          technical details.
        </EmptyState>
      )}

      {studiesLoaded && studies.length === 0 && welcome}

      {studies.length > 0 && (
        <div className="home-grid">
          <aside className="card study-list" aria-label="Studies">
            <header className="card-head">
              <h2 className="card-title">
                Studies <span className="count">{studies.length}</span>
              </h2>
              {!newStudyOpen && (
                <button type="button" className="btn btn-sm btn-primary" onClick={startNewStudy} disabled={!online}>
                  <Icon name="plus" size={14} /> New study
                </button>
              )}
            </header>
            {newStudyOpen && <div className="study-list-form">{newStudyForm}</div>}
            <ul>
              {studies.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    className={`study-item ${s.id === selectedId ? "active" : ""}`}
                    onClick={() => void selectStudy(s.id)}
                    aria-current={s.id === selectedId ? "true" : undefined}
                  >
                    <span className="study-name">{s.name}</span>
                    <span className="study-meta">
                      {s.task_name ? `${s.task_name} · ` : ""}
                      {s.subjects.length} subject{s.subjects.length === 1 ? "" : "s"}
                      {s.created_at ? ` · ${new Date(s.created_at).toLocaleDateString()}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <div className="home-main">
            {!manager ? (
              <p className="loading">{managerLoading ? "Loading study…" : "Select a study."}</p>
            ) : (
              <>
                <section className="study-head" aria-label="Active study">
                  <div className="study-head-text">
                    <span className="eyebrow">Active study</span>
                    <h1 className="study-title">{manager.name}</h1>
                    <p className="study-sub">
                      {manager.task_name && <span>{manager.task_name}</span>}
                      <span className="mono" title="Study ID">
                        {manager.study_id}
                      </span>
                      {selectedStudy?.created_at && <span>Created {fmtDate(selectedStudy.created_at)}</span>}
                    </p>
                  </div>
                  <div className="head-actions">
                    <button type="button" className="btn btn-primary" disabled={!impGate.ok || !!busy} onClick={openImport}>
                      Import recording
                    </button>
                    <button
                      type="button"
                      className="btn"
                      disabled={!trnGate.ok}
                      onClick={() => openStudio("data")}
                      title={trnGate.ok ? "Open NeuroStudio to build datasets and train models" : trnGate.reason}
                    >
                      Train a model
                    </button>
                  </div>
                </section>
                {!trnGate.ok && <Reason text={`Train a model: ${trnGate.reason}`} />}

                <div className="next-step" role="note">
                  <div>
                    <span className="next-label">Next step</span>
                    <strong>{step.title}</strong>
                    <span className="next-detail">{step.detail}</span>
                  </div>
                  {step.action === "import" && (
                    <button type="button" className="btn btn-primary" onClick={openImport} disabled={!impGate.ok}>
                      Import recording
                    </button>
                  )}
                  {step.action === "inspect" && recRows[0] && (
                    <button
                      type="button"
                      className="btn"
                      onClick={() => {
                        const target = recRows.find((r) => r.rec.validation_ok == null) ?? recRows[0];
                        void openRecording(target.rec.id, "inspect");
                      }}
                    >
                      Open in NeuroFlow
                    </button>
                  )}
                </div>

                <section className="pipeline" aria-label="Study progress">
                  {pipeline.map((seg) => (
                    <div key={seg.module} className={`pipeline-seg mod-${seg.module}`}>
                      <span className="pipeline-name">{seg.name}</span>
                      <dl>
                        {seg.stats.map((st) => (
                          <div key={st.label}>
                            <dt>{st.label}</dt>
                            <dd className="num">
                              {st.value == null ? "—" : st.value}
                              {st.of != null && <span className="of">/{st.of}</span>}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  ))}
                </section>

                <Card
                  title={
                    <>
                      Recordings <span className="count">{recRows.length}</span>
                    </>
                  }
                  description={recRows.length ? "Select a row to open the recording in NeuroFlow." : undefined}
                >
                  {recRows.length === 0 ? (
                    <EmptyState
                      title="No recordings in this study yet"
                      actions={
                        <button type="button" className="btn btn-primary" onClick={openImport} disabled={!impGate.ok}>
                          Import recording
                        </button>
                      }
                    >
                      Supported: FIF, EDF, BDF, GDF, EEGLAB .set, BrainVision, CNT, MAT, and delimited text. If a format
                      doesn’t store its sampling rate you’ll be asked for it — the app never guesses.
                    </EmptyState>
                  ) : (
                    <div className="table-wrap">
                      <table className="table table-click">
                        <thead>
                          <tr>
                            <th scope="col">Subject</th>
                            <th scope="col">Session / run</th>
                            <th scope="col">Data</th>
                            <th scope="col" className="r">
                              Rate
                            </th>
                            <th scope="col" className="r">
                              Duration
                            </th>
                            <th scope="col">Validation</th>
                            {showSyncCol && <th scope="col">Sync</th>}
                          </tr>
                        </thead>
                        <tbody>
                          {recRows.map((r) => (
                            <tr
                              key={r.rec.id}
                              className={r.rec.id === selectedRecId ? "selected" : ""}
                              onClick={() => void openRecording(r.rec.id)}
                              tabIndex={0}
                              aria-label={`Open ${recordingLabel(r)} in NeuroFlow`}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  void openRecording(r.rec.id);
                                }
                              }}
                              title={r.rec.id}
                            >
                              <td className="strong">{r.subjectLabel}</td>
                              <td className="nowrap">
                                {r.sessionName} / {r.runName}
                              </td>
                              <td className="nowrap">
                                {r.rec.modalities.join(" + ") || "—"}
                                {r.rec.source_format && <span className="muted"> · {r.rec.source_format}</span>}
                              </td>
                              <td className="r num nowrap">{r.rec.sampling_rate ? `${r.rec.sampling_rate} Hz` : "—"}</td>
                              <td className="r num nowrap">{formatDuration(r.rec.duration)}</td>
                              <td>
                                <ValidationBadge ok={r.rec.validation_ok} errors={r.rec.validation_errors} warnings={r.rec.validation_warnings} />
                              </td>
                              {showSyncCol && <td className="nowrap">
                                {r.rec.sync_group_ids.length ? (
                                  <span className="num">conf {(r.rec.sync_confidence ?? 0).toFixed(2)}</span>
                                ) : r.rec.streams.length > 1 ? (
                                  <Badge tone="warn">not aligned</Badge>
                                ) : (
                                  <span className="muted">—</span>
                                )}
                              </td>}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>

                <div className="home-cols">
                  <Card
                    title={
                      <>
                        Subjects <span className="count">{manager.subjects.length}</span>
                      </>
                    }
                    description="Each subject starts with one session and one run."
                  >
                    {manager.subjects.length > 0 && (
                      <div className="table-wrap">
                        <table className="table">
                          <thead>
                            <tr>
                              <th scope="col">Label</th>
                              <th scope="col" className="r">
                                Recordings
                              </th>
                              <th scope="col">Metadata</th>
                            </tr>
                          </thead>
                          <tbody>
                            {manager.subjects.map((s) => (
                              <tr key={s.id}>
                                <td className="strong">{s.label}</td>
                                <td className="r num">
                                  {s.sessions.reduce((n, ses) => n + ses.runs.reduce((m, run) => m + run.recordings.length, 0), 0)}
                                </td>
                                <td className="muted">{Object.keys(s.metadata || {}).join(", ") || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    <form
                      className="form-grid compact"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void addSubject();
                      }}
                    >
                      <Field label="New subject label" error={subjectTouched && subjectLabel ? subjectCheck.error : null}>
                        <input value={subjectLabel} onChange={(e) => setSubjectLabel(e.target.value)} placeholder="e.g. S002" />
                      </Field>
                      <Field label="Metadata (JSON, optional)" error={subjectMetaCheck.ok ? null : subjectMetaCheck.error}>
                        <input
                          value={subjectMeta}
                          onChange={(e) => setSubjectMeta(e.target.value)}
                          placeholder='{"age": 24}'
                          className="mono"
                        />
                      </Field>
                      <div className="form-actions">
                        <button
                          type="submit"
                          className="btn"
                          disabled={!idle || !subjectLabel.trim() || !subjectCheck.ok || !subjectMetaCheck.ok}
                        >
                          Add subject
                        </button>
                      </div>
                    </form>
                  </Card>

                  <Card title="Recent activity" description="Most recent items saved in this study.">
                    {homeData == null ? (
                      <p className="help">Loading…</p>
                    ) : activity.length === 0 ? (
                      <p className="help">Nothing processed yet. Epoch sets, datasets, plans, and experiments appear here once created.</p>
                    ) : (
                      <ol className="timeline">
                        {activity.map((a, i) => (
                          <li key={`${a.kind}-${a.label}-${i}`}>
                            <span className="timeline-kind">{a.kind}</span>
                            <span className="timeline-label">
                              <span className={a.kind === "Experiment" ? "mono" : ""}>{a.kind === "Experiment" ? shortId(a.label, 14) : a.label}</span>
                              {a.detail && <span className="muted"> · {a.detail}</span>}
                            </span>
                            <time className="timeline-time" dateTime={a.at}>
                              {fmtDate(a.at)}
                            </time>
                          </li>
                        ))}
                      </ol>
                    )}
                  </Card>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
