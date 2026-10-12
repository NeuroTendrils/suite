/** Shapes of backend replies the UI reads. Mirrors the Python handlers; the backend is the source of truth. */

export type StudySummary = {
  id: string;
  name: string;
  task_name?: string | null;
  schema_version?: number;
  created_at?: string;
  subjects: Array<{ id: string; label: string }>;
};

export type InspectInfo = {
  format?: string;
  status?: string;
  self_describing?: boolean;
  required_config?: string[];
  sfreq?: number;
  candidates?: Array<{ key: string; shape: number[] }>;
  suggested_data_key?: string;
  suggested_modality?: string;
  warnings?: string[];
  error?: string;
  columns?: Array<{ index: number; name: string; role: string }>;
};

export type SyncGroup = {
  id: string;
  recording_id: string;
  reference_stream_id: string;
  method: string;
  links: Array<{
    stream_id: string;
    offset_sec: number;
    method: string;
    manual: boolean;
    quality: Record<string, unknown>;
  }>;
  quality: Record<string, unknown>;
};

export type Timeline = {
  recording_id: string;
  start: number;
  duration: number;
  streams: Array<{
    stream_id: string;
    modality: string;
    name: string | null;
    offset_sec: number;
    channels: string[];
    channel_status?: string[];
    times: number[];
    data: number[][];
    error?: string;
  }>;
  events: Array<{
    name: string;
    timestamp: number;
    end?: number;
    modality?: string;
    kind?: string;
    artifact?: boolean;
    id?: string;
  }>;
  sync: { sync_group_id: string; method: string } | null;
};

export type ValidationReport = {
  ok?: boolean;
  blocking_errors?: Array<string | { message?: string; code?: string }>;
  warnings?: Array<string | { message?: string; code?: string }>;
  [k: string]: unknown;
};

export type Plan = {
  id: string;
  name: string;
  version?: number;
  created_at?: string;
  steps: Array<{ operation: string; parameters?: Record<string, unknown> }>;
};

export type EpochSetSummary = {
  id: string;
  name: string;
  recording_id: string;
  n_trials: number;
  event_names: string[];
  tmin: number;
  tmax: number;
  created_at?: string;
};

export type FeatureSetSummary = {
  id: string;
  name: string;
  kind: string;
  recording_id: string;
  n_features: number;
  created_at?: string;
};

export type AnalysisSummary = {
  id: string;
  name: string;
  kind: string;
  recording_id: string | null;
  summary: Record<string, unknown> | null;
  created_at?: string;
};

export type DatasetSummary = {
  id: string;
  name: string;
  source: string;
  n_samples: number;
  n_features: number;
  label_names: string[];
  modalities: string[];
  created_at?: string;
};

export type Split = {
  id: string;
  dataset_id: string;
  method: string;
  train_indices: number[];
  val_indices: number[];
  test_indices: number[];
  train_subjects: string[];
  test_subjects: string[];
  leakage_check?: { ok?: boolean; warnings?: string[] };
  parameters?: Record<string, unknown>;
  created_at?: string;
};

export type ExperimentSummary = {
  id: string;
  template_id: string | null;
  input_artifact_id: string | null;
  metrics: Record<string, unknown> | null;
  model: { model_id?: string } | null;
  split_id?: string | null;
  leakage_check?: { ok?: boolean; warnings?: string[] } | null;
  created_at?: string;
};

export type VizMode = "signal" | "ica" | "erp" | "epochs";
