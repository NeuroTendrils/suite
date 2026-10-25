import { Badge, Card, Checklist, Field, RawResult, Reason } from "../../components/ui";
import { fmtDate, fmtMetric, metricLabel, shortId } from "../../lib/format";
import { isTrained } from "../../lib/study";
import type { StudyLists } from "../../hooks/useStudyLists";
import type { Results } from "../../hooks/useResults";
import type { NeuroStudio } from "../../hooks/useNeuroStudio";

/** NeuroStudio → Train: create an experiment from a dataset + split, train it, then evaluate, explain, and infer. */
export function TrainStage({ lists, res, studio, idle }: {
  lists: StudyLists;
  res: Results;
  studio: NeuroStudio;
  idle: boolean;
}) {
  const { epochsets, datasets, experiments } = lists;
  const { results, studioRun } = res;
  const {
    setSelDatasetId,
    setSelSplitId,
    setSelExperimentId,
    effDatasetId,
    datasetSplits,
    effSplitId,
    effExperimentId,
    selExperiment,
    selectedDataset,
    expBlock,
    modelBlock,
    recommendTemplate,
    createExperiment,
  } = studio;
  const evalMetrics = (results.eval as any)?.metrics as Record<string, any> | undefined;
  return (
    <>
      <Card title="Before you train" description="Each item is checked against what is saved in this study." className="card-checklist">
        <Checklist
          items={[
            { label: "Epochs exist in the study", ok: epochsets.length > 0, detail: epochsets.length ? `${epochsets.length} epoch set${epochsets.length === 1 ? "" : "s"}` : "Create them in NeuroFlow → Preprocess" },
            { label: "Dataset built", ok: datasets.length > 0, detail: selectedDataset ? selectedDataset.name : "Dataset step" },
            { label: "Split for the selected dataset", ok: !!effSplitId, detail: effSplitId ? "selected" : "Dataset step → Create split" },
            { label: "Experiment created", ok: !!selExperiment, detail: selExperiment ? shortId(selExperiment.id, 14) : "Create one below" },
            { label: "Model trained", ok: isTrained(selExperiment), detail: isTrained(selExperiment) ? "ready to evaluate" : "Train the selected experiment" },
          ]}
        />
      </Card>
      <Card
        title="New experiment"
        description="An experiment fixes a dataset and split so training and evaluation are reproducible."
      >
        <div className="note">
          New experiments compare regularized logistic regression and shrinkage LDA using training-only cross-validation
          with balanced accuracy. Scaling is fitted inside each fold. Independent subject/session folds are used when possible.
          Test data stays held out. Prediction probabilities are uncalibrated scores, not guarantees. EEGNet is a catalog placeholder. Accuracy on simulated EEG does not validate Insight recordings.
        </div>
        <div className="form-row">
          <Field label="Dataset">
            <select value={effDatasetId} onChange={(e) => setSelDatasetId(e.target.value)} disabled={!datasets.length}>
              {!datasets.length && <option value="">No datasets</option>}
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} · {d.n_samples} samples · {fmtDate(d.created_at)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Split">
            <select value={effSplitId} onChange={(e) => setSelSplitId(e.target.value)} disabled={!datasetSplits.length}>
              {!datasetSplits.length && <option value="">No splits</option>}
              {datasetSplits.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.method} · {s.train_indices.length}/{s.val_indices.length}/{s.test_indices.length} · {fmtDate(s.created_at)}
                </option>
              ))}
            </select>
          </Field>
          <button type="button" className="btn btn-primary" onClick={() => void createExperiment()} disabled={!idle || !!expBlock}>
            Create experiment
          </button>
          <button type="button" className="btn" onClick={() => void recommendTemplate()} disabled={!idle}>
            Recommend template
          </button>
        </div>
        <Reason text={expBlock} />
        {!!(results.recommend as any)?.recommendations?.length && (
          <p className="help">
            Recommended: {(results.recommend as any).recommendations.map((r: any) => r.template_id).join(", ")}
          </p>
        )}
      </Card>

      <Card title="Experiments">
        {experiments.length ? (
          <div className="table-wrap">
            <table className="table table-click">
              <thead>
                <tr>
                  <th />
                  <th>Experiment</th>
                  <th>Dataset</th>
                  <th>Status</th>
                  <th>Saved metrics</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {experiments.map((x) => {
                  const ds = datasets.find((d) => d.id === x.input_artifact_id);
                  const metrics = Object.entries(x.metrics || {});
                  return (
                    <tr key={x.id} className={x.id === effExperimentId ? "selected" : ""} onClick={() => setSelExperimentId(x.id)}>
                      <td>
                        <input type="radio" readOnly checked={x.id === effExperimentId} aria-label={`Select ${x.id}`} />
                      </td>
                      <td className="mono">{shortId(x.id, 14)}</td>
                      <td>{ds?.name ?? shortId(x.input_artifact_id)}</td>
                      <td>
                        {isTrained(x) ? <Badge tone="ok">trained</Badge> : <Badge>not trained</Badge>}{" "}
                        {x.leakage_check && x.leakage_check.ok === false && <Badge tone="warn">leakage warning</Badge>}
                      </td>
                      <td>
                        {metrics.length ? (
                          <span className="metric-chips">
                            {metrics.map(([k, v]) => (
                              <span key={k} className="metric-chip">
                                <span>{metricLabel(k)}</span>
                                <span className="num">{fmtMetric(v)}</span>
                              </span>
                            ))}
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="muted">{fmtDate(x.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="help">No experiments yet.</p>
        )}
      </Card>

      {selExperiment && (
        <Card
          title={`Experiment ${shortId(selExperiment.id, 14)}`}
          description={selExperiment.leakage_check?.warnings?.length ? `Leakage: ${selExperiment.leakage_check.warnings.join("; ")}` : undefined}
          actions={
            <>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!idle}
                onClick={() =>
                  void studioRun("train", "Training model", "neurostudio.train.start", { experiment_id: selExperiment.id }, (r) =>
                    `Trained on ${r.n_train} samples · classes: ${(r.classes || []).join(", ")}`,
                  )
                }
              >
                {isTrained(selExperiment) ? "Retrain model" : "Train model"}
              </button>
              <button
                type="button"
                className="btn"
                disabled={!idle || !!modelBlock}
                onClick={() =>
                  void studioRun("eval", "Evaluating on test split", "neurostudio.eval.run", { experiment_id: selExperiment.id, split: "test" }, (r) =>
                    `Test accuracy ${fmtMetric(r.metrics?.accuracy)} · macro F1 ${fmtMetric(r.metrics?.f1_macro)} (n=${r.metrics?.n})`,
                  )
                }
              >
                Evaluate
              </button>
              <button
                type="button"
                className="btn"
                disabled={!idle || !!modelBlock}
                onClick={() => void studioRun("explain", "Computing explanations", "neurostudio.explain.run", { experiment_id: selExperiment.id }, "Explanation computed")}
              >
                Explain
              </button>
              <button
                type="button"
                className="btn"
                disabled={!idle || !!modelBlock}
                onClick={() =>
                  void studioRun("infer", "Running inference on the test split", "neurostudio.infer.run", { experiment_id: selExperiment.id, split: "test" }, (r) => `Predicted ${r.labels?.length ?? 0} held-out test samples`)
                }
              >
                Infer
              </button>
            </>
          }
        >
          <Reason text={!isTrained(selExperiment) ? "Evaluate, Explain, and Infer need a trained model. Train this experiment first." : null} />
          {evalMetrics && (results.eval as any)?.result?.experiment_id === selExperiment.id && (
            <div className="metrics">
              <dl className="stats">
                <div>
                  <dt>Accuracy ({evalMetrics.split})</dt>
                  <dd className="num">{fmtMetric(evalMetrics.accuracy)}</dd>
                </div>
                <div>
                  <dt>Macro F1</dt>
                  <dd className="num">{fmtMetric(evalMetrics.f1_macro)}</dd>
                </div>
                <div>
                  <dt>Samples</dt>
                  <dd className="num">{evalMetrics.n}</dd>
                </div>
              </dl>
              <p className="help">Balanced accuracy: {fmtMetric(evalMetrics.balanced_accuracy)} · Cohen’s κ: {fmtMetric(evalMetrics.cohen_kappa)}.
                {Array.isArray(evalMetrics.accuracy_ci95_wilson) && ` Accuracy 95% interval: ${evalMetrics.accuracy_ci95_wilson.map((v: number) => fmtMetric(v)).join(" – ")}.`}
                {" "}{evalMetrics.uncertainty_note}</p>
              {!!evalMetrics.warnings?.length && <ul className="issues warn">{evalMetrics.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}</ul>}
              {Array.isArray(evalMetrics.confusion_matrix) && (
                <table className="table confusion">
                  <caption>Confusion matrix (rows: true, columns: predicted)</caption>
                  <thead>
                    <tr>
                      <th />
                      {(evalMetrics.classes || []).map((c: string) => (
                        <th key={c} className="r">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {evalMetrics.confusion_matrix.map((row: number[], i: number) => (
                      <tr key={i}>
                        <th>{evalMetrics.classes?.[i]}</th>
                        {row.map((v, j) => (
                          <td key={j} className={`r num ${i === j ? "diag" : ""}`}>
                            {v}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
          <RawResult value={results.train} label="Training output" />
          <RawResult value={results.explain} label="Explanation output" />
          <RawResult value={results.infer} label="Inference output" />
        </Card>
      )}
    </>
  );
}
