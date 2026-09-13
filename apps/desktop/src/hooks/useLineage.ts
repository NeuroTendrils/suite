import { useCallback, useEffect, useState } from "react";

import { suiteCall } from "../ipc";
import type { LineageStep } from "../components/LineageRibbon";

type ChainStep = {
  id: string;
  artifact_id: string;
  operation: string;
  label: string;
  detail: string;
  kind: "human" | "filter" | "io";
  parameters: Record<string, unknown>;
  parent_id: string | null;
  checksum: string | null;
  at: string | null;
  replayable: boolean;
};

type ChainResponse = {
  recording_id: string;
  steps: ChainStep[];
  head_index: number;
};

export type SignalWindow = {
  times: number[];
  data: number[][];
  channels: string[];
  artifact_id?: string;
  read_only?: boolean;
};

/**
 * Loads the provenance chain for a recording and, when the user scrubs back,
 * fetches the signal as it was at that step.
 *
 * The live view is never served from this hook. `replay` is null whenever the
 * cursor sits at head, so a bug in history fetching can only ever blank the
 * replay panel — it cannot show stale data as if it were current.
 */
export function useLineage(studyId: string | null, recordingId: string | null) {
  const [steps, setSteps] = useState<LineageStep[]>([]);
  const [rawSteps, setRawSteps] = useState<ChainStep[]>([]);
  const [headIndex, setHeadIndex] = useState(-1);
  const [cursor, setCursor] = useState(-1);
  const [replay, setReplay] = useState<SignalWindow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!studyId || !recordingId) {
      setSteps([]);
      setRawSteps([]);
      setCursor(-1);
      setReplay(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const chain = await suiteCall<ChainResponse>("lineage.chain", {
        study_id: studyId,
        recording_id: recordingId,
      });
      setRawSteps(chain.steps);
      setSteps(
        chain.steps.map((s) => ({
          id: s.id,
          label: s.label,
          detail: s.detail,
          kind: s.kind === "io" ? "io" : s.kind,
          artifactId: s.artifact_id,
          at: s.at ?? undefined,
        })),
      );
      setHeadIndex(chain.head_index);
      setCursor(chain.steps.length - 1);
      setReplay(null);
    } catch (e) {
      setError(String(e));
      setSteps([]);
      setRawSteps([]);
    } finally {
      setLoading(false);
    }
  }, [studyId, recordingId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const atHead = cursor === steps.length - 1;

  const scrubTo = useCallback(
    async (index: number, start = 0, duration = 5) => {
      setCursor(index);

      // At head the caller keeps rendering its own live window.
      if (index === steps.length - 1) {
        setReplay(null);
        return;
      }
      const step = rawSteps[index];
      if (!step || !step.replayable) {
        // A step that recorded a decision but wrote no signal has nothing to
        // show. Say so rather than leaving the previous trace on screen,
        // which would read as "this is what it looked like" and be wrong.
        setReplay(null);
        setError(
          `${step?.label ?? "This step"} recorded a decision but wrote no signal — nothing to replay here.`,
        );
        return;
      }
      setError(null);
      setLoading(true);
      try {
        const window = await suiteCall<SignalWindow>("lineage.signal_window", {
          study_id: studyId,
          recording_id: recordingId,
          artifact_id: step.artifact_id,
          start,
          duration,
        });
        setReplay(window);
      } catch (e) {
        setError(String(e));
        setReplay(null);
      } finally {
        setLoading(false);
      }
    },
    [rawSteps, steps.length, studyId, recordingId],
  );

  const returnToHead = useCallback(() => {
    setCursor(steps.length - 1);
    setReplay(null);
    setError(null);
  }, [steps.length]);

  return {
    steps,
    cursor,
    headIndex,
    atHead,
    replay,
    error,
    loading,
    scrubTo,
    returnToHead,
    refresh,
  };
}
