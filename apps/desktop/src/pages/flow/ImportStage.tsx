import { Badge, Card, Field, Reason } from "../../components/ui";
import { EEG_EXTENSIONS, NEW_RECORDING, NEW_SUBJECT, STREAM_MODALITIES } from "../../lib/constants";
import { recordingLabel } from "../../lib/study";
import type { StudySession } from "../../hooks/useStudySession";
import type { ImportState } from "../../hooks/useImport";

/** NeuroFlow → Import: bring an EEG recording into the study, or attach another modality to a recording. */
export function ImportStage({ session, imp, idle }: {
  session: StudySession;
  imp: ImportState;
  idle: boolean;
}) {
  const { manager, recRows } = session;
  const {
    importPath,
    setImportPath,
    inspect,
    inspectedPath,
    sfreq,
    setSfreq,
    dataKey,
    setDataKey,
    transpose,
    setTranspose,
    montage,
    setMontage,
    columns,
    setColumns,
    importSubjectEff,
    setImportSubject,
    importNewLabel,
    setImportNewLabel,
    importNewLabelCheck,
    extPath,
    setExtPath,
    extInspect,
    extModality,
    setExtModality,
    extSfreq,
    setExtSfreq,
    extSfreqCheck,
    extUnits,
    setExtUnits,
    extAttachEff,
    setExtAttach,
    inspectErr,
    needsConfig,
    needsSfreq,
    needsDataKey,
    sfreqCheck,
    importBlock,
    extBlock,
    inspectImport,
    browseImport,
    importRecording,
    browseExternal,
    importExternalStream,
  } = imp;
  const subjectSelect = (
    <>
      <Field label="Subject" hint="Recordings are filed under the subject’s first session and run.">
        <select value={importSubjectEff} onChange={(e) => setImportSubject(e.target.value)}>
          {manager?.subjects.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
          <option value={NEW_SUBJECT}>New subject…</option>
        </select>
      </Field>
      {importSubjectEff === NEW_SUBJECT && (
        <Field label="New subject label" error={importNewLabelCheck.ok ? null : importNewLabelCheck.error}>
          <input value={importNewLabel} onChange={(e) => setImportNewLabel(e.target.value)} />
        </Field>
      )}
    </>
  );

  return (
    <>
      <Card
        title="Import EEG recording"
        description="Choose a file, review what was detected, provide any settings the format can’t supply, then import."
      >
        <div className="form-row">
          <Field label="File" wide>
            <div className="input-group">
              <input
                value={importPath}
                onChange={(e) => setImportPath(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void inspectImport(importPath);
                }}
                placeholder="/path/to/recording.fif"
                className="mono"
              />
              <button type="button" className="btn" onClick={() => void browseImport()} disabled={!idle}>
                Browse…
              </button>
              {importPath.trim() && inspectedPath !== importPath.trim() && (
                <button type="button" className="btn" onClick={() => void inspectImport(importPath)} disabled={!idle}>
                  Inspect
                </button>
              )}
            </div>
          </Field>
        </div>
        <p className="help">Supported: {EEG_EXTENSIONS.map((e) => `.${e}`).join(" ")}</p>

        {inspect && inspectedPath === importPath.trim() && (
          <div className="detected">
            <div className="detected-head">
              <span>Detected</span>
              <strong>{inspect.format ?? "unknown format"}</strong>
              {inspectErr ? (
                <Badge tone="danger">unreadable</Badge>
              ) : needsConfig ? (
                <Badge tone="warn">needs settings</Badge>
              ) : (
                <Badge tone="ok">ready</Badge>
              )}
              {typeof inspect.sfreq === "number" && <span className="num">{inspect.sfreq} Hz</span>}
            </div>
            {!!inspect.warnings?.length && (
              <ul className="issues warn">
                {inspect.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
            {needsConfig && (
              <div className="form-row">
                {needsSfreq && (
                  <Field
                    label="Sampling rate (Hz)"
                    error={sfreq && sfreqCheck && !sfreqCheck.ok ? sfreqCheck.error : null}
                    hint="Required: this format doesn’t record it."
                  >
                    <input value={sfreq} onChange={(e) => setSfreq(e.target.value)} inputMode="decimal" placeholder="e.g. 250" />
                  </Field>
                )}
                {(inspect.format === "mat" || needsDataKey) && (
                  <Field label="MAT variable" hint="The array that holds the EEG samples.">
                    <select value={dataKey} onChange={(e) => setDataKey(e.target.value)}>
                      <option value="">Choose…</option>
                      {(inspect.candidates || []).map((c) => (
                        <option key={c.key} value={c.key}>
                          {c.key} {JSON.stringify(c.shape)}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                <Field label="Montage (optional)" hint="e.g. standard_1020">
                  <input value={montage} onChange={(e) => setMontage(e.target.value)} />
                </Field>
                <label className="check">
                  <input type="checkbox" checked={transpose} onChange={(e) => setTranspose(e.target.checked)} />
                  Transpose (data is samples × channels)
                </label>
              </div>
            )}
            {columns.length > 0 && (
              <details className="raw" open>
                <summary>Columns ({columns.length}) — set each column’s role</summary>
                <div className="table-wrap tall">
                  <table className="table">
                    <thead>
                      <tr>
                        <th className="r">#</th>
                        <th>Label</th>
                        <th>Role</th>
                      </tr>
                    </thead>
                    <tbody>
                      {columns.map((col, i) => (
                        <tr key={col.index}>
                          <td className="r num">{col.index + 1}</td>
                          <td>
                            <input
                              value={col.name}
                              onChange={(e) => {
                                const name = e.target.value;
                                setColumns((cols) => cols.map((c, j) => (j === i ? { ...c, name } : c)));
                              }}
                            />
                          </td>
                          <td>
                            <select
                              value={col.role}
                              onChange={(e) => {
                                const role = e.target.value;
                                setColumns((cols) => cols.map((c, j) => (j === i ? { ...c, role } : c)));
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
              </details>
            )}
            {!inspectErr && <div className="form-row">{subjectSelect}</div>}
          </div>
        )}

        <div className="form-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void importRecording()}
            disabled={!idle || !!importBlock}
          >
            Import recording
          </button>
          <Reason text={importBlock} />
        </div>
      </Card>

      <Card
        title="Attach another modality"
        description="Import a non-EEG stream (motion, ECG, eye tracking, …) into an existing recording or as a new one. Streams are not assumed to be time-aligned — set up synchronization in the Preprocess step."
      >
        <div className="form-row">
          <Field label="File" wide>
            <div className="input-group">
              <input value={extPath} onChange={(e) => setExtPath(e.target.value)} placeholder="/path/to/stream.csv" className="mono" />
              <button type="button" className="btn" onClick={() => void browseExternal()} disabled={!idle}>
                Browse…
              </button>
            </div>
          </Field>
        </div>
        {extInspect && (
          <p className="help">
            Detected {extInspect.format ?? "file"}
            {extInspect.suggested_modality ? ` · suggested modality: ${extInspect.suggested_modality}` : ""}
          </p>
        )}
        <div className="form-row">
          <Field label="Modality">
            <select value={extModality} onChange={(e) => setExtModality(e.target.value)}>
              {STREAM_MODALITIES.map((m) => (
                <option key={m} value={m}>
                  {m.replace("_", " ")}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Sampling rate (Hz)" error={extSfreq && !extSfreqCheck.ok ? extSfreqCheck.error : null}>
            <input value={extSfreq} onChange={(e) => setExtSfreq(e.target.value)} inputMode="decimal" placeholder="e.g. 100" />
          </Field>
          <Field label="Units (optional)">
            <input value={extUnits} onChange={(e) => setExtUnits(e.target.value)} placeholder="e.g. deg/s" />
          </Field>
          <Field label="Attach to">
            <select value={extAttachEff} onChange={(e) => setExtAttach(e.target.value)}>
              <option value={NEW_RECORDING}>New recording</option>
              {recRows.map((r) => (
                <option key={r.rec.id} value={r.rec.id}>
                  {recordingLabel(r)}
                </option>
              ))}
            </select>
          </Field>
          {extAttachEff === NEW_RECORDING && subjectSelect}
        </div>
        <div className="form-actions">
          <button type="button" className="btn btn-primary" onClick={() => void importExternalStream()} disabled={!idle || !!extBlock}>
            Import stream
          </button>
          <Reason text={extBlock} />
        </div>
      </Card>
    </>
  );
}
