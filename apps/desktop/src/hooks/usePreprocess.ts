import { useEffect, useState } from "react";
import { suiteCall } from "../ipc";
import { exec } from "../lib/backend";
import { EPOCH_WINDOW } from "../lib/constants";
import type { SyncGroup, ValidationReport } from "../types";
import type { Operations } from "./useOperations";
import type { StudyLists } from "./useStudyLists";
import type { Results } from "./useResults";
import type { StudySession } from "./useStudySession";

/** NeuroFlow → Preprocess: stream sync, validation, events, preprocessing plans, and epoch creation. */
export function usePreprocess(ops: Operations, session: StudySession, lists: StudyLists, runFlow: Results["runFlow"]) {
  const { task, setNotice } = ops;
  const { selectedId, selectedRecId, manager, refreshManager } = session;
  const { plans } = lists;
  const [syncMethod, setSyncMethod] = useState("shared_triggers");
  const [syncGroups, setSyncGroups] = useState<SyncGroup[]>([]);
  const [offsetEdits, setOffsetEdits] = useState<Record<string, string>>({});
  const [validation, setValidation] = useState<{ scope: "recording" | "study"; report: ValidationReport } | null>(null);
  const [eventName, setEventName] = useState("manual");
  const [eventTime, setEventTime] = useState("1.0");
  const [events, setEvents] = useState<any[] | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState("");

  // Per-recording results; never carried to another recording.
  useEffect(() => {
    setValidation(null);
    setEvents(null);
    setOffsetEdits({});
  }, [selectedId, selectedRecId]);

  // Per-study selection.
  useEffect(() => {
    setSelectedPlanId("");
  }, [selectedId]);

  useEffect(() => {
    if (selectedRecId && selectedId) {
      let cancelled = false;
      void suiteCall<{ sync_groups: SyncGroup[] }>("sync.list", {
        study_id: selectedId,
        recording_id: selectedRecId,
      })
        .then((r) => !cancelled && setSyncGroups(r.sync_groups))
        .catch(() => !cancelled && setSyncGroups([]));
      return () => {
        cancelled = true;
      };
    }
    setSyncGroups([]);
  }, [selectedRecId, selectedId, manager]);

  // Default selection follows the newest plan unless the user picked one that still exists.
  const effPlanId = plans.some((p) => p.id === selectedPlanId) ? selectedPlanId : (plans[0]?.id ?? "");

  async function createSync() {
    if (!selectedId || !selectedRecId) return;
    const res = await task(
      "Creating sync group",
      () =>
        exec<{ sync_group: SyncGroup }>("sync.create", {
          study_id: selectedId,
          recording_id: selectedRecId,
          method: syncMethod,
        }),
      (r) => `Sync group created (${r.sync_group.method})`,
    );
    if (res) await refreshManager();
  }

  async function applyOffset(syncGroupId: string, streamId: string) {
    if (!selectedId) return;
    const raw = offsetEdits[streamId] ?? "0";
    const offset = Number(raw);
    if (!raw.trim() || !Number.isFinite(offset)) {
      setNotice({ kind: "error", title: "Offset must be a number of seconds", detail: `got “${raw}”` });
      return;
    }
    const ok = await task(
      "Setting stream offset",
      () =>
        exec("sync.set_offset", {
          study_id: selectedId,
          sync_group_id: syncGroupId,
          stream_id: streamId,
          offset_sec: offset,
        }),
      `Offset set to ${offset} s`,
    );
    if (ok) await refreshManager();
  }

  async function runValidate(scope: "recording" | "study") {
    if (!selectedId) return;
    if (scope === "recording" && !selectedRecId) return;
    const report = await task(
      scope === "study" ? "Validating study" : "Validating recording",
      () =>
        scope === "study"
          ? exec<ValidationReport>("validate.study", { study_id: selectedId })
          : exec<ValidationReport>("validate.recording", { study_id: selectedId, recording_id: selectedRecId }),
      (r) =>
        `Validation ${r.ok ? "passed" : "found problems"}: ${r.blocking_errors?.length ?? 0} errors, ${r.warnings?.length ?? 0} warnings`,
    );
    if (!report) return;
    setValidation({ scope, report });
    await refreshManager();
  }

  async function loadEvents() {
    const r = await runFlow<{ events: any[] }>("events", "Loading events", "events.list");
    if (r) setEvents(r.events ?? []);
  }

  async function addEvent() {
    const t = Number(eventTime);
    if (!eventTime.trim() || !Number.isFinite(t) || t < 0) {
      setNotice({ kind: "error", title: "Event time must be a non-negative number of seconds", detail: `got “${eventTime}”` });
      return;
    }
    const name = eventName.trim() || "manual";
    const r = await runFlow("events", "Adding event", "events.create", { timestamp: t, name, source: "manual" }, `Event “${name}” added at ${t} s`);
    if (r) await loadEvents();
  }

  async function createEpochs() {
    const r = await runFlow<any>(
      "epochs",
      "Creating epochs",
      "epochs.create",
      { tmin: EPOCH_WINDOW.tmin, tmax: EPOCH_WINDOW.tmax, name: "epochs" },
      (r) => `Created ${r.n_trials} epochs`,
    );
    return r;
  }

  // ── Plans ─────────────────────────────────────────────────────────────────
  async function createDefaultPlan() {
    const r = await runFlow<any>("plan", "Creating default plan", "plans.default", {}, "Default plan created");
    if (r?.plan?.id) setSelectedPlanId(r.plan.id);
  }

  async function executePlan() {
    if (!effPlanId || !selectedRecId) return;
    const plan = plans.find((p) => p.id === effPlanId);
    await runFlow<any>(
      "planRun",
      `Running plan “${plan?.name ?? effPlanId}”`,
      "plans.execute",
      { plan_id: effPlanId },
      (r) => `Plan finished: ${r.artifacts?.length ?? 0} derived artifact${r.artifacts?.length === 1 ? "" : "s"} written`,
    );
  }

  return {
    syncMethod,
    setSyncMethod,
    syncGroups,
    offsetEdits,
    setOffsetEdits,
    validation,
    eventName,
    setEventName,
    eventTime,
    setEventTime,
    events,
    effPlanId,
    setSelectedPlanId,
    createSync,
    applyOffset,
    runValidate,
    loadEvents,
    addEvent,
    createEpochs,
    createDefaultPlan,
    executePlan,
  };
}

export type Preprocess = ReturnType<typeof usePreprocess>;
