import { Card, RawResult } from "../../components/ui";
import { fmtDate } from "../../lib/format";
import { NeedRecording } from "./RecordingPicker";
import type { StudySession } from "../../hooks/useStudySession";
import type { StudyLists } from "../../hooks/useStudyLists";
import type { Results } from "../../hooks/useResults";

/** NeuroFlow → Analyze: feature extraction and statistics for the selected recording. */
export function AnalyzeStage({ session, lists, res, idle, onImport }: {
  session: StudySession;
  lists: StudyLists;
  res: Results;
  idle: boolean;
  onImport: () => void;
}) {
  const { selectedRecId, recRows } = session;
  const { featuresets, analyses } = lists;
  const { results, runFlow } = res;
  return !selectedRecId ? (
    <NeedRecording what="Analysis" recordingCount={recRows.length} onImport={onImport} />
  ) : (
    <>
      <Card
        title="Feature extraction"
        description="Compute features from this recording."
        actions={
          <>
            <button
              type="button"
              className="btn"
              disabled={!idle}
              onClick={() => void runFlow("features", "Extracting band power", "features.extract", { kind: "band_power" }, (r: any) => `Extracted ${r.n_features} band-power features`)}
            >
              Band power
            </button>
            <button
              type="button"
              className="btn"
              disabled={!idle}
              onClick={() => void runFlow("features", "Extracting PSD summary", "features.extract", { kind: "psd" }, (r: any) => `Extracted ${r.n_features} PSD features`)}
            >
              PSD summary
            </button>
          </>
        }
      >
        {featuresets.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Kind</th>
                  <th className="r">Features</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {featuresets.map((f) => (
                  <tr key={f.id}>
                    <td>{f.name}</td>
                    <td>{f.kind}</td>
                    <td className="r num">{f.n_features}</td>
                    <td className="muted">{fmtDate(f.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="help">No feature sets for this recording yet.</p>
        )}
      </Card>

      <Card
        title="Statistics"
        description="Descriptive statistics use the latest feature set; condition comparison uses epochs."
        actions={
          <>
            <button
              type="button"
              className="btn"
              disabled={!idle}
              onClick={() => void runFlow("analysis", "Running descriptive statistics", "analysis.run", { kind: "descriptive" }, "Descriptive statistics complete")}
            >
              Descriptive
            </button>
            <button
              type="button"
              className="btn"
              disabled={!idle}
              onClick={() =>
                void runFlow("analysis", "Comparing conditions", "analysis.run", { kind: "compare_conditions" }, "Condition comparison complete")
              }
            >
              Compare conditions
            </button>
          </>
        }
      >
        {analyses.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Kind</th>
                  <th>Summary</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {analyses.map((a) => (
                  <tr key={a.id}>
                    <td>{a.name}</td>
                    <td>{a.kind}</td>
                    <td className="mono muted clip">{a.summary ? JSON.stringify(a.summary) : "—"}</td>
                    <td className="muted">{fmtDate(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="help">No analyses for this recording yet.</p>
        )}
        <RawResult value={results.analysis} label="Latest analysis result" />
      </Card>
    </>
  );
}
