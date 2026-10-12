import { Card, Checklist, EmptyState, Field, Reason } from "../../components/ui";
import { SplitTable } from "../../components/tables";
import { fmtDate, shortId } from "../../lib/format";
import { findRecording, recordingLabel } from "../../lib/study";
import type { FlowStage } from "../../lib/workflow";
import type { StudySession } from "../../hooks/useStudySession";
import type { StudyLists } from "../../hooks/useStudyLists";
import type { NeuroStudio } from "../../hooks/useNeuroStudio";

/** NeuroStudio → Dataset: build a dataset from an epoch set, then create a leakage-aware split. */
export function DatasetStage({ session, lists, studio, idle, openFlow }: {
  session: StudySession;
  lists: StudyLists;
  studio: NeuroStudio;
  idle: boolean;
  openFlow: (stage: FlowStage) => void;
}) {
  const { manager, recRows } = session;
  const { epochsets, datasets } = lists;
  const {
    buildSource,
    setBuildSource,
    setSelDatasetId,
    setSelSplitId,
    splitMethod,
    setSplitMethod,
    splitVal,
    setSplitVal,
    splitTest,
    setSplitTest,
    splitSeed,
    setSplitSeed,
    effDatasetId,
    datasetSplits,
    effSplitId,
    effBuildEpochsetId,
    setBuildEpochsetId,
    fracCheck,
    seedCheck,
    selectedDataset,
    hasAnySplit,
    buildDataset,
    createSplit,
  } = studio;
  return !epochsets.length ? (
      <EmptyState
        title="No epochs in this study yet"
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => openFlow(recRows.length ? "plan" : "recording")}
          >
            {recRows.length ? "Create epochs in NeuroFlow" : "Import a recording"}
          </button>
        }
      >
        Datasets are built from epochs — trials cut around event markers. In NeuroFlow, open a recording with events
        and create epochs in the Preprocess step.
      </EmptyState>
    ) : (
      <>
        <Card title="Progress" description="Checked against what is saved in this study." className="card-checklist">
          <Checklist
            items={[
              { label: "Epochs exist in the study", ok: epochsets.length > 0, detail: `${epochsets.length} epoch set${epochsets.length === 1 ? "" : "s"}` },
              { label: "Dataset built", ok: datasets.length > 0, detail: datasets.length ? `${datasets.length} dataset${datasets.length === 1 ? "" : "s"}` : "Build one below" },
              { label: "Split created", ok: hasAnySplit, detail: hasAnySplit ? "Continue to Train" : "Select a dataset, then Create split" },
            ]}
          />
        </Card>
        <Card title="Build dataset" description="Turn an epoch set into a samples × features matrix with one label per trial (the event name).">
          <div className="form-row">
            <Field label="Epoch set" wide>
              <select value={effBuildEpochsetId} onChange={(e) => setBuildEpochsetId(e.target.value)}>
                {epochsets.map((e) => {
                  const row = findRecording(manager, e.recording_id);
                  return (
                    <option key={e.id} value={e.id}>
                      {row ? recordingLabel(row) : shortId(e.recording_id)} · {e.name} · {e.n_trials} trials ·{" "}
                      {e.event_names.join("/") || "no events"}
                    </option>
                  );
                })}
              </select>
            </Field>
            <Field label="Source">
              <select value={buildSource} onChange={(e) => setBuildSource(e.target.value as "epochs" | "multimodal")}>
                <option value="epochs">EEG epochs</option>
                <option value="multimodal">EEG + attached streams</option>
              </select>
            </Field>
            <button type="button" className="btn btn-primary" onClick={() => void buildDataset()} disabled={!idle || !effBuildEpochsetId}>
              Build dataset
            </button>
          </div>
          {(() => {
            const es = epochsets.find((e) => e.id === effBuildEpochsetId);
            return es && new Set(es.event_names).size < 2 ? (
              <Reason text="This epoch set has fewer than two event types. Training a classifier needs at least two classes." />
            ) : null;
          })()}
        </Card>

        <Card title="Datasets">
          {datasets.length ? (
            <div className="table-wrap">
              <table className="table table-click">
                <thead>
                  <tr>
                    <th />
                    <th>Name</th>
                    <th>Source</th>
                    <th className="r">Samples</th>
                    <th className="r">Features</th>
                    <th>Labels</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {datasets.map((d) => (
                    <tr key={d.id} className={d.id === effDatasetId ? "selected" : ""} onClick={() => setSelDatasetId(d.id)}>
                      <td>
                        <input type="radio" readOnly checked={d.id === effDatasetId} aria-label={`Select ${d.name}`} />
                      </td>
                      <td>{d.name}</td>
                      <td>{d.source}</td>
                      <td className="r num">{d.n_samples}</td>
                      <td className="r num">{d.n_features}</td>
                      <td>{d.label_names.join(", ") || "—"}</td>
                      <td className="muted">{fmtDate(d.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="help">No datasets yet. Build one above.</p>
          )}
        </Card>

        {selectedDataset && (
          <Card
            title={`Split “${selectedDataset.name}”`}
            description="Subject-wise splits keep every subject’s trials in one partition, which avoids leakage across subjects. Trial-wise stratified splits are only appropriate within a single subject and are flagged."
          >
            <div className="form-row">
              <Field label="Method">
                <select value={splitMethod} onChange={(e) => setSplitMethod(e.target.value as "subject" | "stratified_trial")}>
                  <option value="subject">By subject</option>
                  <option value="stratified_trial">Stratified by trial</option>
                </select>
              </Field>
              <Field label="Validation fraction">
                <input className="num w-num" value={splitVal} onChange={(e) => setSplitVal(e.target.value)} inputMode="decimal" />
              </Field>
              <Field label="Test fraction">
                <input className="num w-num" value={splitTest} onChange={(e) => setSplitTest(e.target.value)} inputMode="decimal" />
              </Field>
              <Field label="Random seed" hint="Same seed → same split.">
                <input className="num w-num" value={splitSeed} onChange={(e) => setSplitSeed(e.target.value)} inputMode="numeric" />
              </Field>
            </div>
            <div className="form-actions">
              <button type="button" className="btn btn-primary" onClick={() => void createSplit()} disabled={!idle || !fracCheck.ok || !seedCheck.ok}>
                Create split
              </button>
              <Reason text={!fracCheck.ok ? fracCheck.error : !seedCheck.ok ? seedCheck.error : null} />
            </div>
            {datasetSplits.length ? (
              <SplitTable rows={datasetSplits} selected={effSplitId} onSelect={setSelSplitId} />
            ) : (
              <p className="help">No splits for this dataset yet.</p>
            )}
          </Card>
        )}
      </>
    );
}
