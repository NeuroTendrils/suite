/** Pages, workflow stages, and main navigation. */

import type { StepDef } from "../components/ui";

export type Page = "home" | "flow" | "studio";
export type FlowStage = "recording" | "inspect" | "plan" | "review";
export type StudioStage = "data" | "train" | "export";

export const FLOW_STAGES: Array<{ id: FlowStage; label: string; title: string; description: string }> = [
  {
    id: "recording",
    label: "Import",
    title: "Import recording",
    description:
      "Bring EEG into the study, or attach another modality (motion, ECG, eye tracking…) to an existing recording. Source files are copied in and never modified.",
  },
  {
    id: "inspect",
    label: "Inspect",
    title: "Inspect signal",
    description:
      "Review raw channels, mark bad channels and segments, and look at ICA components, ERPs, and epochs.",
  },
  {
    id: "plan",
    label: "Preprocess",
    title: "Align, validate, and preprocess",
    description:
      "Synchronize streams, validate the recording, manage events, run a preprocessing plan, and create epochs.",
  },
  {
    id: "review",
    label: "Analyze",
    title: "Features and statistics",
    description: "Extract features and run descriptive statistics or condition comparisons on this recording.",
  },
];

export const STUDIO_STAGES: Array<{ id: StudioStage; label: string; title: string; description: string }> = [
  {
    id: "data",
    label: "Dataset",
    title: "Datasets and splits",
    description: "Build a machine-learning dataset from epochs, then create a leakage-aware train/validation/test split.",
  },
  {
    id: "train",
    label: "Train",
    title: "Train and evaluate",
    description: "Create an experiment from a dataset and split, train it, then evaluate, explain, and run inference.",
  },
  {
    id: "export",
    label: "Report & export",
    title: "Reports and export",
    description: "Generate Markdown reports and export the study package or a trained model bundle.",
  },
];

export const NAV_ITEMS: Array<{ id: Page; label: string; sub: string; icon: string }> = [
  { id: "home", label: "Home", sub: "Studies and progress", icon: "home" },
  { id: "flow", label: "NeuroFlow", sub: "Recordings: import, clean", icon: "flow" },
  { id: "studio", label: "NeuroStudio", sub: "Datasets, models, export", icon: "studio" },
];

// Step states come only from backend data: "done" means the step's output exists.
const NO_STUDY_HINT = "Create or choose a study first.";

export function flowStepStates(s: {
  studySelected: boolean;
  recordingSelected: boolean;
  recordingCount: number;
  /** Epoch sets saved for the selected recording. */
  recordingEpochsets: number;
  /** Feature sets + analyses saved for the selected recording. */
  recordingResults: number;
}): StepDef[] {
  const noRecHint = s.recordingCount ? "Choose a recording first." : "Import a recording first.";
  return FLOW_STAGES.map((st) => {
    if (!s.studySelected) return { id: st.id, label: st.label, status: "unavailable", hint: NO_STUDY_HINT };
    if (st.id === "recording") {
      return s.recordingSelected
        ? { id: st.id, label: st.label, status: "done", hint: "A recording is imported and selected." }
        : { id: st.id, label: st.label, status: "available" };
    }
    if (!s.recordingSelected) return { id: st.id, label: st.label, status: "unavailable", hint: noRecHint };
    if (st.id === "plan" && s.recordingEpochsets) {
      return { id: st.id, label: st.label, status: "done", hint: "Epochs exist for this recording." };
    }
    if (st.id === "review" && s.recordingResults) {
      return { id: st.id, label: st.label, status: "done", hint: "Features or statistics exist for this recording." };
    }
    return { id: st.id, label: st.label, status: "available" };
  });
}

export function studioStepStates(s: {
  studySelected: boolean;
  /** Epoch sets anywhere in the study. */
  epochsets: number;
  /** Some dataset has at least one split. */
  hasAnySplit: boolean;
  /** Experiments with a trained model (see isTrained). */
  trainedExperiments: number;
}): StepDef[] {
  return STUDIO_STAGES.map((st) => {
    if (!s.studySelected) return { id: st.id, label: st.label, status: "unavailable", hint: NO_STUDY_HINT };
    if (st.id === "data") {
      if (s.hasAnySplit) return { id: st.id, label: st.label, status: "done", hint: "A dataset with a split exists." };
      if (!s.epochsets) return { id: st.id, label: st.label, status: "unavailable", hint: "Create epochs in NeuroFlow first." };
      return { id: st.id, label: st.label, status: "available" };
    }
    if (st.id === "train") {
      if (s.trainedExperiments) return { id: st.id, label: st.label, status: "done", hint: "At least one experiment has a trained model." };
      if (!s.hasAnySplit) return { id: st.id, label: st.label, status: "unavailable", hint: "Build a dataset and create a split first." };
      return { id: st.id, label: st.label, status: "available" };
    }
    return { id: st.id, label: st.label, status: "available" };
  });
}

export type NavState = { page: Page; flowStage: FlowStage; studioStage: StudioStage };
export type NavTarget = { label: string; to: NavState };

/** Where the footer's Back and Next lead from the current NeuroFlow/NeuroStudio step.
 *  Back from a first step is Home; Next from NeuroFlow's last step is NeuroStudio's first. */
export function stageNeighbors(nav: NavState): { prev: NavTarget; next: NavTarget | null } {
  const home: NavTarget = { label: "Home", to: { ...nav, page: "home" } };
  if (nav.page === "flow") {
    const i = FLOW_STAGES.findIndex((s) => s.id === nav.flowStage);
    const p = FLOW_STAGES[i - 1];
    const n = FLOW_STAGES[i + 1];
    return {
      prev: p ? { label: p.label, to: { ...nav, flowStage: p.id } } : home,
      next: n
        ? { label: n.label, to: { ...nav, flowStage: n.id } }
        : { label: "NeuroStudio", to: { ...nav, page: "studio", studioStage: "data" } },
    };
  }
  const i = STUDIO_STAGES.findIndex((s) => s.id === nav.studioStage);
  const p = STUDIO_STAGES[i - 1];
  const n = STUDIO_STAGES[i + 1];
  return {
    prev: p ? { label: p.label, to: { ...nav, studioStage: p.id } } : home,
    next: n ? { label: n.label, to: { ...nav, studioStage: n.id } } : null,
  };
}
