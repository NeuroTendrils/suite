import { useEffect, useMemo, useRef, useState } from "react";
import { suiteCall, waitForSuiteRuntime } from "../ipc";
import { describeError } from "../lib/errors";
import { readStored, writeStored } from "../lib/storage";
import { findRecording, flattenRecordings, type Manager } from "../lib/study";
import type { Connection } from "../components/ui";
import type { StudySummary } from "../types";
import type { Operations } from "./useOperations";

/** Backend connection, the study list, and the active study + recording.
 *  The backend is the source of truth: after any write, call `refreshManager()`
 *  (structure changed) or `bumpLists()` (only derived lists changed). */
export function useStudySession(ops: Operations) {
  const { log, setNotice, showError } = ops;
  const [conn, setConn] = useState<Connection>({ state: "connecting" });
  const connStateRef = useRef<Connection["state"]>("connecting");
  connStateRef.current = conn.state;

  const [studies, setStudies] = useState<StudySummary[]>([]);
  const [studiesLoaded, setStudiesLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Async replies compare against the ref, not render state, so a slow reply for a
  // study the user already left is never applied.
  const selectedIdRef = useRef<string | null>(null);
  const [manager, setManager] = useState<Manager | null>(null);
  const [managerLoading, setManagerLoading] = useState(false);
  const [selectedRecId, setSelectedRecId] = useState<string | null>(null);
  /** Bumped whenever study lists (epochs, datasets, …) should be re-read. */
  const [listsRev, setListsRev] = useState(0);

  function chooseStudy(id: string | null) {
    selectedIdRef.current = id;
    setSelectedId(id);
    writeStored("nt-study", id);
  }

  async function loadManager(studyId: string) {
    setManagerLoading(true);
    try {
      const mgr = await suiteCall<Manager>("studies.manager", { study_id: studyId });
      if (selectedIdRef.current === studyId) setManager(mgr);
      return mgr;
    } finally {
      setManagerLoading(false);
    }
  }

  /** Reload connection, study list, and the selected study. `preferId` wins over current selection. */
  async function refresh(preferId?: string | null) {
    try {
      await waitForSuiteRuntime();
      const health = await suiteCall<{ status: string; version: string }>("health");
      if (connStateRef.current === "offline") log("success", "Reconnected to backend");
      setConn({ state: "online", version: health.version });
      // A connection error is resolved once the backend answers again.
      setNotice((n) => (n?.kind === "error" && n.title.startsWith("Connecting to backend") ? null : n));
      const listed = await suiteCall<{ studies: StudySummary[] }>("studies.list");
      setStudies(listed.studies);
      setStudiesLoaded(true);
      const want = preferId !== undefined ? preferId : (selectedIdRef.current ?? readStored("nt-study"));
      const id =
        want && listed.studies.some((s) => s.id === want) ? want : (listed.studies[0]?.id ?? null);
      if (id !== selectedIdRef.current) chooseStudy(id);
      if (id) await loadManager(id);
      else setManager(null);
      setListsRev((n) => n + 1);
    } catch (e) {
      const f = describeError(e);
      setConn({ state: "offline", detail: f.detail });
      showError("Connecting to backend", e);
    }
  }

  async function refreshManager() {
    const id = selectedIdRef.current;
    if (!id) return;
    try {
      await loadManager(id);
      const listed = await suiteCall<{ studies: StudySummary[] }>("studies.list");
      setStudies(listed.studies);
    } catch (e) {
      showError("Reloading study", e);
    }
    setListsRev((n) => n + 1);
  }

  /** Make `id` the active study with no recording selected. Callers confirm discards first. */
  async function switchStudy(id: string) {
    chooseStudy(id);
    setSelectedRecId(null);
    setManager(null);
    try {
      await loadManager(id);
    } catch (e) {
      showError("Opening study", e);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const recRows = useMemo(() => flattenRecordings(manager), [manager]);
  const selectedRow = useMemo(() => findRecording(manager, selectedRecId), [manager, selectedRecId]);

  // Drop a recording selection that no longer exists in the loaded study.
  useEffect(() => {
    if (manager && selectedRecId && !findRecording(manager, selectedRecId)) setSelectedRecId(null);
  }, [manager, selectedRecId]);

  return {
    conn,
    online: conn.state === "online",
    studies,
    studiesLoaded,
    selectedId,
    selectedStudy: studies.find((s) => s.id === selectedId) ?? null,
    manager,
    managerLoading,
    selectedRecId,
    setSelectedRecId,
    recRows,
    selectedRow,
    selectedRec: selectedRow?.rec ?? null,
    listsRev,
    bumpLists: () => setListsRev((n) => n + 1),
    chooseStudy,
    refresh,
    refreshManager,
    switchStudy,
  };
}

export type StudySession = ReturnType<typeof useStudySession>;
