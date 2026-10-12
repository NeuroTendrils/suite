import { useEffect, useState } from "react";
import { exec } from "../lib/backend";
import { isTrained, validateSeed, validateSplitFractions } from "../lib/study";
import type { Operations } from "./useOperations";
import type { Results } from "./useResults";
import type { StudyLists } from "./useStudyLists";
import type { StudySession } from "./useStudySession";

/** NeuroStudio: dataset/split/experiment selection, the split form, and dataset → experiment actions.
 *  Training, evaluation, and export run through `studioRun` (useResults). */
export function useNeuroStudio(ops: Operations, session: StudySession, lists: StudyLists, setResult: Results["setResult"]) {
  const { task, setNotice } = ops;
  const { selectedId, bumpLists } = session;
  const { epochsets, recEpochsets, datasets, splits, experiments } = lists;
  const [buildEpochsetId, setBuildEpochsetId] = useState("");
  const [buildSource, setBuildSource] = useState<"epochs" | "multimodal">("epochs");
  const [selDatasetId, setSelDatasetId] = useState("");
  const [selSplitId, setSelSplitId] = useState("");
  const [selExperimentId, setSelExperimentId] = useState("");
  const [splitMethod, setSplitMethod] = useState<"subject" | "stratified_trial">("subject");
  const [splitVal, setSplitVal] = useState("0.15");
  const [splitTest, setSplitTest] = useState("0.2");
  const [splitSeed, setSplitSeed] = useState("0");
  const [includeSamples, setIncludeSamples] = useState(false);

  // Per-study selections.
  useEffect(() => {
    setSelDatasetId("");
    setSelSplitId("");
    setSelExperimentId("");
    setBuildEpochsetId("");
  }, [selectedId]);

  // Default selections follow the newest item unless the user picked one that still exists.
  const effDatasetId = datasets.some((d) => d.id === selDatasetId) ? selDatasetId : (datasets[0]?.id ?? "");
  const datasetSplits = splits.filter((s) => s.dataset_id === effDatasetId);
  const effSplitId = datasetSplits.some((s) => s.id === selSplitId) ? selSplitId : (datasetSplits[0]?.id ?? "");
  const effExperimentId = experiments.some((x) => x.id === selExperimentId)
    ? selExperimentId
    : (experiments[0]?.id ?? "");
  const selExperiment = experiments.find((x) => x.id === effExperimentId) ?? null;
  const effBuildEpochsetId = epochsets.some((e) => e.id === buildEpochsetId)
    ? buildEpochsetId
    : (recEpochsets[0]?.id ?? epochsets[0]?.id ?? "");
  const selectedDataset = datasets.find((d) => d.id === effDatasetId) ?? null;
  const hasAnySplit = datasets.some((d) => splits.some((sp) => sp.dataset_id === d.id));
  const expBlock = !effDatasetId ? "Build a dataset first." : !effSplitId ? "Create a split for this dataset first." : null;
  const modelBlock = !selExperiment ? "Create an experiment first." : !isTrained(selExperiment) ? "Train this experiment first." : null;
  const trainedExperiments = experiments.filter(isTrained);

  async function buildDataset() {
    const es = epochsets.find((e) => e.id === effBuildEpochsetId);
    if (!es || !selectedId) return;
    const r = await task(
      "Building dataset",
      () =>
        exec<any>("datasets.build", {
          study_id: selectedId,
          recording_id: es.recording_id,
          epochset_id: es.id,
          source: buildSource,
        }),
      (r) => `Dataset built: ${r.dataset.n_samples} samples × ${r.dataset.n_features} features`,
    );
    if (r) {
      setSelDatasetId(r.dataset.id);
      setResult("dataset", r);
      bumpLists();
    }
  }

  const fracCheck = validateSplitFractions(splitVal, splitTest);
  const seedCheck = validateSeed(splitSeed);

  async function createSplit() {
    if (!selectedId || !effDatasetId || !fracCheck.ok || !seedCheck.ok) return;
    const r = await task(
      "Creating split",
      () =>
        exec<any>("datasets.splits.create", {
          study_id: selectedId,
          dataset_id: effDatasetId,
          method: splitMethod,
          val_frac: fracCheck.val,
          test_frac: fracCheck.test,
          seed: seedCheck.value,
        }),
      (r) =>
        `Split created: ${r.split.train_indices.length} train / ${r.split.val_indices.length} val / ${r.split.test_indices.length} test`,
    );
    if (r) {
      setSelSplitId(r.split.id);
      setResult("split", r);
      bumpLists();
      const warns: string[] = r.split.leakage_check?.warnings ?? [];
      if (warns.length) {
        setNotice({ kind: "warn", title: "Split created with leakage warnings", hint: warns.join(" · ") });
      }
    }
  }

  async function recommendTemplate() {
    if (!selectedId) return;
    const r = await task("Requesting template recommendation", () =>
      exec<any>("neurostudio.templates.recommend", { study_id: selectedId }),
    );
    if (r) setResult("recommend", r);
  }

  async function createExperiment() {
    if (!selectedId || !effDatasetId || !effSplitId) return;
    const r = await task(
      "Creating experiment",
      () =>
        exec<any>("neurostudio.experiments.create", {
          study_id: selectedId,
          template_id: "eegnet",
          input_artifact_id: effDatasetId,
          split_definition: { split_id: effSplitId },
        }),
      "Experiment created",
    );
    if (!r) return;
    setSelExperimentId(r.experiment.id);
    setResult("experiment", r);
    bumpLists();
    const warns: string[] = r.leakage_check?.warnings ?? [];
    if (warns.length) {
      setNotice({ kind: "warn", title: "Experiment created with leakage warnings", hint: warns.join(" · ") });
    }
  }

  return {
    buildSource,
    setBuildSource,
    setSelDatasetId,
    setSelSplitId,
    setSelExperimentId,
    splitMethod,
    setSplitMethod,
    splitVal,
    setSplitVal,
    splitTest,
    setSplitTest,
    splitSeed,
    setSplitSeed,
    includeSamples,
    setIncludeSamples,
    effDatasetId,
    datasetSplits,
    effSplitId,
    effExperimentId,
    selExperiment,
    effBuildEpochsetId,
    setBuildEpochsetId,
    fracCheck,
    seedCheck,
    selectedDataset,
    hasAnySplit,
    expBlock,
    modelBlock,
    trainedExperiments,
    buildDataset,
    createSplit,
    recommendTemplate,
    createExperiment,
  };
}

export type NeuroStudio = ReturnType<typeof useNeuroStudio>;
