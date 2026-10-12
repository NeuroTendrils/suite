import { useEffect, useState } from "react";
import { exec } from "../lib/backend";
import type { Operations } from "./useOperations";
import type { StudySession } from "./useStudySession";

/** Latest reply of each command run in this session, keyed by purpose (e.g. "eval", "report").
 *  Cleared whenever the study or recording changes, so a result is never shown for the wrong data. */
export function useResults(ops: Operations, session: StudySession) {
  const { task } = ops;
  const { selectedId, selectedRecId, refreshManager, bumpLists } = session;
  const [results, setResults] = useState<Record<string, unknown>>({});

  useEffect(() => {
    setResults({});
  }, [selectedId, selectedRecId]);

  function setResult(key: string, value: unknown) {
    setResults((r) => ({ ...r, [key]: value }));
  }

  /** Run a study/recording-scoped command, store its result under `key`, then refresh. */
  async function runFlow<T = any>(
    key: string,
    label: string,
    cmd: string,
    params: Record<string, unknown> = {},
    done?: string | ((r: T) => string),
  ): Promise<T | null> {
    if (!selectedId) return null;
    const res = await task(
      label,
      () =>
        exec<T>(cmd, {
          study_id: selectedId,
          ...(selectedRecId ? { recording_id: selectedRecId } : {}),
          ...params,
        }),
      done,
    );
    if (res != null) {
      setResult(key, res);
      await refreshManager();
    }
    return res;
  }

  async function studioRun(key: string, label: string, cmd: string, params: Record<string, unknown>, done?: string | ((r: any) => string)) {
    if (!selectedId) return null;
    const r = await task(label, () => exec<any>(cmd, { study_id: selectedId, ...params }), done);
    if (r) {
      setResult(key, r);
      bumpLists();
    }
    return r;
  }

  return { results, setResult, runFlow, studioRun };
}

export type Results = ReturnType<typeof useResults>;
