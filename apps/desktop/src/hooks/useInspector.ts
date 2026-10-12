import { useEffect, useState } from "react";
import { suiteCall } from "../ipc";
import { exec } from "../lib/backend";
import { EPOCH_WINDOW, ICA_COMPONENTS, CLEAN_Z_THRESH } from "../lib/constants";
import { describeError } from "../lib/errors";
import { newestFirst } from "../lib/study";
import type { FlowStage, Page } from "../lib/workflow";
import type { EpochSetSummary, Timeline, VizMode } from "../types";
import type { Operations } from "./useOperations";
import type { StudySession } from "./useStudySession";

/** NeuroFlow → Inspect: the signal window, unapplied rejection marks, ICA, ERP, and epoch review.
 *  Marks are only written when applied; until then they live here and survive navigation. */
export function useInspector(ops: Operations, session: StudySession, view: { page: Page; flowStage: FlowStage }) {
  const { task } = ops;
  const { selectedId, selectedRecId, online, refreshManager } = session;
  const { page, flowStage } = view;
  const [tlStart, setTlStart] = useState(0);
  const [tlDur, setTlDur] = useState(4);
  const [tlGain, setTlGain] = useState(1);
  const [tlBusy, setTlBusy] = useState(false);
  const [tlError, setTlError] = useState<string | null>(null);
  const [tlRev, setTlRev] = useState(0);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [vizMode, setVizMode] = useState<VizMode>("signal");
  const [pendingSegments, setPendingSegments] = useState<Array<{ start: number; end: number }>>([]);
  const [pendingBadChannels, setPendingBadChannels] = useState<string[]>([]);
  const [pendingUnrejectAnnIds, setPendingUnrejectAnnIds] = useState<string[]>([]);
  const [erpChannel, setErpChannel] = useState<string>("");
  const [icaData, setIcaData] = useState<any | null>(null);
  const [erpData, setErpData] = useState<any | null>(null);
  const [erpEvent, setErpEvent] = useState("");
  const [epochSet, setEpochSet] = useState<any | null>(null);
  const [pendingEpochReject, setPendingEpochReject] = useState<number[]>([]);

  // Everything here is per-recording; never carry it to another recording.
  useEffect(() => {
    setTimeline(null);
    setTlError(null);
    setTlStart(0);
    setIcaData(null);
    setErpData(null);
    setErpChannel("");
    setErpEvent("");
    setEpochSet(null);
    setPendingSegments([]);
    setPendingBadChannels([]);
    setPendingUnrejectAnnIds([]);
    setPendingEpochReject([]);
  }, [selectedId, selectedRecId]);

  // Auto-load the signal window for the selected recording.
  useEffect(() => {
    if (page !== "flow" || flowStage !== "inspect" || !selectedId || !selectedRecId || !online) return;
    let cancelled = false;
    setTlBusy(true);
    void suiteCall<Timeline>("recordings.timeline", {
      study_id: selectedId,
      recording_id: selectedRecId,
      start: Math.max(0, tlStart),
      duration: Math.max(0.1, tlDur),
      max_points: 800,
    })
      .then((tl) => {
        if (cancelled) return;
        setTimeline(tl);
        setTlError(null);
      })
      .catch((e) => {
        if (!cancelled) setTlError(describeError(e).detail);
      })
      .finally(() => {
        if (!cancelled) setTlBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page, flowStage, selectedId, selectedRecId, tlStart, tlDur, tlRev, online]);

  const marksPending = pendingSegments.length + pendingBadChannels.length + pendingUnrejectAnnIds.length;
  const pendingCount =
    pendingSegments.length + pendingBadChannels.length + pendingUnrejectAnnIds.length + pendingEpochReject.length;

  function clearMarks() {
    setPendingSegments([]);
    setPendingBadChannels([]);
    setPendingUnrejectAnnIds([]);
  }

  function toggleUnreject(annotationId: string) {
    setPendingUnrejectAnnIds((prev) =>
      prev.includes(annotationId) ? prev.filter((x) => x !== annotationId) : [...prev, annotationId],
    );
  }

  function nudgeTime(delta: number) {
    setTlStart((s) => Math.max(0, +(s + delta).toFixed(4)));
  }

  // ── Visualizer marks ──────────────────────────────────────────────────────
  function togglePendingBadChannel(channel: string) {
    setPendingBadChannels((prev) => (prev.includes(channel) ? prev.filter((c) => c !== channel) : [...prev, channel]));
  }

  function markPendingSegment(t0: number, t1: number) {
    setPendingSegments((prev) => [...prev, { start: t0, end: t1 }]);
  }

  function channelIsBad(channel: string): boolean {
    const st = timeline?.streams?.find((s) => s.modality === "eeg");
    if (!st) return false;
    const i = st.channels.indexOf(channel);
    if (i < 0) return false;
    return (st.channel_status?.[i] || "") === "bad";
  }

  /** Apply all pending marks. Failed items stay marked so nothing is silently lost. */
  async function applyRejectMarks() {
    if (!selectedId || !selectedRecId) return;
    if (!pendingSegments.length && !pendingBadChannels.length && !pendingUnrejectAnnIds.length) return;
    const base = { study_id: selectedId, recording_id: selectedRecId };
    const total = pendingSegments.length + pendingBadChannels.length + pendingUnrejectAnnIds.length;
    const res = await task(
      "Applying rejections",
      async () => {
        const keepSegs: typeof pendingSegments = [];
        const keepCh: string[] = [];
        const keepUn: string[] = [];
        let firstErr: unknown = null;
        for (const seg of pendingSegments) {
          try {
            await exec("artifacts.apply", {
              ...base,
              suggestion: {
                kind: "bad_segment",
                start: seg.start,
                end: seg.end,
                method: "manual_visualizer",
                reason: "REJECT in visualizer",
                placeholder: false,
              },
            });
          } catch (e) {
            keepSegs.push(seg);
            firstErr ??= e;
          }
        }
        for (const ch of pendingBadChannels) {
          try {
            await exec("channels.update", { ...base, channel_name: ch, bad: !channelIsBad(ch) });
          } catch (e) {
            keepCh.push(ch);
            firstErr ??= e;
          }
        }
        for (const annId of pendingUnrejectAnnIds) {
          try {
            await exec("artifacts.revert", { ...base, annotation_id: annId });
          } catch (e) {
            keepUn.push(annId);
            firstErr ??= e;
          }
        }
        setPendingSegments(keepSegs);
        setPendingBadChannels(keepCh);
        setPendingUnrejectAnnIds(keepUn);
        setTlRev((n) => n + 1);
        const failed = keepSegs.length + keepCh.length + keepUn.length;
        if (failed) {
          throw new Error(
            `${failed} of ${total} changes failed and are still marked; ${total - failed} were applied. First error: ${describeError(firstErr).detail}`,
          );
        }
        return total;
      },
      (n) => `Applied ${n} change${n === 1 ? "" : "s"}. The source recording is unchanged.`,
    );
    void res;
    await refreshManager();
  }

  async function loadIca() {
    if (!selectedId || !selectedRecId) return;
    const res = await task(
      `Fitting ICA (${ICA_COMPONENTS} components)`,
      () =>
        exec<any>("ica.components.list", {
          study_id: selectedId,
          recording_id: selectedRecId,
          n_components: ICA_COMPONENTS,
        }),
      (r) => `ICA ready: ${r.n_components} components`,
    );
    if (res) setIcaData(res);
  }

  async function toggleIcaReject(index: number) {
    if (!selectedId || !selectedRecId || !icaData) return;
    const comp = icaData.components?.find((c: any) => c.index === index);
    const action = comp?.rejected ? "keep" : "reject";
    const res = await task(
      action === "reject" ? `Marking IC${index} for removal` : `Keeping IC${index}`,
      async () => {
        await exec("ica.component.set_rejection", {
          study_id: selectedId,
          recording_id: selectedRecId,
          component_indices: [index],
          action,
        });
        return exec<any>("ica.components.list", {
          study_id: selectedId,
          recording_id: selectedRecId,
          n_components: ICA_COMPONENTS,
        });
      },
    );
    if (res) setIcaData(res);
  }

  async function loadErp() {
    if (!selectedId || !selectedRecId) return;
    const res = await task(
      "Computing ERP",
      () =>
        exec<any>("erp.compute", {
          study_id: selectedId,
          recording_id: selectedRecId,
          event_name: erpEvent || null,
          tmin: EPOCH_WINDOW.tmin,
          tmax: EPOCH_WINDOW.tmax,
          erpimage_channel: erpChannel || null,
        }),
      (r) => (r.status === "ok" ? `ERP computed from ${r.nave ?? 0} epochs` : `ERP: ${r.status}`),
    );
    if (res) setErpData(res);
  }

  async function applyIcaRemovals() {
    if (!selectedId || !selectedRecId) return;
    const res = await task(
      "Applying ICA removals",
      () =>
        exec<any>("ica.apply", {
          study_id: selectedId,
          recording_id: selectedRecId,
          n_components: ICA_COMPONENTS,
          use_as_working: true,
        }),
      (r) => `ICA applied: excluded [${(r.excluded || []).join(", ")}]. A new working FIF was written; the source is unchanged.`,
    );
    if (!res) return;
    setTlRev((n) => n + 1);
    setIcaData(null);
  }

  async function runCleanContinuous() {
    if (!selectedId || !selectedRecId) return;
    const res = await task(
      "Cleaning continuous data",
      () =>
        exec<any>("neuroflow.clean_continuous", {
          study_id: selectedId,
          recording_id: selectedRecId,
          z_thresh: CLEAN_Z_THRESH,
          use_as_working: true,
        }),
      (r) =>
        `Clean continuous: ${r.n_bad_spans} bad spans, ${r.duration_before?.toFixed?.(2)} → ${r.duration_after?.toFixed?.(2)} s${r.warning ? ` (${r.warning})` : ""}`,
    );
    if (res) setTlRev((n) => n + 1);
  }

  async function loadEpochSet(epochsetId?: string) {
    if (!selectedId || !selectedRecId) return;
    const res = await task("Loading epochs", async () => {
      let id = epochsetId;
      if (!id) {
        const listed = await exec<{ epochsets: EpochSetSummary[] }>("epochs.list", {
          study_id: selectedId,
          recording_id: selectedRecId,
        });
        id = newestFirst(listed.epochsets)[0]?.id;
      }
      if (!id) return null;
      return exec<any>("epochs.get", { study_id: selectedId, epochset_id: id });
    });
    setEpochSet(res ?? null);
    setPendingEpochReject([]);
  }

  function togglePendingEpoch(index: number) {
    setPendingEpochReject((prev) => (prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]));
  }

  async function applyEpochReject() {
    if (!selectedId || !epochSet?.id || !pendingEpochReject.length) return;
    const byIndex = new Map<number, any>((epochSet.trials || []).map((t: any) => [t.index, t]));
    const toReject = pendingEpochReject.filter((i) => !byIndex.get(i)?.rejected);
    const toKeep = pendingEpochReject.filter((i) => byIndex.get(i)?.rejected);
    const ok = await task(
      "Updating epoch rejections",
      async () => {
        if (toReject.length) {
          await exec("epochs.reject", {
            study_id: selectedId,
            epochset_id: epochSet.id,
            trial_indices: toReject,
            rejected: true,
            rewrite_fif: true,
          });
        }
        if (toKeep.length) {
          await exec("epochs.reject", {
            study_id: selectedId,
            epochset_id: epochSet.id,
            trial_indices: toKeep,
            rejected: false,
            rewrite_fif: true,
          });
        }
        return true;
      },
      `Rejected ${toReject.length}, restored ${toKeep.length} epoch${toReject.length + toKeep.length === 1 ? "" : "s"}`,
    );
    // Reload either way: on partial failure the server state is the truth.
    await loadEpochSet(epochSet.id);
    if (!ok) setPendingEpochReject(pendingEpochReject);
  }

  return {
    tlStart,
    setTlStart,
    tlDur,
    setTlDur,
    tlGain,
    setTlGain,
    tlBusy,
    tlError,
    setTlRev,
    timeline,
    vizMode,
    setVizMode,
    pendingSegments,
    pendingBadChannels,
    pendingUnrejectAnnIds,
    erpChannel,
    setErpChannel,
    icaData,
    erpData,
    erpEvent,
    setErpEvent,
    epochSet,
    pendingEpochReject,
    setPendingEpochReject,
    pendingCount,
    marksPending,
    clearMarks,
    toggleUnreject,
    nudgeTime,
    togglePendingBadChannel,
    markPendingSegment,
    applyRejectMarks,
    loadIca,
    toggleIcaReject,
    loadErp,
    applyIcaRemovals,
    runCleanContinuous,
    loadEpochSet,
    togglePendingEpoch,
    applyEpochReject,
  };
}

export type Inspector = ReturnType<typeof useInspector>;
