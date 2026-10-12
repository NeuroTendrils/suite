import { useState } from "react";
import { exec } from "../lib/backend";
import { parseMetadata, validateStudyName, validateSubjectLabel } from "../lib/study";
import type { StudySummary } from "../types";
import type { Operations } from "./useOperations";
import type { StudySession } from "./useStudySession";

/** The new-study form (shown on Home and in the NeuroFlow/NeuroStudio empty states) and the
 *  add-subject form. Drafts live here so they survive navigation. */
export function useStudyForms(ops: Operations, session: StudySession, confirmDiscardPending: () => Promise<boolean>) {
  const { task } = ops;
  const { studies, manager, selectedId, setSelectedRecId, chooseStudy, refresh, refreshManager } = session;
  const [newStudyOpen, setNewStudyOpen] = useState(false);
  const [newStudyName, setNewStudyName] = useState("");
  const [newStudyTask, setNewStudyTask] = useState("");
  const [newStudyTouched, setNewStudyTouched] = useState(false);
  const [subjectLabel, setSubjectLabel] = useState("");
  const [subjectMeta, setSubjectMeta] = useState("");
  const [subjectTouched, setSubjectTouched] = useState(false);

  function openNewStudy() {
    setNewStudyOpen(true);
    setNewStudyTouched(false);
  }

  function closeNewStudy() {
    setNewStudyOpen(false);
    setNewStudyName("");
    setNewStudyTask("");
    setNewStudyTouched(false);
  }

  const studyNameCheck = validateStudyName(newStudyName, studies);

  async function createStudy() {
    setNewStudyTouched(true);
    if (!studyNameCheck.ok) return;
    if (!(await confirmDiscardPending())) return;
    const created = await task(
      "Creating study",
      () =>
        exec<StudySummary>("studies.create", {
          name: newStudyName.trim(),
          task_name: newStudyTask.trim() || null,
        }),
      (s) => `Study “${s.name}” created`,
    );
    if (!created) return;
    setNewStudyOpen(false);
    setNewStudyName("");
    setNewStudyTask("");
    setNewStudyTouched(false);
    setSelectedRecId(null);
    chooseStudy(created.id);
    // Stay where the study was created (Home, or the NeuroFlow/NeuroStudio empty state).
    await refresh(created.id);
  }

  const subjectCheck = validateSubjectLabel(subjectLabel, manager?.subjects ?? []);
  const subjectMetaCheck = parseMetadata(subjectMeta);

  async function addSubject() {
    setSubjectTouched(true);
    if (!selectedId || !subjectCheck.ok || !subjectMetaCheck.ok) return;
    const label = subjectLabel.trim();
    const ok = await task(
      "Adding subject",
      () =>
        exec("subjects.add", {
          study_id: selectedId,
          label,
          metadata: subjectMetaCheck.value,
        }),
      `Subject ${label} added`,
    );
    if (!ok) return;
    setSubjectLabel("");
    setSubjectMeta("");
    setSubjectTouched(false);
    await refreshManager();
  }

  return {
    newStudyOpen,
    newStudyName,
    setNewStudyName,
    newStudyTask,
    setNewStudyTask,
    newStudyTouched,
    setNewStudyTouched,
    studyNameCheck,
    openNewStudy,
    closeNewStudy,
    createStudy,
    subjectLabel,
    setSubjectLabel,
    subjectMeta,
    setSubjectMeta,
    subjectTouched,
    subjectCheck,
    subjectMetaCheck,
    addSubject,
  };
}

export type StudyForms = ReturnType<typeof useStudyForms>;
