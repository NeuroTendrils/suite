import { Field, Reason } from "./ui";
import type { StudyForms } from "../hooks/useStudyForms";

/** Create-study form. Shown on Home and in the NeuroFlow/NeuroStudio "no study" state. */
export function NewStudyForm({
  forms,
  idle,
  online,
  canCancel,
}: {
  forms: StudyForms;
  idle: boolean;
  online: boolean;
  /** Cancel only makes sense when other studies exist to fall back to. */
  canCancel: boolean;
}) {
  const {
    newStudyName,
    setNewStudyName,
    newStudyTask,
    setNewStudyTask,
    newStudyTouched,
    setNewStudyTouched,
    studyNameCheck,
    createStudy,
    closeNewStudy,
  } = forms;
  return (
    <form noValidate
      className="form-grid new-study"
      onSubmit={(e) => {
        e.preventDefault();
        void createStudy();
      }}
    >
      <Field
        label="Study name"
        error={newStudyTouched ? studyNameCheck.error : null}
        hint={studyNameCheck.warning ?? "For example: Auditory oddball pilot"}
      >
        <input
          autoFocus
          value={newStudyName}
          onChange={(e) => setNewStudyName(e.target.value)}
          onBlur={() => newStudyName && setNewStudyTouched(true)}
          maxLength={160}
          aria-required="true"
        />
      </Field>
      <Field label="Task or paradigm (optional)" hint="For example: oddball, motor imagery, resting state">
        <input value={newStudyTask} onChange={(e) => setNewStudyTask(e.target.value)} />
      </Field>
      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={!idle || (newStudyTouched && !studyNameCheck.ok)}>
          Create study
        </button>
        {canCancel && (
          <button type="button" className="btn" onClick={closeNewStudy}>
            Cancel
          </button>
        )}
        {!online && <Reason text="The backend is offline, so studies can’t be created right now." />}
      </div>
    </form>
  );
}
