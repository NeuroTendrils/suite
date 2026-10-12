import { Badge, Card, Field, RawResult, Reason } from "../../components/ui";
import { EpochTable, ValidationBadge } from "../../components/tables";
import { fmtDate, issueText, shortId } from "../../lib/format";
import { EPOCH_WINDOW } from "../../lib/constants";
import { NeedRecording } from "./RecordingPicker";
import type { StudySession } from "../../hooks/useStudySession";
import type { StudyLists } from "../../hooks/useStudyLists";
import type { Results } from "../../hooks/useResults";
import type { Preprocess } from "../../hooks/usePreprocess";

/** NeuroFlow → Preprocess: synchronize streams, validate, manage events, run a preprocessing plan, create epochs. */
export function PreprocessStage({ session, lists, res, pre, idle, onImport }: {
  session: StudySession;
  lists: StudyLists;
  res: Results;
  pre: Preprocess;
  idle: boolean;
  onImport: () => void;
}) {
  const { selectedRecId, recRows, selectedRec } = session;
  const { plans, recEpochsets } = lists;
  const { results, runFlow } = res;
  const {
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
  } = pre;
  const selectedPlan = plans.find((p) => p.id === effPlanId) ?? null;
  const planRun = results.planRun as { artifacts?: Array<{ id: string; operation?: string }> } | undefined;
  return !selectedRecId ? (
    <NeedRecording what="Preprocessing" recordingCount={recRows.length} onImport={onImport} />
  ) : (
    <>
      <Card
        title="Synchronization"
        description="Streams are never assumed to be aligned because their start times look similar. Align them with shared triggers, timestamps, or a manual offset."
      >
        {selectedRec && selectedRec.streams.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Stream</th>
                  <th className="r">Rate</th>
                  <th className="r">Channels</th>
                  <th>ID</th>
                </tr>
              </thead>
              <tbody>
                {selectedRec.streams.map((s) => (
                  <tr key={s.id}>
                    <td>{s.modality}</td>
                    <td className="r num">{s.sfreq ?? "?"} Hz</td>
                    <td className="r num">{s.n_channels}</td>
                    <td className="mono muted">{shortId(s.id, 14)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="form-row">
          <Field label="Method">
            <select value={syncMethod} onChange={(e) => setSyncMethod(e.target.value)}>
              <option value="shared_triggers">Shared triggers</option>
              <option value="timestamps">Timestamps</option>
              <option value="manual_offset">Manual offset</option>
            </select>
          </Field>
          <button type="button" className="btn" onClick={() => void createSync()} disabled={!idle}>
            Create sync group
          </button>
        </div>
        {syncGroups.map((g) => (
          <div key={g.id} className="subcard">
            <div className="subcard-head">
              <span className="mono">{shortId(g.id, 14)}</span>
              <span>{g.method}</span>
              <span className="num">confidence {Number(g.quality?.mean_confidence ?? 0).toFixed(2)}</span>
              {g.quality?.assumed_synchronized ? <Badge tone="warn">assumed synchronized</Badge> : null}
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Stream</th>
                  <th>Method</th>
                  <th>Offset (s)</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {g.links.map((l) => (
                  <tr key={l.stream_id}>
                    <td className="mono">
                      {shortId(l.stream_id)}
                      {l.manual ? " (manual)" : ""}
                    </td>
                    <td>{l.method}</td>
                    <td>
                      <input
                        className="num w-num"
                        value={offsetEdits[l.stream_id] ?? String(l.offset_sec)}
                        onChange={(e) => setOffsetEdits((m) => ({ ...m, [l.stream_id]: e.target.value }))}
                      />
                    </td>
                    <td>
                      <button type="button" className="btn btn-sm" onClick={() => void applyOffset(g.id, l.stream_id)} disabled={!idle}>
                        Set
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        {!syncGroups.length && <p className="help">No sync groups for this recording yet.</p>}
      </Card>

      <Card
        title="Validation"
        description="Checks the recording (or whole study) for blocking problems and warnings. Results are saved with the recording."
        actions={
          <>
            <button type="button" className="btn" onClick={() => void runValidate("recording")} disabled={!idle}>
              Validate recording
            </button>
            <button type="button" className="btn" onClick={() => void runValidate("study")} disabled={!idle}>
              Validate study
            </button>
          </>
        }
      >
        {validation ? (
          <div>
            <div className="result-line">
              {validation.report.ok ? <Badge tone="ok">passed</Badge> : <Badge tone="danger">problems found</Badge>}
              <span>{validation.scope === "study" ? "Whole study" : "This recording"}</span>
              <span className="num">
                {validation.report.blocking_errors?.length ?? 0} errors · {validation.report.warnings?.length ?? 0} warnings
              </span>
            </div>
            {!!validation.report.blocking_errors?.length && (
              <ul className="issues danger">
                {validation.report.blocking_errors.map((x, i) => (
                  <li key={i}>{issueText(x)}</li>
                ))}
              </ul>
            )}
            {!!validation.report.warnings?.length && (
              <ul className="issues warn">
                {validation.report.warnings.map((x, i) => (
                  <li key={i}>{issueText(x)}</li>
                ))}
              </ul>
            )}
            <RawResult value={validation.report} label="Full validation report" />
          </div>
        ) : selectedRec && selectedRec.validation_ok != null ? (
          <p className="help">
            Last saved result: <ValidationBadge ok={selectedRec.validation_ok} errors={selectedRec.validation_errors} warnings={selectedRec.validation_warnings} />{" "}
            Run again to see details.
          </p>
        ) : (
          <p className="help">Not validated yet.</p>
        )}
      </Card>

      <Card
        title="Events"
        description="Event markers drive epochs and ERPs."
        actions={
          <button type="button" className="btn" onClick={() => void loadEvents()} disabled={!idle}>
            {events ? "Reload events" : "Show events"}
          </button>
        }
      >
        <form
          className="form-row"
          onSubmit={(e) => {
            e.preventDefault();
            void addEvent();
          }}
        >
          <Field label="Time (s)">
            <input className="num w-num" value={eventTime} onChange={(e) => setEventTime(e.target.value)} inputMode="decimal" />
          </Field>
          <Field label="Name">
            <input value={eventName} onChange={(e) => setEventName(e.target.value)} />
          </Field>
          <button type="submit" className="btn" disabled={!idle}>
            Add event
          </button>
        </form>
        {events &&
          (events.length ? (
            <div className="table-wrap tall">
              <table className="table">
                <thead>
                  <tr>
                    <th className="r">Time (s)</th>
                    <th>Name</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev: any, i: number) => (
                    <tr key={ev.id ?? i}>
                      <td className="r num">{Number(ev.timestamp ?? ev.onset ?? 0).toFixed(3)}</td>
                      <td>{ev.mapped_name ?? ev.name}</td>
                      <td className="muted">{ev.source ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="help">This recording has no events.</p>
          ))}
      </Card>

      <Card
        title="Preprocessing plan"
        description="A plan is an ordered list of processing steps. Running it writes derived artifacts; the source recording is never modified."
      >
        <div className="form-row">
          <Field label="Plan">
            <select value={effPlanId} onChange={(e) => setSelectedPlanId(e.target.value)} disabled={!plans.length}>
              {!plans.length && <option value="">No plans yet</option>}
              {plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.version ? ` (v${p.version})` : ""}
                  {p.created_at ? ` · ${fmtDate(p.created_at)}` : ""}
                </option>
              ))}
            </select>
          </Field>
          <button type="button" className="btn" onClick={() => void createDefaultPlan()} disabled={!idle}>
            Create default plan
          </button>
          <button type="button" className="btn btn-primary" onClick={() => void executePlan()} disabled={!idle || !effPlanId}>
            Run on this recording
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => void runFlow("recommend", "Requesting recommendation", "neuroflow.recommend_preprocessing")}
            disabled={!idle}
          >
            Recommend steps
          </button>
        </div>
        {!plans.length && <Reason text="Create a plan first. The default plan is a fixed, EEGLAB-tutorial-aligned sequence; it is not adapted to your data." />}
        {selectedPlan && (
          <ol className="plan-steps">
            {selectedPlan.steps.map((s, i) => (
              <li key={i}>
                <span className="mono">{s.operation}</span>
                {s.parameters && Object.keys(s.parameters).length > 0 && (
                  <span className="muted mono"> {JSON.stringify(s.parameters)}</span>
                )}
              </li>
            ))}
          </ol>
        )}
        {planRun && (
          <p className="help">
            Last run wrote {planRun.artifacts?.length ?? 0} artifact{planRun.artifacts?.length === 1 ? "" : "s"}
            {planRun.artifacts?.length ? `: ${planRun.artifacts.map((a) => a.operation ?? shortId(a.id)).join(" → ")}` : "."}
          </p>
        )}
        <RawResult value={results.recommend} label="Recommendation (placeholder heuristic)" />
        <RawResult value={results.plan} label="Default plan details" />
      </Card>

      <Card
        title="Epochs"
        description={`Cut the recording into trials around each event, ${EPOCH_WINDOW.tmin} to ${EPOCH_WINDOW.tmax} s. NeuroStudio datasets are built from epochs.`}
        actions={
          <button type="button" className="btn btn-primary" onClick={() => void createEpochs()} disabled={!idle}>
            Create epochs
          </button>
        }
      >
        {recEpochsets.length ? (
          <EpochTable rows={recEpochsets} />
        ) : (
          <p className="help">No epochs for this recording yet. The recording needs events.</p>
        )}
      </Card>
    </>
  );
}
