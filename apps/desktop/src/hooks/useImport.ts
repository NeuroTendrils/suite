import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { exec } from "../lib/backend";
import { EEG_EXTENSIONS, NEW_RECORDING, NEW_SUBJECT, STREAM_EXTENSIONS } from "../lib/constants";
import { inspectProblem } from "../lib/errors";
import { findRecording, parsePositive, validateSubjectLabel } from "../lib/study";
import type { InspectInfo } from "../types";
import type { Operations } from "./useOperations";
import type { StudySession } from "./useStudySession";

/** NeuroFlow → Import: EEG recordings and extra-modality streams.
 *  Form state lives here (not in the stage component) so a half-filled form survives navigation. */
export function useImport(ops: Operations, session: StudySession) {
  const { task, setNotice, log } = ops;
  const { selectedId, manager, selectedRecId, setSelectedRecId, refreshManager } = session;
  const [importPath, setImportPath] = useState("");
  const [captureSeconds, setCaptureSeconds] = useState("10");
  const [captureConsent, setCaptureConsent] = useState(false);
  const [inspect, setInspect] = useState<InspectInfo | null>(null);
  const [inspectedPath, setInspectedPath] = useState("");
  const [sfreq, setSfreq] = useState("");
  const [dataKey, setDataKey] = useState("");
  const [transpose, setTranspose] = useState(false);
  const [montage, setMontage] = useState("");
  const [columns, setColumns] = useState<Array<{ index: number; name: string; role: string }>>([]);
  const [importSubject, setImportSubject] = useState("");
  const [importNewLabel, setImportNewLabel] = useState("S001");
  const [extPath, setExtPath] = useState("");
  const [extInspect, setExtInspect] = useState<InspectInfo | null>(null);
  const [extModality, setExtModality] = useState("gyroscope");
  const [extSfreq, setExtSfreq] = useState("");
  const [extUnits, setExtUnits] = useState("");
  const [extAttach, setExtAttach] = useState("");

  // Per-study targets.
  useEffect(() => {
    setImportSubject("");
    setExtAttach("");
  }, [selectedId]);

  const importSubjectEff =
    manager?.subjects.some((s) => s.id === importSubject) || importSubject === NEW_SUBJECT
      ? importSubject
      : (manager?.subjects[0]?.id ?? NEW_SUBJECT);
  const extAttachEff = extAttach || selectedRecId || NEW_RECORDING;

  async function inspectImport(path: string) {
    const p = path.trim();
    if (!p) return;
    setInspect(null);
    setInspectedPath("");
    setColumns([]);
    setDataKey("");
    setTranspose(false);
    setMontage("");
    const info = await task("Inspecting file", () => exec<InspectInfo>("import.inspect", { path: p }));
    if (!info) return;
    setInspect(info);
    setInspectedPath(p);
    const problem = inspectProblem(info);
    if (problem) {
      setNotice({ kind: "error", ...problem });
      log("error", `Inspecting file failed — ${problem.title}`, problem.detail);
      return;
    }
    setNotice(null);
    log("info", `Inspected ${info.format ?? "file"}: ${info.status === "needs_config" ? "needs settings" : "ready to import"}`);
    if (info.suggested_data_key) setDataKey(info.suggested_data_key);
    setSfreq(typeof info.sfreq === "number" ? String(info.sfreq) : "");
    if (Array.isArray(info.columns)) {
      setColumns(
        info.columns.map((c) => ({ index: Number(c.index), name: String(c.name), role: String(c.role ?? "eeg") })),
      );
    }
  }

  async function captureInsight() {
    const seconds = Number(captureSeconds);
    if (!selectedId || !captureConsent || !Number.isInteger(seconds) || seconds < 2 || seconds > 30) return;
    const result = await task("Capturing Insight EEG", () => exec<{ path: string; warnings: string[] }>("insight.capture", {
      study_id: selectedId, seconds, consent_to_record: captureConsent,
    }));
    if (!result) return;
    setCaptureConsent(false);
    setImportPath(result.path);
    await inspectImport(result.path);
    setNotice({ kind: result.warnings.length ? "warn" : "success", title: "Insight capture saved locally",
      hint: [...result.warnings, "Review the settings and choose Import recording to add it to the study."].join(" · ") });
  }

  async function browseImport() {
    const selected = await open({
      multiple: false,
      title: "Import EEG recording",
      filters: [{ name: "EEG", extensions: EEG_EXTENSIONS }],
    });
    if (typeof selected !== "string" || !selected) return;
    setImportPath(selected);
    await inspectImport(selected);
  }

  const inspectErr = inspectProblem(inspect);
  const needsConfig = !inspectErr && (inspect?.status === "needs_config" || inspect?.self_describing === false);
  const needs = new Set(inspect?.required_config || []);
  const needsSfreq = needs.has("sfreq") || inspect?.status === "needs_config";
  const needsDataKey = needs.has("data_key");
  const sfreqCheck = needsSfreq ? parsePositive(sfreq, "Sampling rate") : null;
  const importNewLabelCheck =
    importSubjectEff === NEW_SUBJECT ? validateSubjectLabel(importNewLabel, manager?.subjects ?? []) : { ok: true as const };
  const importBlock: string | null = !importPath.trim()
    ? "Choose a file to import."
    : inspectedPath !== importPath.trim() || !inspect
      ? "Inspect the file first so its format and required settings are known."
      : inspectErr
        ? "This file could not be read. Choose a different file."
        : sfreqCheck && !sfreqCheck.ok
          ? "Enter the sampling rate. It cannot be read from this file format."
          : needsDataKey && !dataKey
            ? "Choose which MAT variable holds the EEG data."
            : !importNewLabelCheck.ok
              ? (importNewLabelCheck.error ?? "Enter a subject label.")
              : null;

  async function resolveImportTarget(): Promise<{ subject_id: string; session_id: string; run_id: string; label: string }> {
    if (!selectedId) throw new Error("no study selected");
    if (importSubjectEff === NEW_SUBJECT) {
      const label = importNewLabel.trim();
      const added = await exec<any>("subjects.add", { study_id: selectedId, label });
      log("info", `Created subject ${label}`);
      return { subject_id: added.subject.id, session_id: added.session_id, run_id: added.run_id, label };
    }
    const sub = manager?.subjects.find((s) => s.id === importSubjectEff);
    const ses = sub?.sessions[0];
    const run = ses?.runs[0];
    if (!sub || !ses || !run) {
      throw new Error(`Subject ${sub?.label ?? importSubjectEff} has no session/run to import into.`);
    }
    return { subject_id: sub.id, session_id: ses.id, run_id: run.id, label: sub.label };
  }

  async function importRecording() {
    if (!selectedId || importBlock) return;
    const res = await task(
      "Importing recording",
      async () => {
        const target = await resolveImportTarget();
        const payload: Record<string, unknown> = {
          study_id: selectedId,
          subject_id: target.subject_id,
          session_id: target.session_id,
          run_id: target.run_id,
          path: importPath.trim(),
        };
        if (needsSfreq && sfreqCheck?.ok) payload.sfreq = sfreqCheck.value;
        if (needsDataKey) payload.data_key = dataKey;
        if (transpose) payload.transpose = true;
        if (montage) payload.montage = montage;
        if (columns.length) payload.column_selection = columns;
        return exec<any>("import.recording", payload);
      },
      "Recording imported",
    );
    if (!res) return;
    // Reload first: selecting an id the loaded study doesn't contain yet would be dropped as stale.
    await refreshManager();
    setSelectedRecId(res.recording.id);
    setImportPath("");
    setInspect(null);
    setInspectedPath("");
    setColumns([]);
    setNotice({
      kind: "success",
      title: "Recording imported",
      hint: "Next: open the Inspect step to review the signal.",
    });
  }

  async function browseExternal() {
    const selected = await open({
      multiple: false,
      title: "Import external modality",
      filters: [{ name: "Streams", extensions: STREAM_EXTENSIONS }],
    });
    if (typeof selected !== "string" || !selected) return;
    setExtPath(selected);
    setExtInspect(null);
    const info = await task("Inspecting stream file", () => exec<InspectInfo>("import.stream.inspect", { path: selected }));
    if (!info) return;
    setExtInspect(info);
    if (info.suggested_modality) setExtModality(info.suggested_modality);
    if (typeof info.sfreq === "number") setExtSfreq(String(info.sfreq));
  }

  const extSfreqCheck = parsePositive(extSfreq, "Sampling rate");
  const extBlock: string | null = !extPath.trim()
    ? "Choose a stream file."
    : !extSfreqCheck.ok
      ? "Enter the stream's sampling rate in Hz."
      : extAttachEff === NEW_RECORDING && importSubjectEff === NEW_SUBJECT && !importNewLabelCheck.ok
        ? (importNewLabelCheck.error ?? "Enter a subject label.")
        : null;

  async function importExternalStream() {
    if (!selectedId || extBlock || !extSfreqCheck.ok) return;
    const hz = extSfreqCheck.value;
    const res = await task(
      "Importing stream",
      async () => {
        let target: { subject_id: string; session_id: string; run_id: string };
        let recording_id: string | undefined;
        if (extAttachEff !== NEW_RECORDING) {
          // Attach using the target recording's own subject/session/run.
          const row = findRecording(manager, extAttachEff);
          if (!row) throw new Error("The recording to attach to no longer exists.");
          target = { subject_id: row.subjectId, session_id: row.sessionId, run_id: row.runId };
          recording_id = row.rec.id;
        } else {
          target = await resolveImportTarget();
        }
        const payload: Record<string, unknown> = {
          study_id: selectedId,
          ...target,
          path: extPath.trim(),
          modality: extModality,
          sfreq: hz,
        };
        if (extUnits) payload.units = extUnits;
        if (recording_id) payload.recording_id = recording_id;
        return exec<any>("import.stream", payload);
      },
      (r) => `Imported ${r.stream.modality} stream`,
    );
    if (!res) return;
    await refreshManager();
    setSelectedRecId(res.recording.id);
    setExtPath("");
    setExtInspect(null);
  }

  return {
    captureSeconds, setCaptureSeconds, captureConsent, setCaptureConsent, captureInsight,
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
  };
}

export type ImportState = ReturnType<typeof useImport>;
