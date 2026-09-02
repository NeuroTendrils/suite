import { useMemo, useState } from "react";

import { suiteCall } from "../ipc";
import "./BatchRunner.css";

export type BatchOutcome = {
  recording_id: string;
  subject_id: string;
  subject_label: string;
  session_id: string;
  run_id: string;
  status: "ok" | "failed" | "blocked" | "skipped";
  reason: string | null;
  message: string | null;
  artifact_ids: string[];
  duration_ms: number;
};

export type BatchReport = {
  study_id: string;
  plan_id: string;
  plan_name: string;
  dry_run: boolean;
  totals: { total: number; ok: number; failed: number; blocked: number; skipped: number };
  duration_ms: number;
  outcomes: BatchOutcome[];
};

export type BatchRunnerProps = {
  studyId: string;
  planId: string;
  planName: string;
  onClose: () => void;
  onComplete?: (report: BatchReport) => void;
};

/** Reason codes are stable; the copy lives here so the backend stays terse. */
const REASON_COPY: Record<string, string> = {
  no_eeg_stream: "No EEG stream attached",
  not_normalized: "Not normalized yet",
  validation_failed: "Failed validation",
  unsynced_multistream: "Multiple streams, no sync group",
  already_processed: "Already processed by this plan",
  executor_error: "Processing error",
};

/** What the researcher should actually do about it. */
const REASON_FIX: Record<string, string> = {
  no_eeg_stream: "Import an EEG recording, or scope the batch to EEG only.",
  not_normalized: "Run Normalize on these recordings first.",
  validation_failed: "Open each recording and resolve the validation errors.",
  unsynced_multistream: "Create a sync group, or restrict the batch to the EEG modality.",
  already_processed: "Turn on “Re-derive” to run them again.",
};

export function BatchRunner({
  studyId,
  planId,
  planName,
  onClose,
  onComplete,
}: BatchRunnerProps) {
  const [phase, setPhase] = useState<"idle" | "previewing" | "ready" | "running" | "done">(
    "idle",
  );
  const [report, setReport] = useState<BatchReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [force, setForce] = useState(false);

  async function preview() {
    setPhase("previewing");
    setError(null);
    try {
      const r = await suiteCall<BatchReport>("batch.preview", {
        study_id: studyId,
        plan_id: planId,
        force,
      });
      setReport(r);
      setPhase("ready");
    } catch (e) {
      setError(String(e));
      setPhase("idle");
    }
  }

  async function execute() {
    setPhase("running");
    setError(null);
    try {
      const r = await suiteCall<BatchReport>("batch.execute", {
        study_id: studyId,
        plan_id: planId,
        force,
      });
      setReport(r);
      setPhase("done");
      onComplete?.(r);
    } catch (e) {
      setError(String(e));
      setPhase("ready");
    }
  }

  // Group non-runnable recordings by cause so the researcher fixes a class of
  // problem once instead of reading forty individual rows.
  const grouped = useMemo(() => {
    if (!report) return [];
    const map = new Map<string, BatchOutcome[]>();
    for (const o of report.outcomes) {
      if (o.status === "ok") continue;
      const key = o.reason ?? "unknown";
      const list = map.get(key) ?? [];
      list.push(o);
      map.set(key, list);
    }
    return [...map.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [report]);

  const eligible = report ? report.totals.ok : 0;

  return (
    <div className="batch" role="dialog" aria-modal="true" aria-label="Apply plan to study">
      <div className="batch__panel">
        <header className="batch__head">
          <div>
            <h2>Apply to study</h2>
            <p>{planName}</p>
          </div>
          <button type="button" className="batch__x" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="batch__body">
          {phase === "idle" && (
            <div className="batch__empty">
              <p>
                Check this plan against every recording in the study before anything is
                written. Nothing changes until you run it.
              </p>
              <button type="button" className="btn btn--primary" onClick={preview}>
                Check the study
              </button>
            </div>
          )}

          {phase === "previewing" && <p className="batch__status">Checking recordings…</p>}
          {phase === "running" && (
            <p className="batch__status">
              Processing {eligible} recordings — a failure on one will not stop the rest.
            </p>
          )}

          {report && (phase === "ready" || phase === "done") && (
            <>
              <div className="batch__tally">
                <Tally n={report.totals.ok} label={phase === "done" ? "processed" : "ready"} tone="ok" />
                {report.totals.skipped > 0 && (
                  <Tally n={report.totals.skipped} label="skipped" tone="dim" />
                )}
                {report.totals.blocked > 0 && (
                  <Tally n={report.totals.blocked} label="blocked" tone="warn" />
                )}
                {report.totals.failed > 0 && (
                  <Tally n={report.totals.failed} label="failed" tone="bad" />
                )}
              </div>

              {grouped.length > 0 && (
                <div className="batch__groups">
                  {grouped.map(([reason, list]) => (
                    <details key={reason} className="batch__group">
                      <summary>
                        <span className="batch__gcount num">{list.length}</span>
                        <span>{REASON_COPY[reason] ?? reason}</span>
                      </summary>
                      {REASON_FIX[reason] && <p className="batch__fix">{REASON_FIX[reason]}</p>}
                      <ul>
                        {list.slice(0, 40).map((o) => (
                          <li key={o.recording_id}>
                            <span className="num">{o.subject_label}</span>
                            <span className="batch__rid num">
                              {o.recording_id.slice(0, 12)}
                            </span>
                            {o.message && <span className="batch__msg">{o.message}</span>}
                          </li>
                        ))}
                      </ul>
                      {list.length > 40 && (
                        <p className="batch__more">and {list.length - 40} more</p>
                      )}
                    </details>
                  ))}
                </div>
              )}

              {grouped.length === 0 && phase === "ready" && (
                <p className="batch__clean">Every recording in this study can be processed.</p>
              )}
            </>
          )}

          {error && <p className="batch__error">{error}</p>}
        </div>

        <footer className="batch__foot">
          <label className="batch__toggle">
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => {
                setForce(e.target.checked);
                if (phase === "ready") setPhase("idle");
              }}
            />
            Re-derive recordings this plan already produced
          </label>
          <div className="batch__spacer" />
          <button type="button" className="btn" onClick={onClose}>
            {phase === "done" ? "Close" : "Cancel"}
          </button>
          {phase === "ready" && (
            <button
              type="button"
              className="btn btn--primary"
              onClick={execute}
              disabled={eligible === 0}
            >
              {eligible === 0
                ? "Nothing to process"
                : `Process ${eligible} recording${eligible === 1 ? "" : "s"}`}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

function Tally({ n, label, tone }: { n: number; label: string; tone: string }) {
  return (
    <div className="batch__tallyItem" data-tone={tone}>
      <span className="num">{n}</span>
      <em>{label}</em>
    </div>
  );
}
