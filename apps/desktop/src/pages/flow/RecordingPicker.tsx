import { EmptyState, Field } from "../../components/ui";
import { ValidationBadge } from "../../components/tables";
import { formatDuration, recordingLabel } from "../../lib/study";
import type { StudySession } from "../../hooks/useStudySession";

/** The recording that Inspect, Preprocess, and Analyze work on, with its key facts. */
export function RecordingPicker({
  session,
  onChange,
}: {
  session: StudySession;
  onChange: (id: string) => void | Promise<void>;
}) {
  const { recRows, selectedRec, selectedRecId } = session;
  return (
    <div className="picker">
      <Field label="Recording">
        <select value={selectedRecId ?? ""} onChange={(e) => void onChange(e.target.value)} disabled={!recRows.length}>
          <option value="">{recRows.length ? "Choose a recording…" : "No recordings in this study"}</option>
          {recRows.map((r) => (
            <option key={r.rec.id} value={r.rec.id}>
              {recordingLabel(r)}
            </option>
          ))}
        </select>
      </Field>
      {selectedRec && (
        <dl className="facts">
          <div>
            <dt>Format</dt>
            <dd>{selectedRec.source_format ?? "—"}</dd>
          </div>
          <div>
            <dt>Rate</dt>
            <dd className="num">{selectedRec.sampling_rate ? `${selectedRec.sampling_rate} Hz` : "—"}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd className="num">{formatDuration(selectedRec.duration)}</dd>
          </div>
          <div>
            <dt>Streams</dt>
            <dd className="num">{selectedRec.streams.length}</dd>
          </div>
          <div>
            <dt>Validation</dt>
            <dd>
              <ValidationBadge ok={selectedRec.validation_ok} errors={selectedRec.validation_errors} warnings={selectedRec.validation_warnings} />
            </dd>
          </div>
        </dl>
      )}
    </div>
  );
}

/** Empty state for a per-recording step when no recording is selected. */
export function NeedRecording({
  what,
  recordingCount,
  onImport,
}: {
  what: string;
  recordingCount: number;
  onImport: () => void;
}) {
  return (
    <EmptyState
      title={recordingCount ? "Choose a recording" : "No recordings yet"}
      actions={
        recordingCount ? null : (
          <button type="button" className="btn btn-primary" onClick={onImport}>
            Import a recording
          </button>
        )
      }
    >
      {recordingCount
        ? `${what} works on one recording at a time. Select it in the Recording field above.`
        : `${what} needs a recording. Import EEG into this study first.`}
    </EmptyState>
  );
}
