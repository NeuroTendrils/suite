import { useEffect, useState } from "react";
import { suiteCall } from "../ipc";
import { describeError } from "../lib/errors";
import { newestFirst } from "../lib/study";
import type { Page } from "../lib/workflow";
import type {
  AnalysisSummary,
  DatasetSummary,
  EpochSetSummary,
  ExperimentSummary,
  FeatureSetSummary,
  Plan,
  Split,
} from "../types";
import type { Operations } from "./useOperations";
import type { StudySession } from "./useStudySession";

export type HomeData = {
  epochsets: EpochSetSummary[];
  datasets: DatasetSummary[];
  experiments: ExperimentSummary[];
  plans: Plan[];
};

/** Saved study artifacts, re-read for the page being shown whenever the study,
 *  recording, or `listsRev` changes. Lists are newest-first. */
export function useStudyLists(ops: Operations, session: StudySession, page: Page) {
  const { log } = ops;
  const { selectedId, selectedRecId, listsRev, online } = session;
  const [homeData, setHomeData] = useState<HomeData | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [epochsets, setEpochsets] = useState<EpochSetSummary[]>([]);
  const [featuresets, setFeaturesets] = useState<FeatureSetSummary[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([]);
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [splits, setSplits] = useState<Split[]>([]);
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);

  // Per-study lists. (Epoch sets, feature sets, and analyses are replaced when the next load lands.)
  useEffect(() => {
    setPlans([]);
    setDatasets([]);
    setSplits([]);
    setExperiments([]);
    setHomeData(null);
  }, [selectedId]);

  // Lists used by NeuroFlow / NeuroStudio / Home progress. Read-only, not busy-gated.
  useEffect(() => {
    if (!selectedId || !online) return;
    let cancelled = false;
    const sid = selectedId;
    const settle = <T,>(p: Promise<T>, apply: (v: T) => void, what: string) =>
      p
        .then((v) => {
          if (!cancelled) apply(v);
        })
        .catch((e) => {
          if (!cancelled) log("error", `Loading ${what} failed`, describeError(e).detail);
        });

    if (page === "home") {
      void Promise.all([
        suiteCall<{ epochsets: EpochSetSummary[] }>("epochs.list", { study_id: sid }),
        suiteCall<{ datasets: DatasetSummary[] }>("datasets.list", { study_id: sid }),
        suiteCall<{ experiments: ExperimentSummary[] }>("neurostudio.experiments.list", { study_id: sid }),
        suiteCall<{ plans: Plan[] }>("plans.list", { study_id: sid }),
      ])
        .then(([e, d, x, pl]) => {
          if (cancelled) return;
          setHomeData({ epochsets: e.epochsets, datasets: d.datasets, experiments: x.experiments, plans: pl.plans });
        })
        .catch((err) => {
          if (cancelled) return;
          setHomeData(null);
          log("error", "Loading study progress failed", describeError(err).detail);
        });
    }
    if (page === "flow" || page === "studio") {
      void settle(
        suiteCall<{ epochsets: EpochSetSummary[] }>("epochs.list", { study_id: sid }),
        (r) => setEpochsets(newestFirst(r.epochsets)),
        "epochs",
      );
    }
    if (page === "flow") {
      void settle(
        suiteCall<{ plans: Plan[] }>("plans.list", { study_id: sid }),
        (r) => setPlans(newestFirst(r.plans)),
        "plans",
      );
      if (selectedRecId) {
        void settle(
          suiteCall<{ featuresets: FeatureSetSummary[] }>("features.list", { study_id: sid, recording_id: selectedRecId }),
          (r) => setFeaturesets(newestFirst(r.featuresets)),
          "feature sets",
        );
        void settle(
          suiteCall<{ reports: AnalysisSummary[] }>("analysis.list", { study_id: sid, recording_id: selectedRecId }),
          (r) => setAnalyses(newestFirst(r.reports)),
          "analyses",
        );
      } else {
        setFeaturesets([]);
        setAnalyses([]);
      }
    }
    if (page === "studio") {
      void settle(
        suiteCall<{ datasets: DatasetSummary[] }>("datasets.list", { study_id: sid }),
        (r) => setDatasets(newestFirst(r.datasets)),
        "datasets",
      );
      void settle(
        suiteCall<{ splits: Split[] }>("datasets.splits.list", { study_id: sid }),
        (r) => setSplits(newestFirst(r.splits)),
        "splits",
      );
      void settle(
        suiteCall<{ experiments: ExperimentSummary[] }>("neurostudio.experiments.list", { study_id: sid }),
        (r) => setExperiments(newestFirst(r.experiments)),
        "experiments",
      );
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, selectedId, selectedRecId, listsRev, online]);

  /** Epoch sets of the selected recording. */
  const recEpochsets = epochsets.filter((e) => e.recording_id === selectedRecId);

  return { homeData, plans, epochsets, recEpochsets, featuresets, analyses, datasets, splits, experiments };
}

export type StudyLists = ReturnType<typeof useStudyLists>;
