import type { ReactNode } from "react";
import { Card, EmptyState } from "../components/ui";

/** NeuroFlow/NeuroStudio before a study is chosen: create one in place, or pick one. */
export function NoStudy({
  module,
  hasStudies,
  newStudyForm,
  goHome,
}: {
  module: "NeuroFlow" | "NeuroStudio";
  hasStudies: boolean;
  newStudyForm: ReactNode;
  goHome: () => void;
}) {
  return !hasStudies ? (
    <Card
      className="card-feature"
      title="Create a study first"
      description={`${module} works inside a study — the container for one experiment’s subjects, recordings, and everything derived from them. Create one here and you can continue right away.`}
    >
      {newStudyForm}
    </Card>
  ) : (
    <EmptyState
      icon="info"
      title="Choose a study"
      actions={
        <button type="button" className="btn btn-primary" onClick={goHome}>
          Go to Home
        </button>
      }
    >
      {module} works inside a study. Choose one with the Study selector at the top of the window, or open Home to
      see all studies.
    </EmptyState>
  );
}
