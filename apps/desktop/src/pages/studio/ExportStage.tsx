import { Card, Reason } from "../../components/ui";
import type { Results } from "../../hooks/useResults";
import type { NeuroStudio } from "../../hooks/useNeuroStudio";

/** NeuroStudio → Report & export: Markdown reports, the study package, and trained model bundles. */
export function ExportStage({ res, studio, idle }: {
  res: Results;
  studio: NeuroStudio;
  idle: boolean;
}) {
  const { results, studioRun } = res;
  const { includeSamples, setIncludeSamples, selExperiment, modelBlock } = studio;
  const report = results.report as { markdown?: string; path?: string } | undefined;
  return (
    <>
      <Card
        title="Reports"
        description="Markdown reports are written to the study’s reports folder."
        actions={
          <>
            <button
              type="button"
              className="btn"
              disabled={!idle}
              onClick={() => void studioRun("report", "Building study summary", "neurostudio.report.build", {}, "Study summary written")}
            >
              Study summary
            </button>
            <button
              type="button"
              className="btn"
              disabled={!idle || !selExperiment}
              onClick={() =>
                selExperiment &&
                void studioRun("report", "Building experiment report", "neurostudio.report.build", { experiment_id: selExperiment.id }, "Experiment report written")
              }
              title={selExperiment ? `Report for ${selExperiment.id}` : "Create an experiment first"}
            >
              Experiment report
            </button>
          </>
        }
      >
        {report?.path && (
          <p className="help">
            Saved to <span className="mono">{report.path}</span>
          </p>
        )}
        {report?.markdown ? <pre className="doc">{report.markdown}</pre> : <p className="help">No report generated in this session.</p>}
      </Card>

      <Card title="Export" description="Exports are zip files written to the study’s exports folder.">
        <div className="form-row">
          <label className="check">
            <input type="checkbox" checked={includeSamples} onChange={(e) => setIncludeSamples(e.target.checked)} />
            Include sample data (FIF/NPY) — larger file
          </label>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!idle}
            onClick={() =>
              void studioRun("exportStudy", "Exporting study package", "study.export", { include_samples: includeSamples }, (r) =>
                `Study exported (${(r.bytes / 1024 / 1024).toFixed(1)} MB)`,
              )
            }
          >
            Export study package
          </button>
          <button
            type="button"
            className="btn"
            disabled={!idle || !!modelBlock}
            onClick={() =>
              selExperiment &&
              void studioRun("exportModel", "Exporting model bundle", "neurostudio.model.export", { experiment_id: selExperiment.id }, "Model bundle exported")
            }
          >
            Export model bundle
          </button>
        </div>
        <Reason text={modelBlock ? `Model bundle: ${modelBlock}` : null} />
        {(["exportStudy", "exportModel"] as const).map((k) => {
          const r = results[k] as { path?: string; note?: string } | undefined;
          return r?.path ? (
            <p key={k} className="help">
              {k === "exportStudy" ? "Study package" : "Model bundle"}: <span className="mono">{r.path}</span>
              {r.note ? ` — ${r.note}` : ""}
            </p>
          ) : null;
        })}
      </Card>
    </>
  );
}
