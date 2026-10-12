import { useEffect, useMemo, useRef, useState } from "react";
import { ask, open } from "@tauri-apps/plugin-dialog";
import { suiteCall, waitForSuiteRuntime } from "./ipc";
import { backendFailure, describeError, inspectProblem } from "./lib/errors";
import {
  findRecording,
  flattenRecordings,
  formatDuration,
  importGate,
  isTrained,
  newestFirst,
  nextStep,
  parseMetadata,
  parsePositive,
  recentActivity,
  recordingLabel,
  trainGate,
  validateSeed,
  validateSplitFractions,
  validateStudyName,
  validateSubjectLabel,
  type Manager,
} from "./lib/study";
import {
  ActivityLog,
  Badge,
  BusyIndicator,
  Card,
  Checklist,
  ConnectionStatus,
  EmptyState,
  Field,
  Icon,
  NoticeBar,
  RawResult,
  Reason,
  Stepper,
  type Busy,
  type Connection,
  type LogEntry,
  type Notice,
  type StepDef,
} from "./components/ui";
import { useElementWidth } from "./lib/useElementWidth";
import "./App.css";

type StudySummary = {
  id: string;
  name: string;
  task_name?: string | null;
  schema_version?: number;
  created_at?: string;
  subjects: Array<{ id: string; label: string }>;
};

type InspectInfo = {
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

type SyncGroup = {
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

type Timeline = {
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

type ValidationReport = {
  ok?: boolean;
  blocking_errors?: Array<string | { message?: string; code?: string }>;
  warnings?: Array<string | { message?: string; code?: string }>;
  [k: string]: unknown;
};

type Plan = {
  id: string;
  name: string;
  version?: number;
  created_at?: string;
  steps: Array<{ operation: string; parameters?: Record<string, unknown> }>;
};

type EpochSetSummary = {
  id: string;
  name: string;
  recording_id: string;
  n_trials: number;
  event_names: string[];
  tmin: number;
  tmax: number;
  created_at?: string;
};

type FeatureSetSummary = {
  id: string;
  name: string;
  kind: string;
  recording_id: string;
  n_features: number;
  created_at?: string;
};

type AnalysisSummary = {
  id: string;
  name: string;
  kind: string;
  recording_id: string | null;
  summary: Record<string, unknown> | null;
  created_at?: string;
};

type DatasetSummary = {
  id: string;
  name: string;
  source: string;
  n_samples: number;
  n_features: number;
  label_names: string[];
  modalities: string[];
  created_at?: string;
};

type Split = {
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

type ExperimentSummary = {
  id: string;
  template_id: string | null;
  input_artifact_id: string | null;
  metrics: Record<string, unknown> | null;
  model: { model_id?: string } | null;
  split_id?: string | null;
  leakage_check?: { ok?: boolean; warnings?: string[] } | null;
  created_at?: string;
};

type VizMode = "signal" | "ica" | "erp" | "epochs";

type Page = "home" | "flow" | "studio";
type FlowStage = "recording" | "inspect" | "plan" | "review";
type StudioStage = "data" | "train" | "export";

const FLOW_STAGES: Array<{ id: FlowStage; label: string; title: string; description: string }> = [
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

const STUDIO_STAGES: Array<{ id: StudioStage; label: string; title: string; description: string }> = [
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

const NAV_ITEMS: Array<{ id: Page; label: string; sub: string; icon: string }> = [
  { id: "home", label: "Home", sub: "Studies and progress", icon: "home" },
  { id: "flow", label: "NeuroFlow", sub: "Recordings: import, clean", icon: "flow" },
  { id: "studio", label: "NeuroStudio", sub: "Datasets, models, export", icon: "studio" },
];

const NEW_SUBJECT = "__new_subject__";
const NEW_RECORDING = "__new_recording__";

const EEG_EXTENSIONS = ["fif", "edf", "bdf", "gdf", "set", "vhdr", "cnt", "mat", "txt", "csv", "tsv", "asc"];
const STREAM_EXTENSIONS = ["txt", "csv", "tsv", "asc", "mat", "npy"];
const STREAM_MODALITIES = [
  "gyroscope",
  "accelerometer",
  "ecg",
  "emg",
  "eog",
  "eye_tracking",
  "motion",
  "behavioral",
  "trigger",
  "gsr",
  "respiration",
  "misc",
];

/** Fixed parameters the existing UI has always sent. Shown to the user, not changed. */
const EPOCH_WINDOW = { tmin: -0.2, tmax: 0.8 };
const ICA_COMPONENTS = 15;
const CLEAN_Z_THRESH = 5;

type ThemeName = "dark" | "light";

function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string | null) {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

function readStoredTheme(): ThemeName {
  const v = readStored("nt-theme");
  return v === "light" ? "light" : "dark";
}

function shortId(id: string | null | undefined, n = 10): string {
  if (!id) return "—";
  return id.length > n ? `${id.slice(0, n)}…` : id;
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function issueText(i: string | { message?: string; code?: string }): string {
  return typeof i === "string" ? i : i.message || i.code || JSON.stringify(i);
}

/** Readable name for a saved experiment metric key, e.g. test_f1_macro → "test F1 (macro)". */
function metricLabel(key: string): string {
  return key
    .replace(/f1_macro/g, "F1 (macro)")
    .replace(/accuracy/g, "accuracy")
    .replace(/^n_/, "n ")
    .replace(/_/g, " ");
}

function fmtMetric(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (v == null) return "—";
  return typeof v === "string" ? v : JSON.stringify(v);
}

const EVENT_COLORS = ["#3dcf6a", "#e85d5d", "#5db0e8", "#e8c55d", "#c77dff"];

/** Interactive stacked plot: click channel label = toggle bad; drag = reject segment. */
function StackedStreamPlot({
  times,
  data,
  channels,
  channelStatus,
  events,
  start,
  duration,
  gain = 1,
  width = 720,
  rowH = 18,
  onChannelClick,
  onRegionSelect,
  onArtifactClick,
  pendingUnrejectIds = [],
}: {
  times: number[];
  data: number[][];
  channels: string[];
  channelStatus?: string[];
  events: Array<{
    name: string;
    timestamp: number;
    end?: number;
    kind?: string;
    artifact?: boolean;
    id?: string;
  }>;
  start: number;
  duration: number;
  gain?: number;
  width?: number;
  rowH?: number;
  onChannelClick?: (channel: string) => void;
  onRegionSelect?: (t0: number, t1: number) => void;
  onArtifactClick?: (annotationId: string) => void;
  pendingUnrejectIds?: string[];
}) {
  const n = Math.max(data.length, 1);
  const labelW = 56;
  const plotL = labelW;
  const plotR = width - 6;
  const plotW = plotR - plotL;
  const axisH = 22;
  const h = rowH * n + axisH + 8;
  const t0 = start;
  const t1 = start + duration;
  const xAt = (t: number) => plotL + ((t - t0) / (duration || 1)) * plotW;
  const tAt = (x: number) => t0 + ((x - plotL) / (plotW || 1)) * duration;
  const eventNames = [...new Set(events.map((e) => e.name))];
  const colorFor = (name: string) =>
    EVENT_COLORS[eventNames.indexOf(name) % EVENT_COLORS.length] ?? "#aaa";
  const g = Math.max(0.05, gain);
  const dragX = useRef<number | null>(null);
  const [dragCur, setDragCur] = useState<number | null>(null);

  const artifacts = events.filter(
    (e) => e.end != null && (e.artifact || e.kind === "annotation" || e.name === "artifact"),
  );

  return (
    <svg
      width={width}
      height={h}
      className="eegplot"
      style={{ cursor: onRegionSelect ? "crosshair" : "default" }}
      onMouseDown={(ev) => {
        if (!onRegionSelect) return;
        const rect = (ev.currentTarget as SVGSVGElement).getBoundingClientRect();
        const x = ev.clientX - rect.left;
        if (x < plotL || x > plotR) return;
        dragX.current = x;
        setDragCur(x);
      }}
      onMouseMove={(ev) => {
        if (dragX.current == null) return;
        const rect = (ev.currentTarget as SVGSVGElement).getBoundingClientRect();
        setDragCur(Math.min(plotR, Math.max(plotL, ev.clientX - rect.left)));
      }}
      onMouseUp={() => {
        if (dragX.current == null || dragCur == null || !onRegionSelect) {
          dragX.current = null;
          setDragCur(null);
          return;
        }
        const a = tAt(dragX.current);
        const b = tAt(dragCur);
        dragX.current = null;
        setDragCur(null);
        if (Math.abs(b - a) < 0.02) return;
        onRegionSelect(Math.min(a, b), Math.max(a, b));
      }}
      onMouseLeave={() => {
        dragX.current = null;
        setDragCur(null);
      }}
    >
      <rect x={0} y={0} width={width} height={h} fill="#0a0a0a" />
      {artifacts.map((a, i) => {
        const x0 = xAt(Math.max(t0, a.timestamp));
        const x1 = xAt(Math.min(t1, a.end ?? a.timestamp));
        const unrej = !!(a.id && pendingUnrejectIds.includes(a.id));
        return (
          <rect
            key={`art-${a.id || a.name}-${i}`}
            x={x0}
            y={4}
            width={Math.max(2, x1 - x0)}
            height={h - axisH - 4}
            fill={unrej ? "#3a6" : "#a33"}
            opacity={unrej ? 0.2 : 0.25}
            style={{ cursor: a.id && onArtifactClick ? "pointer" : undefined }}
            onClick={(e) => {
              if (!a.id || !onArtifactClick) return;
              e.stopPropagation();
              onArtifactClick(a.id);
            }}
            onMouseDown={(e) => {
              // don't start a drag-select when clicking an existing reject band
              if (a.id && onArtifactClick) e.stopPropagation();
            }}
          />
        );
      })}
      {dragX.current != null && dragCur != null && (
        <rect
          x={Math.min(dragX.current, dragCur)}
          y={4}
          width={Math.abs(dragCur - dragX.current)}
          height={h - axisH - 4}
          fill="#c66"
          opacity={0.35}
        />
      )}
      {data.map((vals, ci) => {
        const mid = 6 + ci * rowH + rowH / 2;
        const label = channels[ci] || `ch${ci + 1}`;
        const bad = (channelStatus?.[ci] || "") === "bad";
        let lo = Infinity;
        let hi = -Infinity;
        for (const v of vals) {
          if (v < lo) lo = v;
          if (v > hi) hi = v;
        }
        if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
          lo = 0;
          hi = 1;
        }
        const center = (lo + hi) / 2;
        let half = (hi - lo) / 2 || 1e-12;
        half = half / g;
        const amp = rowH * 0.42;
        const pts = vals
          .map((v, i) => {
            const t = times[i] ?? t0;
            const x = xAt(t);
            const y = mid - ((v - center) / half) * amp;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
          })
          .join(" ");
        return (
          <g key={`${label}-${ci}`}>
            <line
              x1={plotL}
              x2={plotR}
              y1={mid}
              y2={mid}
              stroke="#222"
              strokeWidth={1}
            />
            <text
              x={4}
              y={mid + 3}
              fill={bad ? "#f66" : "#9cf"}
              fontSize={10}
              fontFamily="ui-monospace, monospace"
              style={{ cursor: onChannelClick ? "pointer" : "default" }}
              onClick={(e) => {
                e.stopPropagation();
                onChannelClick?.(label);
              }}
            >
              {bad ? "×" : ""}
              {label.length > 7 ? label.slice(0, 7) : label}
            </text>
            {pts && (
              <polyline
                fill="none"
                stroke={bad ? "#844" : "#6af"}
                strokeWidth={1}
                opacity={bad ? 0.45 : 1}
                points={pts}
              />
            )}
          </g>
        );
      })}
      {events
        .filter((e) => e.end == null)
        .map((e, i) => {
          if (e.timestamp < t0 || e.timestamp > t1) return null;
          const x = xAt(e.timestamp);
          const col = colorFor(e.name);
          return (
            <g key={`ev-${i}-${e.timestamp}`}>
              <line
                x1={x}
                x2={x}
                y1={4}
                y2={h - axisH}
                stroke={col}
                strokeWidth={1.5}
                strokeDasharray="4 3"
              />
              <text
                x={x + 3}
                y={12 + (i % 3) * 11}
                fill={col}
                fontSize={10}
                fontFamily="ui-monospace, monospace"
              >
                {e.name}
              </text>
            </g>
          );
        })}
      {[0, 0.25, 0.5, 0.75, 1].map((f) => {
        const t = t0 + f * duration;
        const x = xAt(t);
        return (
          <g key={f}>
            <line
              x1={x}
              x2={x}
              y1={h - axisH}
              y2={h - axisH + 4}
              stroke="#888"
            />
            <text
              x={x}
              y={h - 6}
              fill="#aaa"
              fontSize={10}
              textAnchor="middle"
              fontFamily="ui-monospace, monospace"
            >
              {t.toFixed(2)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** EEGLAB-ish Channel ERPs: butterfly overlay + optional single-channel average. */
function ErpImagePlot({
  times,
  trials,
  vmin,
  vmax,
  width = 720,
  height = 220,
}: {
  times: number[];
  trials: number[][];
  vmin: number;
  vmax: number;
  width?: number;
  height?: number;
}) {
  const padL = 40;
  const padR = 12;
  const padT = 8;
  const padB = 24;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const nT = times.length || 1;
  const nE = trials.length || 1;
  const t0 = times[0] ?? 0;
  const t1 = times[times.length - 1] ?? 1;
  const span = vmax - vmin || 1;
  const cellW = plotW / nT;
  const cellH = plotH / nE;
  const colorAt = (v: number) => {
    const x = Math.max(0, Math.min(1, (v - vmin) / span));
    // blue → white → red
    if (x < 0.5) {
      const t = x * 2;
      const r = Math.round(40 + t * 200);
      const g = Math.round(80 + t * 160);
      const b = Math.round(180 + t * 60);
      return `rgb(${r},${g},${b})`;
    }
    const t = (x - 0.5) * 2;
    const r = Math.round(240);
    const g = Math.round(240 - t * 160);
    const b = Math.round(240 - t * 180);
    return `rgb(${r},${g},${b})`;
  };

  return (
    <svg width={width} height={height} className="eegplot">
      <rect x={0} y={0} width={width} height={height} fill="#0a0a0a" />
      {trials.map((row, ei) =>
        row.map((v, ti) => (
          <rect
            key={`${ei}-${ti}`}
            x={padL + ti * cellW}
            y={padT + ei * cellH}
            width={Math.max(1, cellW + 0.5)}
            height={Math.max(1, cellH + 0.5)}
            fill={colorAt(v)}
          />
        )),
      )}
      <line
        x1={padL + ((0 - t0) / (t1 - t0 || 1)) * plotW}
        x2={padL + ((0 - t0) / (t1 - t0 || 1)) * plotW}
        y1={padT}
        y2={height - padB}
        stroke="#e85d5d"
        strokeWidth={1}
        strokeDasharray="3 2"
      />
      <text x={4} y={padT + 10} fill="#888" fontSize={10}>
        trial
      </text>
      <text x={width / 2} y={height - 4} fill="#666" fontSize={9} textAnchor="middle">
        time (ms) · ERPimage
      </text>
    </svg>
  );
}

function ErpButterflyPlot({
  times,
  data,
  channels,
  highlight,
  width = 720,
  height = 280,
}: {
  times: number[];
  data: number[][];
  channels: string[];
  highlight?: string;
  width?: number;
  height?: number;
}) {
  const padL = 48;
  const padR = 12;
  const padT = 16;
  const padB = 28;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  let lo = Infinity;
  let hi = -Infinity;
  for (const row of data) {
    for (const v of row) {
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo === hi) {
    lo = -1;
    hi = 1;
  }
  const t0 = times[0] ?? 0;
  const t1 = times[times.length - 1] ?? 1;
  const xAt = (t: number) => padL + ((t - t0) / (t1 - t0 || 1)) * plotW;
  const yAt = (v: number) => padT + ((hi - v) / (hi - lo || 1)) * plotH;
  const hiIdx = highlight ? channels.indexOf(highlight) : -1;

  return (
    <svg width={width} height={height} className="eegplot">
      <rect x={0} y={0} width={width} height={height} fill="#0a0a0a" />
      {/* zero line */}
      <line
        x1={padL}
        x2={width - padR}
        y1={yAt(0)}
        y2={yAt(0)}
        stroke="#444"
        strokeWidth={1}
      />
      {/* stimulus onset */}
      <line
        x1={xAt(0)}
        x2={xAt(0)}
        y1={padT}
        y2={height - padB}
        stroke="#e85d5d"
        strokeWidth={1.5}
        strokeDasharray="4 3"
      />
      <text x={xAt(0) + 4} y={padT + 12} fill="#e85d5d" fontSize={10}>
        0
      </text>
      {data.map((row, ci) => {
        if (hiIdx >= 0 && ci !== hiIdx) return null;
        const pts = row
          .map((v, i) => `${xAt(times[i] ?? t0).toFixed(1)},${yAt(v).toFixed(1)}`)
          .join(" ");
        return (
          <polyline
            key={channels[ci] || ci}
            fill="none"
            stroke={hiIdx >= 0 ? "#6af" : `hsl(${(ci * 47) % 360} 55% 60%)`}
            strokeWidth={hiIdx >= 0 ? 2 : 1}
            opacity={hiIdx >= 0 ? 1 : 0.5}
            points={pts}
          />
        );
      })}
      <text x={4} y={padT + 8} fill="#888" fontSize={10}>
        {hi.toExponential(1)}
      </text>
      <text x={4} y={height - padB} fill="#888" fontSize={10}>
        {lo.toExponential(1)}
      </text>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => {
        const t = t0 + f * (t1 - t0);
        return (
          <text
            key={f}
            x={xAt(t)}
            y={height - 8}
            fill="#aaa"
            fontSize={10}
            textAnchor="middle"
          >
            {(t * 1000).toFixed(0)}
          </text>
        );
      })}
      <text x={width / 2} y={height - 2} fill="#666" fontSize={9} textAnchor="middle">
        time (ms)
      </text>
    </svg>
  );
}

function App() {
  // ── Connection, activity, feedback ────────────────────────────────────────
  const [conn, setConn] = useState<Connection>({ state: "connecting" });
  const connStateRef = useRef<Connection["state"]>("connecting");
  connStateRef.current = conn.state;
  const [busy, setBusy] = useState<Busy | null>(null);
  const busyRef = useRef(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const logSeq = useRef(0);
  const [logOpen, setLogOpen] = useState(false);

  // ── Navigation / chrome ───────────────────────────────────────────────────
  const [page, setPage] = useState<Page>("home");
  const [flowStage, setFlowStage] = useState<FlowStage>("recording");
  const [studioStage, setStudioStage] = useState<StudioStage>("data");
  const [theme, setTheme] = useState<ThemeName>(readStoredTheme);
  const [sidebarOpen, setSidebarOpen] = useState(() => readStored("nt-sidebar") !== "0");

  // ── Study state ───────────────────────────────────────────────────────────
  const [studies, setStudies] = useState<StudySummary[]>([]);
  const [studiesLoaded, setStudiesLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  const [manager, setManager] = useState<Manager | null>(null);
  const [managerLoading, setManagerLoading] = useState(false);
  const [selectedRecId, setSelectedRecId] = useState<string | null>(null);
  const [homeData, setHomeData] = useState<{
    epochsets: EpochSetSummary[];
    datasets: DatasetSummary[];
    experiments: ExperimentSummary[];
    plans: Plan[];
  } | null>(null);

  const [newStudyOpen, setNewStudyOpen] = useState(false);
  const [newStudyName, setNewStudyName] = useState("");
  const [newStudyTask, setNewStudyTask] = useState("");
  const [newStudyTouched, setNewStudyTouched] = useState(false);
  const [subjectLabel, setSubjectLabel] = useState("");
  const [subjectMeta, setSubjectMeta] = useState("");
  const [subjectTouched, setSubjectTouched] = useState(false);

  // ── Import ────────────────────────────────────────────────────────────────
  const [importPath, setImportPath] = useState("");
  const [inspect, setInspect] = useState<InspectInfo | null>(null);
  const [inspectedPath, setInspectedPath] = useState("");
  const [sfreq, setSfreq] = useState("");
  const [dataKey, setDataKey] = useState("");
  const [transpose, setTranspose] = useState(false);
  const [montage, setMontage] = useState("");
  const [columns, setColumns] = useState<Array<{ index: number; name: string; role: string }>>([]);
  const [importSubject, setImportSubject] = useState("");
  const [importNewLabel, setImportNewLabel] = useState("S001");
  const [extPath, setExtPath] = useState("");
  const [extInspect, setExtInspect] = useState<InspectInfo | null>(null);
  const [extModality, setExtModality] = useState("gyroscope");
  const [extSfreq, setExtSfreq] = useState("");
  const [extUnits, setExtUnits] = useState("");
  const [extAttach, setExtAttach] = useState("");

  // ── NeuroFlow ─────────────────────────────────────────────────────────────
  const [syncMethod, setSyncMethod] = useState("shared_triggers");
  const [syncGroups, setSyncGroups] = useState<SyncGroup[]>([]);
  const [offsetEdits, setOffsetEdits] = useState<Record<string, string>>({});
  const [validation, setValidation] = useState<{ scope: "recording" | "study"; report: ValidationReport } | null>(null);
  const [tlStart, setTlStart] = useState(0);
  const [tlDur, setTlDur] = useState(4);
  const [tlGain, setTlGain] = useState(1);
  const [tlBusy, setTlBusy] = useState(false);
  const [tlError, setTlError] = useState<string | null>(null);
  const [tlRev, setTlRev] = useState(0);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [vizMode, setVizMode] = useState<VizMode>("signal");
  const [pendingSegments, setPendingSegments] = useState<Array<{ start: number; end: number }>>([]);
  const [pendingBadChannels, setPendingBadChannels] = useState<string[]>([]);
  const [pendingUnrejectAnnIds, setPendingUnrejectAnnIds] = useState<string[]>([]);
  const [erpChannel, setErpChannel] = useState<string>("");
  const [icaData, setIcaData] = useState<any | null>(null);
  const [erpData, setErpData] = useState<any | null>(null);
  const [erpEvent, setErpEvent] = useState("");
  const [epochSet, setEpochSet] = useState<any | null>(null);
  const [pendingEpochReject, setPendingEpochReject] = useState<number[]>([]);
  const [eventName, setEventName] = useState("manual");
  const [eventTime, setEventTime] = useState("1.0");
  const [events, setEvents] = useState<any[] | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [epochsets, setEpochsets] = useState<EpochSetSummary[]>([]);
  const [featuresets, setFeaturesets] = useState<FeatureSetSummary[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([]);
  const [listsRev, setListsRev] = useState(0);
  const [results, setResults] = useState<Record<string, unknown>>({});

  // ── NeuroStudio ───────────────────────────────────────────────────────────
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [splits, setSplits] = useState<Split[]>([]);
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
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

  // ── Helpers ───────────────────────────────────────────────────────────────
  function log(level: LogEntry["level"], text: string, detail?: string) {
    logSeq.current += 1;
    const entry: LogEntry = { id: logSeq.current, at: Date.now(), level, text, detail };
    setLogEntries((prev) => [entry, ...prev].slice(0, 300));
  }

  function showError(context: string, e: unknown) {
    const f = describeError(e);
    setNotice({ kind: "error", title: `${context}: ${f.title}`, hint: f.hint, detail: f.detail });
    log("error", `${context} failed — ${f.title}`, f.detail);
  }

  /** Call the backend; a `{status: "error"}` reply is raised as a failure. */
  async function exec<T = any>(command: string, params: Record<string, unknown> = {}): Promise<T> {
    const res = await suiteCall<T>(command, params);
    const fail = backendFailure(res);
    if (fail) throw new Error(fail);
    return res;
  }

  /** Run one user-initiated operation. Only one runs at a time; the backend
   *  serializes calls anyway, so a second click would only queue a duplicate. */
  async function task<T>(label: string, fn: () => Promise<T>, done?: string | ((r: T) => string)): Promise<T | null> {
    if (busyRef.current) {
      setNotice({ kind: "info", title: "Another operation is still running", hint: "Wait for it to finish, then try again." });
      return null;
    }
    busyRef.current = true;
    setBusy({ label, startedAt: Date.now() });
    try {
      const r = await fn();
      const msg = typeof done === "function" ? done(r) : done;
      log("success", msg || `${label} — done`);
      if (msg) setNotice({ kind: "success", title: msg });
      return r;
    } catch (e) {
      showError(label, e);
      return null;
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  }

  function chooseStudy(id: string | null) {
    selectedIdRef.current = id;
    setSelectedId(id);
    writeStored("nt-study", id);
  }

  async function loadManager(studyId: string) {
    setManagerLoading(true);
    try {
      const mgr = await suiteCall<Manager>("studies.manager", { study_id: studyId });
      if (selectedIdRef.current === studyId) setManager(mgr);
      return mgr;
    } finally {
      setManagerLoading(false);
    }
  }

  /** Reload connection, study list, and the selected study. `preferId` wins over current selection. */
  async function refresh(preferId?: string | null) {
    try {
      await waitForSuiteRuntime();
      const health = await suiteCall<{ status: string; version: string }>("health");
      if (connStateRef.current === "offline") log("success", "Reconnected to backend");
      setConn({ state: "online", version: health.version });
      // A connection error is resolved once the backend answers again.
      setNotice((n) => (n?.kind === "error" && n.title.startsWith("Connecting to backend") ? null : n));
      const listed = await suiteCall<{ studies: StudySummary[] }>("studies.list");
      setStudies(listed.studies);
      setStudiesLoaded(true);
      const want = preferId !== undefined ? preferId : (selectedIdRef.current ?? readStored("nt-study"));
      const id =
        want && listed.studies.some((s) => s.id === want) ? want : (listed.studies[0]?.id ?? null);
      if (id !== selectedIdRef.current) chooseStudy(id);
      if (id) await loadManager(id);
      else setManager(null);
      setListsRev((n) => n + 1);
    } catch (e) {
      const f = describeError(e);
      setConn({ state: "offline", detail: f.detail });
      showError("Connecting to backend", e);
    }
  }

  async function refreshManager() {
    const id = selectedIdRef.current;
    if (!id) return;
    try {
      await loadManager(id);
      const listed = await suiteCall<{ studies: StudySummary[] }>("studies.list");
      setStudies(listed.studies);
    } catch (e) {
      showError("Reloading study", e);
    }
    setListsRev((n) => n + 1);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Confirmations fade on their own; errors and warnings stay until dismissed.
  useEffect(() => {
    if (!notice || (notice.kind !== "success" && notice.kind !== "info")) return;
    const t = window.setTimeout(() => setNotice((n) => (n === notice ? null : n)), 6000);
    return () => window.clearTimeout(t);
  }, [notice]);

  // A new screen starts at the top, and a confirmation about one screen doesn't linger on the next.
  useEffect(() => {
    document.getElementById("main")?.scrollTo({ top: 0 });
    setNotice((n) => (n && (n.kind === "success" || n.kind === "info") ? null : n));
  }, [page, flowStage, studioStage]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    writeStored("nt-theme", theme);
  }, [theme]);

  useEffect(() => {
    writeStored("nt-sidebar", sidebarOpen ? "1" : "0");
  }, [sidebarOpen]);

  // ── Derived ───────────────────────────────────────────────────────────────
  const online = conn.state === "online";
  const idle = online && !busy;
  const recRows = useMemo(() => flattenRecordings(manager), [manager]);
  const selectedRow = useMemo(() => findRecording(manager, selectedRecId), [manager, selectedRecId]);
  const selectedRec = selectedRow?.rec ?? null;
  const selectedStudy = studies.find((s) => s.id === selectedId) ?? null;
  const [plotRef, plotWidth] = useElementWidth<HTMLDivElement>(720);
  // Plots draw in pixel units; fit them to the container (minus the track border).
  const plotW = Math.max(480, plotWidth - 2);
  const pendingCount =
    pendingSegments.length + pendingBadChannels.length + pendingUnrejectAnnIds.length + pendingEpochReject.length;

  // Drop a recording selection that no longer exists in the loaded study.
  useEffect(() => {
    if (manager && selectedRecId && !findRecording(manager, selectedRecId)) setSelectedRecId(null);
  }, [manager, selectedRecId]);

  // Everything below is per-recording; never carry it to another recording.
  useEffect(() => {
    setTimeline(null);
    setTlError(null);
    setTlStart(0);
    setIcaData(null);
    setErpData(null);
    setErpChannel("");
    setErpEvent("");
    setEpochSet(null);
    setPendingSegments([]);
    setPendingBadChannels([]);
    setPendingUnrejectAnnIds([]);
    setPendingEpochReject([]);
    setValidation(null);
    setEvents(null);
    setOffsetEdits({});
    setResults({});
  }, [selectedId, selectedRecId]);

  // Per-study selections.
  useEffect(() => {
    setPlans([]);
    setSelectedPlanId("");
    setDatasets([]);
    setSplits([]);
    setExperiments([]);
    setSelDatasetId("");
    setSelSplitId("");
    setSelExperimentId("");
    setBuildEpochsetId("");
    setImportSubject("");
    setExtAttach("");
    setHomeData(null);
  }, [selectedId]);

  useEffect(() => {
    if (selectedRecId && selectedId) {
      let cancelled = false;
      void suiteCall<{ sync_groups: SyncGroup[] }>("sync.list", {
        study_id: selectedId,
        recording_id: selectedRecId,
      })
        .then((r) => !cancelled && setSyncGroups(r.sync_groups))
        .catch(() => !cancelled && setSyncGroups([]));
      return () => {
        cancelled = true;
      };
    }
    setSyncGroups([]);
  }, [selectedRecId, selectedId, manager]);

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

  // Default selections follow the newest item unless the user picked one that still exists.
  const effPlanId = plans.some((p) => p.id === selectedPlanId) ? selectedPlanId : (plans[0]?.id ?? "");
  const effDatasetId = datasets.some((d) => d.id === selDatasetId) ? selDatasetId : (datasets[0]?.id ?? "");
  const datasetSplits = splits.filter((s) => s.dataset_id === effDatasetId);
  const effSplitId = datasetSplits.some((s) => s.id === selSplitId) ? selSplitId : (datasetSplits[0]?.id ?? "");
  const effExperimentId = experiments.some((x) => x.id === selExperimentId)
    ? selExperimentId
    : (experiments[0]?.id ?? "");
  const selExperiment = experiments.find((x) => x.id === effExperimentId) ?? null;
  const recEpochsets = epochsets.filter((e) => e.recording_id === selectedRecId);
  const effBuildEpochsetId = epochsets.some((e) => e.id === buildEpochsetId)
    ? buildEpochsetId
    : (recEpochsets[0]?.id ?? epochsets[0]?.id ?? "");
  const importSubjectEff =
    manager?.subjects.some((s) => s.id === importSubject) || importSubject === NEW_SUBJECT
      ? importSubject
      : (manager?.subjects[0]?.id ?? NEW_SUBJECT);
  const extAttachEff = extAttach || selectedRecId || NEW_RECORDING;

  // Auto-load the signal window for the selected recording.
  useEffect(() => {
    if (page !== "flow" || flowStage !== "inspect" || !selectedId || !selectedRecId || !online) return;
    let cancelled = false;
    setTlBusy(true);
    void suiteCall<Timeline>("recordings.timeline", {
      study_id: selectedId,
      recording_id: selectedRecId,
      start: Math.max(0, tlStart),
      duration: Math.max(0.1, tlDur),
      max_points: 800,
    })
      .then((tl) => {
        if (cancelled) return;
        setTimeline(tl);
        setTlError(null);
      })
      .catch((e) => {
        if (!cancelled) setTlError(describeError(e).detail);
      })
      .finally(() => {
        if (!cancelled) setTlBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page, flowStage, selectedId, selectedRecId, tlStart, tlDur, tlRev, online]);

  // ── Guards ────────────────────────────────────────────────────────────────
  async function confirmDiscardPending(): Promise<boolean> {
    if (!pendingCount) return true;
    const msg = `You have ${pendingCount} unapplied mark${pendingCount === 1 ? "" : "s"} on this recording. Switching will discard ${pendingCount === 1 ? "it" : "them"}. Nothing has been written yet.`;
    try {
      return await ask(msg, {
        title: "Discard unapplied marks?",
        kind: "warning",
        okLabel: "Discard marks",
        cancelLabel: "Keep editing",
      });
    } catch {
      return window.confirm(msg);
    }
  }

  async function selectStudy(id: string) {
    if (!id || id === selectedId) return;
    if (!(await confirmDiscardPending())) return;
    chooseStudy(id);
    setSelectedRecId(null);
    setManager(null);
    try {
      await loadManager(id);
    } catch (e) {
      showError("Opening study", e);
    }
  }

  async function openRecording(id: string, stage: FlowStage = "inspect") {
    if (id !== selectedRecId && !(await confirmDiscardPending())) return;
    setSelectedRecId(id);
    setPage("flow");
    setFlowStage(stage);
  }

  async function changeRecording(id: string) {
    if (id === selectedRecId) return;
    if (!(await confirmDiscardPending())) return;
    setSelectedRecId(id || null);
  }

  // ── Study / subject actions ───────────────────────────────────────────────
  const studyNameCheck = validateStudyName(newStudyName, studies);

  async function createStudy() {
    setNewStudyTouched(true);
    if (!studyNameCheck.ok) return;
    if (!(await confirmDiscardPending())) return;
    const created = await task(
      "Creating study",
      () =>
        exec<StudySummary>("studies.create", {
          name: newStudyName.trim(),
          task_name: newStudyTask.trim() || null,
        }),
      (s) => `Study “${s.name}” created`,
    );
    if (!created) return;
    setNewStudyOpen(false);
    setNewStudyName("");
    setNewStudyTask("");
    setNewStudyTouched(false);
    setSelectedRecId(null);
    chooseStudy(created.id);
    // Stay where the study was created (Home, or the NeuroFlow/NeuroStudio empty state).
    await refresh(created.id);
  }

  const subjectCheck = validateSubjectLabel(subjectLabel, manager?.subjects ?? []);
  const subjectMetaCheck = parseMetadata(subjectMeta);

  async function addSubject() {
    setSubjectTouched(true);
    if (!selectedId || !subjectCheck.ok || !subjectMetaCheck.ok) return;
    const label = subjectLabel.trim();
    const ok = await task(
      "Adding subject",
      () =>
        exec("subjects.add", {
          study_id: selectedId,
          label,
          metadata: subjectMetaCheck.value,
        }),
      `Subject ${label} added`,
    );
    if (!ok) return;
    setSubjectLabel("");
    setSubjectMeta("");
    setSubjectTouched(false);
    await refreshManager();
  }

  // ── Import ────────────────────────────────────────────────────────────────
  async function inspectImport(path: string) {
    const p = path.trim();
    if (!p) return;
    setInspect(null);
    setInspectedPath("");
    setColumns([]);
    setDataKey("");
    setTranspose(false);
    setMontage("");
    const info = await task("Inspecting file", () => exec<InspectInfo>("import.inspect", { path: p }));
    if (!info) return;
    setInspect(info);
    setInspectedPath(p);
    const problem = inspectProblem(info);
    if (problem) {
      setNotice({ kind: "error", ...problem });
      log("error", `Inspecting file failed — ${problem.title}`, problem.detail);
      return;
    }
    setNotice(null);
    log("info", `Inspected ${info.format ?? "file"}: ${info.status === "needs_config" ? "needs settings" : "ready to import"}`);
    if (info.suggested_data_key) setDataKey(info.suggested_data_key);
    setSfreq(typeof info.sfreq === "number" ? String(info.sfreq) : "");
    if (Array.isArray(info.columns)) {
      setColumns(
        info.columns.map((c) => ({ index: Number(c.index), name: String(c.name), role: String(c.role ?? "eeg") })),
      );
    }
  }

  async function browseImport() {
    const selected = await open({
      multiple: false,
      title: "Import EEG recording",
      filters: [{ name: "EEG", extensions: EEG_EXTENSIONS }],
    });
    if (typeof selected !== "string" || !selected) return;
    setImportPath(selected);
    await inspectImport(selected);
  }

  const inspectErr = inspectProblem(inspect);
  const needsConfig = !inspectErr && (inspect?.status === "needs_config" || inspect?.self_describing === false);
  const needs = new Set(inspect?.required_config || []);
  const needsSfreq = needs.has("sfreq") || inspect?.status === "needs_config";
  const needsDataKey = needs.has("data_key");
  const sfreqCheck = needsSfreq ? parsePositive(sfreq, "Sampling rate") : null;
  const importNewLabelCheck =
    importSubjectEff === NEW_SUBJECT ? validateSubjectLabel(importNewLabel, manager?.subjects ?? []) : { ok: true as const };
  const importBlock: string | null = !importPath.trim()
    ? "Choose a file to import."
    : inspectedPath !== importPath.trim() || !inspect
      ? "Inspect the file first so its format and required settings are known."
      : inspectErr
        ? "This file could not be read. Choose a different file."
        : sfreqCheck && !sfreqCheck.ok
          ? "Enter the sampling rate. It cannot be read from this file format."
          : needsDataKey && !dataKey
            ? "Choose which MAT variable holds the EEG data."
            : !importNewLabelCheck.ok
              ? (importNewLabelCheck.error ?? "Enter a subject label.")
              : null;

  async function resolveImportTarget(): Promise<{ subject_id: string; session_id: string; run_id: string; label: string }> {
    if (!selectedId) throw new Error("no study selected");
    if (importSubjectEff === NEW_SUBJECT) {
      const label = importNewLabel.trim();
      const added = await exec<any>("subjects.add", { study_id: selectedId, label });
      log("info", `Created subject ${label}`);
      return { subject_id: added.subject.id, session_id: added.session_id, run_id: added.run_id, label };
    }
    const sub = manager?.subjects.find((s) => s.id === importSubjectEff);
    const ses = sub?.sessions[0];
    const run = ses?.runs[0];
    if (!sub || !ses || !run) {
      throw new Error(`Subject ${sub?.label ?? importSubjectEff} has no session/run to import into.`);
    }
    return { subject_id: sub.id, session_id: ses.id, run_id: run.id, label: sub.label };
  }

  async function importRecording() {
    if (!selectedId || importBlock) return;
    const res = await task(
      "Importing recording",
      async () => {
        const target = await resolveImportTarget();
        const payload: Record<string, unknown> = {
          study_id: selectedId,
          subject_id: target.subject_id,
          session_id: target.session_id,
          run_id: target.run_id,
          path: importPath.trim(),
        };
        if (needsSfreq && sfreqCheck?.ok) payload.sfreq = sfreqCheck.value;
        if (needsDataKey) payload.data_key = dataKey;
        if (transpose) payload.transpose = true;
        if (montage) payload.montage = montage;
        if (columns.length) payload.column_selection = columns;
        return exec<any>("import.recording", payload);
      },
      "Recording imported",
    );
    if (!res) return;
    // Reload first: selecting an id the loaded study doesn't contain yet would be dropped as stale.
    await refreshManager();
    setSelectedRecId(res.recording.id);
    setImportPath("");
    setInspect(null);
    setInspectedPath("");
    setColumns([]);
    setNotice({
      kind: "success",
      title: "Recording imported",
      hint: "Next: open the Inspect step to review the signal.",
    });
  }

  async function browseExternal() {
    const selected = await open({
      multiple: false,
      title: "Import external modality",
      filters: [{ name: "Streams", extensions: STREAM_EXTENSIONS }],
    });
    if (typeof selected !== "string" || !selected) return;
    setExtPath(selected);
    setExtInspect(null);
    const info = await task("Inspecting stream file", () => exec<InspectInfo>("import.stream.inspect", { path: selected }));
    if (!info) return;
    setExtInspect(info);
    if (info.suggested_modality) setExtModality(info.suggested_modality);
    if (typeof info.sfreq === "number") setExtSfreq(String(info.sfreq));
  }

  const extSfreqCheck = parsePositive(extSfreq, "Sampling rate");
  const extBlock: string | null = !extPath.trim()
    ? "Choose a stream file."
    : !extSfreqCheck.ok
      ? "Enter the stream's sampling rate in Hz."
      : extAttachEff === NEW_RECORDING && importSubjectEff === NEW_SUBJECT && !importNewLabelCheck.ok
        ? (importNewLabelCheck.error ?? "Enter a subject label.")
        : null;

  async function importExternalStream() {
    if (!selectedId || extBlock || !extSfreqCheck.ok) return;
    const hz = extSfreqCheck.value;
    const res = await task(
      "Importing stream",
      async () => {
        let target: { subject_id: string; session_id: string; run_id: string };
        let recording_id: string | undefined;
        if (extAttachEff !== NEW_RECORDING) {
          // Attach using the target recording's own subject/session/run.
          const row = findRecording(manager, extAttachEff);
          if (!row) throw new Error("The recording to attach to no longer exists.");
          target = { subject_id: row.subjectId, session_id: row.sessionId, run_id: row.runId };
          recording_id = row.rec.id;
        } else {
          target = await resolveImportTarget();
        }
        const payload: Record<string, unknown> = {
          study_id: selectedId,
          ...target,
          path: extPath.trim(),
          modality: extModality,
          sfreq: hz,
        };
        if (extUnits) payload.units = extUnits;
        if (recording_id) payload.recording_id = recording_id;
        return exec<any>("import.stream", payload);
      },
      (r) => `Imported ${r.stream.modality} stream`,
    );
    if (!res) return;
    await refreshManager();
    setSelectedRecId(res.recording.id);
    setExtPath("");
    setExtInspect(null);
  }

  // ── Sync / validation / events ────────────────────────────────────────────
  async function createSync() {
    if (!selectedId || !selectedRecId) return;
    const res = await task(
      "Creating sync group",
      () =>
        exec<{ sync_group: SyncGroup }>("sync.create", {
          study_id: selectedId,
          recording_id: selectedRecId,
          method: syncMethod,
        }),
      (r) => `Sync group created (${r.sync_group.method})`,
    );
    if (res) await refreshManager();
  }

  async function applyOffset(syncGroupId: string, streamId: string) {
    if (!selectedId) return;
    const raw = offsetEdits[streamId] ?? "0";
    const offset = Number(raw);
    if (!raw.trim() || !Number.isFinite(offset)) {
      setNotice({ kind: "error", title: "Offset must be a number of seconds", detail: `got “${raw}”` });
      return;
    }
    const ok = await task(
      "Setting stream offset",
      () =>
        exec("sync.set_offset", {
          study_id: selectedId,
          sync_group_id: syncGroupId,
          stream_id: streamId,
          offset_sec: offset,
        }),
      `Offset set to ${offset} s`,
    );
    if (ok) await refreshManager();
  }

  async function runValidate(scope: "recording" | "study") {
    if (!selectedId) return;
    if (scope === "recording" && !selectedRecId) return;
    const report = await task(
      scope === "study" ? "Validating study" : "Validating recording",
      () =>
        scope === "study"
          ? exec<ValidationReport>("validate.study", { study_id: selectedId })
          : exec<ValidationReport>("validate.recording", { study_id: selectedId, recording_id: selectedRecId }),
      (r) =>
        `Validation ${r.ok ? "passed" : "found problems"}: ${r.blocking_errors?.length ?? 0} errors, ${r.warnings?.length ?? 0} warnings`,
    );
    if (!report) return;
    setValidation({ scope, report });
    await refreshManager();
  }

  /** Run a study/recording-scoped command, store its result under `key`, then refresh. */
  async function runFlow<T = any>(
    key: string,
    label: string,
    cmd: string,
    params: Record<string, unknown> = {},
    done?: string | ((r: T) => string),
  ): Promise<T | null> {
    if (!selectedId) return null;
    const res = await task(
      label,
      () =>
        exec<T>(cmd, {
          study_id: selectedId,
          ...(selectedRecId ? { recording_id: selectedRecId } : {}),
          ...params,
        }),
      done,
    );
    if (res != null) {
      setResults((r) => ({ ...r, [key]: res }));
      await refreshManager();
    }
    return res;
  }

  async function loadEvents() {
    const r = await runFlow<{ events: any[] }>("events", "Loading events", "events.list");
    if (r) setEvents(r.events ?? []);
  }

  async function addEvent() {
    const t = Number(eventTime);
    if (!eventTime.trim() || !Number.isFinite(t) || t < 0) {
      setNotice({ kind: "error", title: "Event time must be a non-negative number of seconds", detail: `got “${eventTime}”` });
      return;
    }
    const name = eventName.trim() || "manual";
    const r = await runFlow("events", "Adding event", "events.create", { timestamp: t, name, source: "manual" }, `Event “${name}” added at ${t} s`);
    if (r) await loadEvents();
  }

  function nudgeTime(delta: number) {
    setTlStart((s) => Math.max(0, +(s + delta).toFixed(4)));
  }

  // ── Visualizer marks ──────────────────────────────────────────────────────
  function togglePendingBadChannel(channel: string) {
    setPendingBadChannels((prev) => (prev.includes(channel) ? prev.filter((c) => c !== channel) : [...prev, channel]));
  }

  function markPendingSegment(t0: number, t1: number) {
    setPendingSegments((prev) => [...prev, { start: t0, end: t1 }]);
  }

  function channelIsBad(channel: string): boolean {
    const st = timeline?.streams?.find((s) => s.modality === "eeg");
    if (!st) return false;
    const i = st.channels.indexOf(channel);
    if (i < 0) return false;
    return (st.channel_status?.[i] || "") === "bad";
  }

  /** Apply all pending marks. Failed items stay marked so nothing is silently lost. */
  async function applyRejectMarks() {
    if (!selectedId || !selectedRecId) return;
    if (!pendingSegments.length && !pendingBadChannels.length && !pendingUnrejectAnnIds.length) return;
    const base = { study_id: selectedId, recording_id: selectedRecId };
    const total = pendingSegments.length + pendingBadChannels.length + pendingUnrejectAnnIds.length;
    const res = await task(
      "Applying rejections",
      async () => {
        const keepSegs: typeof pendingSegments = [];
        const keepCh: string[] = [];
        const keepUn: string[] = [];
        let firstErr: unknown = null;
        for (const seg of pendingSegments) {
          try {
            await exec("artifacts.apply", {
              ...base,
              suggestion: {
                kind: "bad_segment",
                start: seg.start,
                end: seg.end,
                method: "manual_visualizer",
                reason: "REJECT in visualizer",
                placeholder: false,
              },
            });
          } catch (e) {
            keepSegs.push(seg);
            firstErr ??= e;
          }
        }
        for (const ch of pendingBadChannels) {
          try {
            await exec("channels.update", { ...base, channel_name: ch, bad: !channelIsBad(ch) });
          } catch (e) {
            keepCh.push(ch);
            firstErr ??= e;
          }
        }
        for (const annId of pendingUnrejectAnnIds) {
          try {
            await exec("artifacts.revert", { ...base, annotation_id: annId });
          } catch (e) {
            keepUn.push(annId);
            firstErr ??= e;
          }
        }
        setPendingSegments(keepSegs);
        setPendingBadChannels(keepCh);
        setPendingUnrejectAnnIds(keepUn);
        setTlRev((n) => n + 1);
        const failed = keepSegs.length + keepCh.length + keepUn.length;
        if (failed) {
          throw new Error(
            `${failed} of ${total} changes failed and are still marked; ${total - failed} were applied. First error: ${describeError(firstErr).detail}`,
          );
        }
        return total;
      },
      (n) => `Applied ${n} change${n === 1 ? "" : "s"}. The source recording is unchanged.`,
    );
    void res;
    await refreshManager();
  }

  async function loadIca() {
    if (!selectedId || !selectedRecId) return;
    const res = await task(
      `Fitting ICA (${ICA_COMPONENTS} components)`,
      () =>
        exec<any>("ica.components.list", {
          study_id: selectedId,
          recording_id: selectedRecId,
          n_components: ICA_COMPONENTS,
        }),
      (r) => `ICA ready: ${r.n_components} components`,
    );
    if (res) setIcaData(res);
  }

  async function toggleIcaReject(index: number) {
    if (!selectedId || !selectedRecId || !icaData) return;
    const comp = icaData.components?.find((c: any) => c.index === index);
    const action = comp?.rejected ? "keep" : "reject";
    const res = await task(
      action === "reject" ? `Marking IC${index} for removal` : `Keeping IC${index}`,
      async () => {
        await exec("ica.component.set_rejection", {
          study_id: selectedId,
          recording_id: selectedRecId,
          component_indices: [index],
          action,
        });
        return exec<any>("ica.components.list", {
          study_id: selectedId,
          recording_id: selectedRecId,
          n_components: ICA_COMPONENTS,
        });
      },
    );
    if (res) setIcaData(res);
  }

  async function loadErp() {
    if (!selectedId || !selectedRecId) return;
    const res = await task(
      "Computing ERP",
      () =>
        exec<any>("erp.compute", {
          study_id: selectedId,
          recording_id: selectedRecId,
          event_name: erpEvent || null,
          tmin: EPOCH_WINDOW.tmin,
          tmax: EPOCH_WINDOW.tmax,
          erpimage_channel: erpChannel || null,
        }),
      (r) => (r.status === "ok" ? `ERP computed from ${r.nave ?? 0} epochs` : `ERP: ${r.status}`),
    );
    if (res) setErpData(res);
  }

  async function applyIcaRemovals() {
    if (!selectedId || !selectedRecId) return;
    const res = await task(
      "Applying ICA removals",
      () =>
        exec<any>("ica.apply", {
          study_id: selectedId,
          recording_id: selectedRecId,
          n_components: ICA_COMPONENTS,
          use_as_working: true,
        }),
      (r) => `ICA applied: excluded [${(r.excluded || []).join(", ")}]. A new working FIF was written; the source is unchanged.`,
    );
    if (!res) return;
    setTlRev((n) => n + 1);
    setIcaData(null);
  }

  async function runCleanContinuous() {
    if (!selectedId || !selectedRecId) return;
    const res = await task(
      "Cleaning continuous data",
      () =>
        exec<any>("neuroflow.clean_continuous", {
          study_id: selectedId,
          recording_id: selectedRecId,
          z_thresh: CLEAN_Z_THRESH,
          use_as_working: true,
        }),
      (r) =>
        `Clean continuous: ${r.n_bad_spans} bad spans, ${r.duration_before?.toFixed?.(2)} → ${r.duration_after?.toFixed?.(2)} s${r.warning ? ` (${r.warning})` : ""}`,
    );
    if (res) setTlRev((n) => n + 1);
  }

  async function loadEpochSet(epochsetId?: string) {
    if (!selectedId || !selectedRecId) return;
    const res = await task("Loading epochs", async () => {
      let id = epochsetId;
      if (!id) {
        const listed = await exec<{ epochsets: EpochSetSummary[] }>("epochs.list", {
          study_id: selectedId,
          recording_id: selectedRecId,
        });
        id = newestFirst(listed.epochsets)[0]?.id;
      }
      if (!id) return null;
      return exec<any>("epochs.get", { study_id: selectedId, epochset_id: id });
    });
    setEpochSet(res ?? null);
    setPendingEpochReject([]);
  }

  async function createEpochs() {
    const r = await runFlow<any>(
      "epochs",
      "Creating epochs",
      "epochs.create",
      { tmin: EPOCH_WINDOW.tmin, tmax: EPOCH_WINDOW.tmax, name: "epochs" },
      (r) => `Created ${r.n_trials} epochs`,
    );
    return r;
  }

  function togglePendingEpoch(index: number) {
    setPendingEpochReject((prev) => (prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]));
  }

  async function applyEpochReject() {
    if (!selectedId || !epochSet?.id || !pendingEpochReject.length) return;
    const byIndex = new Map<number, any>((epochSet.trials || []).map((t: any) => [t.index, t]));
    const toReject = pendingEpochReject.filter((i) => !byIndex.get(i)?.rejected);
    const toKeep = pendingEpochReject.filter((i) => byIndex.get(i)?.rejected);
    const ok = await task(
      "Updating epoch rejections",
      async () => {
        if (toReject.length) {
          await exec("epochs.reject", {
            study_id: selectedId,
            epochset_id: epochSet.id,
            trial_indices: toReject,
            rejected: true,
            rewrite_fif: true,
          });
        }
        if (toKeep.length) {
          await exec("epochs.reject", {
            study_id: selectedId,
            epochset_id: epochSet.id,
            trial_indices: toKeep,
            rejected: false,
            rewrite_fif: true,
          });
        }
        return true;
      },
      `Rejected ${toReject.length}, restored ${toKeep.length} epoch${toReject.length + toKeep.length === 1 ? "" : "s"}`,
    );
    // Reload either way: on partial failure the server state is the truth.
    await loadEpochSet(epochSet.id);
    if (!ok) setPendingEpochReject(pendingEpochReject);
  }

  // ── Plans ─────────────────────────────────────────────────────────────────
  async function createDefaultPlan() {
    const r = await runFlow<any>("plan", "Creating default plan", "plans.default", {}, "Default plan created");
    if (r?.plan?.id) setSelectedPlanId(r.plan.id);
  }

  async function executePlan() {
    if (!effPlanId || !selectedRecId) return;
    const plan = plans.find((p) => p.id === effPlanId);
    await runFlow<any>(
      "planRun",
      `Running plan “${plan?.name ?? effPlanId}”`,
      "plans.execute",
      { plan_id: effPlanId },
      (r) => `Plan finished: ${r.artifacts?.length ?? 0} derived artifact${r.artifacts?.length === 1 ? "" : "s"} written`,
    );
  }

  // ── NeuroStudio ───────────────────────────────────────────────────────────
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
      setResults((x) => ({ ...x, dataset: r }));
      setListsRev((n) => n + 1);
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
      setResults((x) => ({ ...x, split: r }));
      setListsRev((n) => n + 1);
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
    if (r) setResults((x) => ({ ...x, recommend: r }));
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
    setResults((x) => ({ ...x, experiment: r }));
    setListsRev((n) => n + 1);
    const warns: string[] = r.leakage_check?.warnings ?? [];
    if (warns.length) {
      setNotice({ kind: "warn", title: "Experiment created with leakage warnings", hint: warns.join(" · ") });
    }
  }

  async function studioRun(key: string, label: string, cmd: string, params: Record<string, unknown>, done?: string | ((r: any) => string)) {
    if (!selectedId) return null;
    const r = await task(label, () => exec<any>(cmd, { study_id: selectedId, ...params }), done);
    if (r) {
      setResults((x) => ({ ...x, [key]: r }));
      setListsRev((n) => n + 1);
    }
    return r;
  }

  // ── Navigation ────────────────────────────────────────────────────────────
  const flowIndex = FLOW_STAGES.findIndex((s) => s.id === flowStage);
  const studioIndex = STUDIO_STAGES.findIndex((s) => s.id === studioStage);
  const flowMeta = FLOW_STAGES[flowIndex] ?? FLOW_STAGES[0];
  const studioMeta = STUDIO_STAGES[studioIndex] ?? STUDIO_STAGES[0];

  function goPage(p: Page) {
    if (p === "flow" && page !== "flow" && selectedRecId && flowStage === "recording") setFlowStage("inspect");
    setPage(p);
  }

  const impGate = importGate(!!selectedId, online);
  const trnGate = trainGate(!!selectedId, online, recRows.length);
  const step = nextStep(manager);
  const trainedExperiments = experiments.filter(isTrained);

  function openImport() {
    setPage("flow");
    setFlowStage("recording");
  }

  function startNewStudy() {
    setNewStudyOpen(true);
    setNewStudyTouched(false);
    setPage("home");
  }

  // ── Render pieces ─────────────────────────────────────────────────────────
  function closeNewStudy() {
    setNewStudyOpen(false);
    setNewStudyName("");
    setNewStudyTask("");
    setNewStudyTouched(false);
  }

  const newStudyForm = (
    <form
      className="form-grid new-study"
      onSubmit={(e) => {
        e.preventDefault();
        void createStudy();
      }}
    >
      <Field
        label="Study name"
        error={newStudyTouched ? studyNameCheck.error : null}
        hint={studyNameCheck.warning ?? "For example: Auditory oddball pilot"}
      >
        <input
          autoFocus
          value={newStudyName}
          onChange={(e) => setNewStudyName(e.target.value)}
          onBlur={() => newStudyName && setNewStudyTouched(true)}
          maxLength={160}
          aria-required="true"
        />
      </Field>
      <Field label="Task or paradigm (optional)" hint="For example: oddball, motor imagery, resting state">
        <input value={newStudyTask} onChange={(e) => setNewStudyTask(e.target.value)} />
      </Field>
      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={!idle || (newStudyTouched && !studyNameCheck.ok)}>
          Create study
        </button>
        {studies.length > 0 && (
          <button type="button" className="btn" onClick={closeNewStudy}>
            Cancel
          </button>
        )}
        {!online && <Reason text="The backend is offline, so studies can’t be created right now." />}
      </div>
    </form>
  );

  const noStudy = (module: "NeuroFlow" | "NeuroStudio") =>
    studies.length === 0 ? (
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
          <button type="button" className="btn btn-primary" onClick={() => setPage("home")}>
            Go to Home
          </button>
        }
      >
        {module} works inside a study. Choose one with the Study selector at the top of the window, or open Home to
        see all studies.
      </EmptyState>
    );

  const recordingPicker = (
    <div className="picker">
      <Field label="Recording">
        <select value={selectedRecId ?? ""} onChange={(e) => void changeRecording(e.target.value)} disabled={!recRows.length}>
          <option value="">{recRows.length ? "Choose a recording…" : "No recordings in this study"}</option>
          {recRows.map((r) => (
            <option key={r.rec.id} value={r.rec.id}>
              {recordingLabel(r)}
            </option>
          ))}
        </select>
      </Field>
      {selectedRec && (
        <dl className="facts">
          <div>
            <dt>Format</dt>
            <dd>{selectedRec.source_format ?? "—"}</dd>
          </div>
          <div>
            <dt>Rate</dt>
            <dd className="num">{selectedRec.sampling_rate ? `${selectedRec.sampling_rate} Hz` : "—"}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd className="num">{formatDuration(selectedRec.duration)}</dd>
          </div>
          <div>
            <dt>Streams</dt>
            <dd className="num">{selectedRec.streams.length}</dd>
          </div>
          <div>
            <dt>Validation</dt>
            <dd>
              <ValidationBadge ok={selectedRec.validation_ok} errors={selectedRec.validation_errors} warnings={selectedRec.validation_warnings} />
            </dd>
          </div>
        </dl>
      )}
    </div>
  );

  const needRecording = (what: string) => (
    <EmptyState
      title={recRows.length ? "Choose a recording" : "No recordings yet"}
      actions={
        recRows.length ? null : (
          <button type="button" className="btn btn-primary" onClick={() => setFlowStage("recording")}>
            Import a recording
          </button>
        )
      }
    >
      {recRows.length
        ? `${what} works on one recording at a time. Select it in the Recording field above.`
        : `${what} needs a recording. Import EEG into this study first.`}
    </EmptyState>
  );

  // ── HOME ──────────────────────────────────────────────────────────────────
  const validatedCount = recRows.filter((r) => r.rec.validation_ok != null).length;
  // Sync only matters for multi-stream recordings; skip an all-"—" column otherwise.
  const showSyncCol = recRows.some((r) => r.rec.streams.length > 1 || r.rec.sync_group_ids.length > 0);
  const homeTrained = homeData ? homeData.experiments.filter(isTrained).length : null;
  const activity = homeData ? recentActivity(homeData) : [];
  const pipeline: Array<{ module: "home" | "flow" | "studio"; name: string; stats: Array<{ label: string; value: number | null; of?: number }> }> =
    manager
      ? [
          {
            module: "home",
            name: "Study",
            stats: [
              { label: "Subjects", value: manager.totals.subjects },
              { label: "Recordings", value: recRows.length },
            ],
          },
          {
            module: "flow",
            name: "NeuroFlow",
            stats: [
              { label: "Validated", value: validatedCount, of: recRows.length },
              { label: "Epoch sets", value: homeData ? homeData.epochsets.length : null },
            ],
          },
          {
            module: "studio",
            name: "NeuroStudio",
            stats: [
              { label: "Datasets", value: homeData ? homeData.datasets.length : null },
              { label: "Experiments", value: homeData ? homeData.experiments.length : null },
              { label: "Trained", value: homeTrained },
            ],
          },
        ]
      : [];

  const welcome = (
    <section className="welcome" aria-labelledby="welcome-title">
      <div className="welcome-main">
        <span className="eyebrow">Getting started</span>
        <h1 id="welcome-title">Create your first study</h1>
        <p className="welcome-lead">
          A study holds one experiment: its subjects, their EEG recordings, and everything derived from them. Nothing
          leaves this computer, and imported source files are never modified.
        </p>
        {newStudyForm}
      </div>
      <ol className="welcome-steps" aria-label="How the suite fits together">
        <li className="mod-home">
          <span className="welcome-icon">
            <Icon name="home" size={18} />
          </span>
          <div>
            <strong>Home — organize</strong>
            <span>Create studies and subjects. Track what has been recorded, processed, and modeled.</span>
          </div>
        </li>
        <li className="mod-flow">
          <span className="welcome-icon">
            <Icon name="flow" size={18} />
          </span>
          <div>
            <strong>NeuroFlow — process each recording</strong>
            <span>Import EEG, inspect channels, reject artifacts, run a preprocessing plan, and cut epochs around events.</span>
          </div>
        </li>
        <li className="mod-studio">
          <span className="welcome-icon">
            <Icon name="studio" size={18} />
          </span>
          <div>
            <strong>NeuroStudio — model across the study</strong>
            <span>Turn epochs into datasets, split them without leakage, train and evaluate models, export results.</span>
          </div>
        </li>
      </ol>
    </section>
  );

  const homePage = (
    <>
      {!studiesLoaded && conn.state !== "offline" && <p className="loading">Loading studies…</p>}
      {conn.state === "offline" && !studiesLoaded && (
        <EmptyState
          icon="alert"
          title="Can’t reach the analysis backend"
          actions={
            <button type="button" className="btn btn-primary" onClick={() => void refresh()}>
              Retry connection
            </button>
          }
        >
          Studies are stored by the backend, so they can’t be listed until it is running. The message above has the
          technical details.
        </EmptyState>
      )}

      {studiesLoaded && studies.length === 0 && welcome}

      {studies.length > 0 && (
        <div className="home-grid">
          <aside className="card study-list" aria-label="Studies">
            <header className="card-head">
              <h2 className="card-title">
                Studies <span className="count">{studies.length}</span>
              </h2>
              {!newStudyOpen && (
                <button type="button" className="btn btn-sm btn-primary" onClick={startNewStudy} disabled={!online}>
                  <Icon name="plus" size={14} /> New study
                </button>
              )}
            </header>
            {newStudyOpen && <div className="study-list-form">{newStudyForm}</div>}
            <ul>
              {studies.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    className={`study-item ${s.id === selectedId ? "active" : ""}`}
                    onClick={() => void selectStudy(s.id)}
                    aria-current={s.id === selectedId ? "true" : undefined}
                  >
                    <span className="study-name">{s.name}</span>
                    <span className="study-meta">
                      {s.task_name ? `${s.task_name} · ` : ""}
                      {s.subjects.length} subject{s.subjects.length === 1 ? "" : "s"}
                      {s.created_at ? ` · ${new Date(s.created_at).toLocaleDateString()}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <div className="home-main">
            {!manager ? (
              <p className="loading">{managerLoading ? "Loading study…" : "Select a study."}</p>
            ) : (
              <>
                <section className="study-head" aria-label="Active study">
                  <div className="study-head-text">
                    <span className="eyebrow">Active study</span>
                    <h1 className="study-title">{manager.name}</h1>
                    <p className="study-sub">
                      {manager.task_name && <span>{manager.task_name}</span>}
                      <span className="mono" title="Study ID">
                        {manager.study_id}
                      </span>
                      {selectedStudy?.created_at && <span>Created {fmtDate(selectedStudy.created_at)}</span>}
                    </p>
                  </div>
                  <div className="head-actions">
                    <button type="button" className="btn btn-primary" disabled={!impGate.ok || !!busy} onClick={openImport}>
                      Import recording
                    </button>
                    <button
                      type="button"
                      className="btn"
                      disabled={!trnGate.ok}
                      onClick={() => {
                        setPage("studio");
                        setStudioStage("data");
                      }}
                      title={trnGate.ok ? "Open NeuroStudio to build datasets and train models" : trnGate.reason}
                    >
                      Train a model
                    </button>
                  </div>
                </section>
                {!trnGate.ok && <Reason text={`Train a model: ${trnGate.reason}`} />}

                <div className="next-step" role="note">
                  <div>
                    <span className="next-label">Next step</span>
                    <strong>{step.title}</strong>
                    <span className="next-detail">{step.detail}</span>
                  </div>
                  {step.action === "import" && (
                    <button type="button" className="btn btn-primary" onClick={openImport} disabled={!impGate.ok}>
                      Import recording
                    </button>
                  )}
                  {step.action === "inspect" && recRows[0] && (
                    <button
                      type="button"
                      className="btn"
                      onClick={() => {
                        const target = recRows.find((r) => r.rec.validation_ok == null) ?? recRows[0];
                        void openRecording(target.rec.id, "inspect");
                      }}
                    >
                      Open in NeuroFlow
                    </button>
                  )}
                </div>

                <section className="pipeline" aria-label="Study progress">
                  {pipeline.map((seg) => (
                    <div key={seg.module} className={`pipeline-seg mod-${seg.module}`}>
                      <span className="pipeline-name">{seg.name}</span>
                      <dl>
                        {seg.stats.map((st) => (
                          <div key={st.label}>
                            <dt>{st.label}</dt>
                            <dd className="num">
                              {st.value == null ? "—" : st.value}
                              {st.of != null && <span className="of">/{st.of}</span>}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  ))}
                </section>

                <Card
                  title={
                    <>
                      Recordings <span className="count">{recRows.length}</span>
                    </>
                  }
                  description={recRows.length ? "Select a row to open the recording in NeuroFlow." : undefined}
                >
                  {recRows.length === 0 ? (
                    <EmptyState
                      title="No recordings in this study yet"
                      actions={
                        <button type="button" className="btn btn-primary" onClick={openImport} disabled={!impGate.ok}>
                          Import recording
                        </button>
                      }
                    >
                      Supported: FIF, EDF, BDF, GDF, EEGLAB .set, BrainVision, CNT, MAT, and delimited text. If a format
                      doesn’t store its sampling rate you’ll be asked for it — the app never guesses.
                    </EmptyState>
                  ) : (
                    <div className="table-wrap">
                      <table className="table table-click">
                        <thead>
                          <tr>
                            <th scope="col">Subject</th>
                            <th scope="col">Session / run</th>
                            <th scope="col">Data</th>
                            <th scope="col" className="r">
                              Rate
                            </th>
                            <th scope="col" className="r">
                              Duration
                            </th>
                            <th scope="col">Validation</th>
                            {showSyncCol && <th scope="col">Sync</th>}
                          </tr>
                        </thead>
                        <tbody>
                          {recRows.map((r) => (
                            <tr
                              key={r.rec.id}
                              className={r.rec.id === selectedRecId ? "selected" : ""}
                              onClick={() => void openRecording(r.rec.id)}
                              tabIndex={0}
                              aria-label={`Open ${recordingLabel(r)} in NeuroFlow`}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  void openRecording(r.rec.id);
                                }
                              }}
                              title={r.rec.id}
                            >
                              <td className="strong">{r.subjectLabel}</td>
                              <td className="nowrap">
                                {r.sessionName} / {r.runName}
                              </td>
                              <td className="nowrap">
                                {r.rec.modalities.join(" + ") || "—"}
                                {r.rec.source_format && <span className="muted"> · {r.rec.source_format}</span>}
                              </td>
                              <td className="r num nowrap">{r.rec.sampling_rate ? `${r.rec.sampling_rate} Hz` : "—"}</td>
                              <td className="r num nowrap">{formatDuration(r.rec.duration)}</td>
                              <td>
                                <ValidationBadge ok={r.rec.validation_ok} errors={r.rec.validation_errors} warnings={r.rec.validation_warnings} />
                              </td>
                              {showSyncCol && <td className="nowrap">
                                {r.rec.sync_group_ids.length ? (
                                  <span className="num">conf {(r.rec.sync_confidence ?? 0).toFixed(2)}</span>
                                ) : r.rec.streams.length > 1 ? (
                                  <Badge tone="warn">not aligned</Badge>
                                ) : (
                                  <span className="muted">—</span>
                                )}
                              </td>}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>

                <div className="home-cols">
                  <Card
                    title={
                      <>
                        Subjects <span className="count">{manager.subjects.length}</span>
                      </>
                    }
                    description="Each subject starts with one session and one run."
                  >
                    {manager.subjects.length > 0 && (
                      <div className="table-wrap">
                        <table className="table">
                          <thead>
                            <tr>
                              <th scope="col">Label</th>
                              <th scope="col" className="r">
                                Recordings
                              </th>
                              <th scope="col">Metadata</th>
                            </tr>
                          </thead>
                          <tbody>
                            {manager.subjects.map((s) => (
                              <tr key={s.id}>
                                <td className="strong">{s.label}</td>
                                <td className="r num">
                                  {s.sessions.reduce((n, ses) => n + ses.runs.reduce((m, run) => m + run.recordings.length, 0), 0)}
                                </td>
                                <td className="muted">{Object.keys(s.metadata || {}).join(", ") || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    <form
                      className="form-grid compact"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void addSubject();
                      }}
                    >
                      <Field label="New subject label" error={subjectTouched && subjectLabel ? subjectCheck.error : null}>
                        <input value={subjectLabel} onChange={(e) => setSubjectLabel(e.target.value)} placeholder="e.g. S002" />
                      </Field>
                      <Field label="Metadata (JSON, optional)" error={subjectMetaCheck.ok ? null : subjectMetaCheck.error}>
                        <input
                          value={subjectMeta}
                          onChange={(e) => setSubjectMeta(e.target.value)}
                          placeholder='{"age": 24}'
                          className="mono"
                        />
                      </Field>
                      <div className="form-actions">
                        <button
                          type="submit"
                          className="btn"
                          disabled={!idle || !subjectLabel.trim() || !subjectCheck.ok || !subjectMetaCheck.ok}
                        >
                          Add subject
                        </button>
                      </div>
                    </form>
                  </Card>

                  <Card title="Recent activity" description="Most recent items saved in this study.">
                    {homeData == null ? (
                      <p className="help">Loading…</p>
                    ) : activity.length === 0 ? (
                      <p className="help">Nothing processed yet. Epoch sets, datasets, plans, and experiments appear here once created.</p>
                    ) : (
                      <ol className="timeline">
                        {activity.map((a, i) => (
                          <li key={`${a.kind}-${a.label}-${i}`}>
                            <span className="timeline-kind">{a.kind}</span>
                            <span className="timeline-label">
                              <span className={a.kind === "Experiment" ? "mono" : ""}>{a.kind === "Experiment" ? shortId(a.label, 14) : a.label}</span>
                              {a.detail && <span className="muted"> · {a.detail}</span>}
                            </span>
                            <time className="timeline-time" dateTime={a.at}>
                              {fmtDate(a.at)}
                            </time>
                          </li>
                        ))}
                      </ol>
                    )}
                  </Card>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );

  // ── NEUROFLOW: Import ─────────────────────────────────────────────────────
  const subjectSelect = (
    <>
      <Field label="Subject" hint="Recordings are filed under the subject’s first session and run.">
        <select value={importSubjectEff} onChange={(e) => setImportSubject(e.target.value)}>
          {manager?.subjects.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
          <option value={NEW_SUBJECT}>New subject…</option>
        </select>
      </Field>
      {importSubjectEff === NEW_SUBJECT && (
        <Field label="New subject label" error={importNewLabelCheck.ok ? null : importNewLabelCheck.error}>
          <input value={importNewLabel} onChange={(e) => setImportNewLabel(e.target.value)} />
        </Field>
      )}
    </>
  );

  const flowImport = (
    <>
      <Card
        title="Import EEG recording"
        description="Choose a file, review what was detected, provide any settings the format can’t supply, then import."
      >
        <div className="form-row">
          <Field label="File" wide>
            <div className="input-group">
              <input
                value={importPath}
                onChange={(e) => setImportPath(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void inspectImport(importPath);
                }}
                placeholder="/path/to/recording.fif"
                className="mono"
              />
              <button type="button" className="btn" onClick={() => void browseImport()} disabled={!idle}>
                Browse…
              </button>
              {importPath.trim() && inspectedPath !== importPath.trim() && (
                <button type="button" className="btn" onClick={() => void inspectImport(importPath)} disabled={!idle}>
                  Inspect
                </button>
              )}
            </div>
          </Field>
        </div>
        <p className="help">Supported: {EEG_EXTENSIONS.map((e) => `.${e}`).join(" ")}</p>

        {inspect && inspectedPath === importPath.trim() && (
          <div className="detected">
            <div className="detected-head">
              <span>Detected</span>
              <strong>{inspect.format ?? "unknown format"}</strong>
              {inspectErr ? (
                <Badge tone="danger">unreadable</Badge>
              ) : needsConfig ? (
                <Badge tone="warn">needs settings</Badge>
              ) : (
                <Badge tone="ok">ready</Badge>
              )}
              {typeof inspect.sfreq === "number" && <span className="num">{inspect.sfreq} Hz</span>}
            </div>
            {!!inspect.warnings?.length && (
              <ul className="issues warn">
                {inspect.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
            {needsConfig && (
              <div className="form-row">
                {needsSfreq && (
                  <Field
                    label="Sampling rate (Hz)"
                    error={sfreq && sfreqCheck && !sfreqCheck.ok ? sfreqCheck.error : null}
                    hint="Required: this format doesn’t record it."
                  >
                    <input value={sfreq} onChange={(e) => setSfreq(e.target.value)} inputMode="decimal" placeholder="e.g. 250" />
                  </Field>
                )}
                {(inspect.format === "mat" || needsDataKey) && (
                  <Field label="MAT variable" hint="The array that holds the EEG samples.">
                    <select value={dataKey} onChange={(e) => setDataKey(e.target.value)}>
                      <option value="">Choose…</option>
                      {(inspect.candidates || []).map((c) => (
                        <option key={c.key} value={c.key}>
                          {c.key} {JSON.stringify(c.shape)}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                <Field label="Montage (optional)" hint="e.g. standard_1020">
                  <input value={montage} onChange={(e) => setMontage(e.target.value)} />
                </Field>
                <label className="check">
                  <input type="checkbox" checked={transpose} onChange={(e) => setTranspose(e.target.checked)} />
                  Transpose (data is samples × channels)
                </label>
              </div>
            )}
            {columns.length > 0 && (
              <details className="raw" open>
                <summary>Columns ({columns.length}) — set each column’s role</summary>
                <div className="table-wrap tall">
                  <table className="table">
                    <thead>
                      <tr>
                        <th className="r">#</th>
                        <th>Label</th>
                        <th>Role</th>
                      </tr>
                    </thead>
                    <tbody>
                      {columns.map((col, i) => (
                        <tr key={col.index}>
                          <td className="r num">{col.index + 1}</td>
                          <td>
                            <input
                              value={col.name}
                              onChange={(e) => {
                                const name = e.target.value;
                                setColumns((cols) => cols.map((c, j) => (j === i ? { ...c, name } : c)));
                              }}
                            />
                          </td>
                          <td>
                            <select
                              value={col.role}
                              onChange={(e) => {
                                const role = e.target.value;
                                setColumns((cols) => cols.map((c, j) => (j === i ? { ...c, role } : c)));
                              }}
                            >
                              <option value="eeg">EEG</option>
                              <option value="misc">misc</option>
                              <option value="stim">stim</option>
                              <option value="time">time</option>
                              <option value="ignore">ignore</option>
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
            {!inspectErr && <div className="form-row">{subjectSelect}</div>}
          </div>
        )}

        <div className="form-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void importRecording()}
            disabled={!idle || !!importBlock}
          >
            Import recording
          </button>
          <Reason text={importBlock} />
        </div>
      </Card>

      <Card
        title="Attach another modality"
        description="Import a non-EEG stream (motion, ECG, eye tracking, …) into an existing recording or as a new one. Streams are not assumed to be time-aligned — set up synchronization in the Preprocess step."
      >
        <div className="form-row">
          <Field label="File" wide>
            <div className="input-group">
              <input value={extPath} onChange={(e) => setExtPath(e.target.value)} placeholder="/path/to/stream.csv" className="mono" />
              <button type="button" className="btn" onClick={() => void browseExternal()} disabled={!idle}>
                Browse…
              </button>
            </div>
          </Field>
        </div>
        {extInspect && (
          <p className="help">
            Detected {extInspect.format ?? "file"}
            {extInspect.suggested_modality ? ` · suggested modality: ${extInspect.suggested_modality}` : ""}
          </p>
        )}
        <div className="form-row">
          <Field label="Modality">
            <select value={extModality} onChange={(e) => setExtModality(e.target.value)}>
              {STREAM_MODALITIES.map((m) => (
                <option key={m} value={m}>
                  {m.replace("_", " ")}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Sampling rate (Hz)" error={extSfreq && !extSfreqCheck.ok ? extSfreqCheck.error : null}>
            <input value={extSfreq} onChange={(e) => setExtSfreq(e.target.value)} inputMode="decimal" placeholder="e.g. 100" />
          </Field>
          <Field label="Units (optional)">
            <input value={extUnits} onChange={(e) => setExtUnits(e.target.value)} placeholder="e.g. deg/s" />
          </Field>
          <Field label="Attach to">
            <select value={extAttachEff} onChange={(e) => setExtAttach(e.target.value)}>
              <option value={NEW_RECORDING}>New recording</option>
              {recRows.map((r) => (
                <option key={r.rec.id} value={r.rec.id}>
                  {recordingLabel(r)}
                </option>
              ))}
            </select>
          </Field>
          {extAttachEff === NEW_RECORDING && subjectSelect}
        </div>
        <div className="form-actions">
          <button type="button" className="btn btn-primary" onClick={() => void importExternalStream()} disabled={!idle || !!extBlock}>
            Import stream
          </button>
          <Reason text={extBlock} />
        </div>
      </Card>
    </>
  );

  // ── NEUROFLOW: Inspect ────────────────────────────────────────────────────
  const marksPending = pendingSegments.length + pendingBadChannels.length + pendingUnrejectAnnIds.length;
  const flowInspect = !selectedRecId ? (
    needRecording("Inspection")
  ) : (
    <div className="inspect">
      <div className="tabs" role="tablist" aria-label="Plot views">
        {(
          [
            ["signal", "Channels"],
            ["ica", "ICA"],
            ["erp", "ERP"],
            ["epochs", "Epochs"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={vizMode === id}
            tabIndex={vizMode === id ? 0 : -1}
            onKeyDown={(e) => {
              if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
              const order: VizMode[] = ["signal", "ica", "erp", "epochs"];
              const next = order[(order.indexOf(id) + (e.key === "ArrowRight" ? 1 : order.length - 1)) % order.length];
              setVizMode(next);
              (e.currentTarget.parentElement?.querySelector(`[data-tab="${next}"]`) as HTMLElement | null)?.focus();
            }}
            data-tab={id}
            className={`tab ${vizMode === id ? "active" : ""}`}
            onClick={() => {
              setVizMode(id);
              if (id === "epochs" && !epochSet) void loadEpochSet();
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {vizMode === "signal" && (
        <>
          <div className="toolbar">
            <div className="tool-group" aria-label="Time navigation">
              <button type="button" className="btn btn-sm" onClick={() => nudgeTime(-tlDur)} title="Back one window">
                «
              </button>
              <button type="button" className="btn btn-sm" onClick={() => nudgeTime(-tlDur / 4)} title="Back ¼ window">
                ‹
              </button>
              <label className="inline">
                Start
                <input
                  className="num w-num"
                  type="number"
                  step="0.1"
                  min={0}
                  value={tlStart}
                  onChange={(e) => setTlStart(Math.max(0, Number(e.target.value) || 0))}
                />
                s
              </label>
              <button type="button" className="btn btn-sm" onClick={() => nudgeTime(tlDur / 4)} title="Forward ¼ window">
                ›
              </button>
              <button type="button" className="btn btn-sm" onClick={() => nudgeTime(tlDur)} title="Forward one window">
                »
              </button>
              <span className="plot-status" aria-live="polite">
                {tlBusy ? "Loading…" : timeline ? `${timeline.start.toFixed(2)}–${(timeline.start + timeline.duration).toFixed(2)} s` : ""}
              </span>
            </div>
            <div className="tool-group">
              <label className="inline">
                Window
                <input
                  className="num w-num"
                  type="number"
                  step="0.5"
                  min={0.5}
                  value={tlDur}
                  onChange={(e) => setTlDur(Math.max(0.5, Number(e.target.value) || 4))}
                />
                s
              </label>
              <label className="inline">
                Gain
                <button type="button" className="btn btn-sm" onClick={() => setTlGain((s) => Math.max(0.25, s / 2))} aria-label="Decrease gain">
                  −
                </button>
                <input
                  className="num w-num"
                  type="number"
                  step="0.25"
                  min={0.25}
                  value={tlGain}
                  onChange={(e) => setTlGain(Math.max(0.25, Number(e.target.value) || 1))}
                />
                <button type="button" className="btn btn-sm" onClick={() => setTlGain((s) => s * 2)} aria-label="Increase gain">
                  +
                </button>
              </label>
            </div>
            <div className="tool-group tool-end">
              <button
                type="button"
                className="btn"
                disabled={!idle}
                onClick={() =>
                  void runFlow("montage", "Applying 10–20 montage", "channels.apply_montage", { montage: "standard_1020" }, "Montage standard_1020 applied")
                }
              >
                Apply 10–20 montage
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => void runCleanContinuous()}
                disabled={!idle}
                title={`Drops windows whose amplitude z-score exceeds ${CLEAN_Z_THRESH}; writes a new working FIF (not ASR). Source is unchanged.`}
              >
                Clean continuous (z &gt; {CLEAN_Z_THRESH})
              </button>
            </div>
          </div>

          <div className={`marks ${marksPending ? "has-marks" : ""}`}>
            <span className="marks-help">
              <strong>Drag</strong> to mark a bad segment · <strong>click a channel</strong> to toggle bad/good ·{" "}
              <strong>click a red band</strong> to un-reject. Nothing is saved until you apply.
            </span>
            <span className="marks-count num">
              {marksPending
                ? `${pendingSegments.length} segment${pendingSegments.length === 1 ? "" : "s"}, ${pendingBadChannels.length} channel${pendingBadChannels.length === 1 ? "" : "s"}, ${pendingUnrejectAnnIds.length} un-reject`
                : "No pending marks"}
            </span>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setPendingSegments([]);
                setPendingBadChannels([]);
                setPendingUnrejectAnnIds([]);
              }}
              disabled={!marksPending}
            >
              Clear
            </button>
            <button type="button" className="btn btn-danger" onClick={() => void applyRejectMarks()} disabled={!idle || !marksPending}>
              Apply {marksPending || ""} mark{marksPending === 1 ? "" : "s"}
            </button>
          </div>

          {tlError && (
            <div className="inline-error">
              Couldn’t load the signal window. <span className="mono">{tlError}</span>{" "}
              <button type="button" className="btn-link" onClick={() => setTlRev((n) => n + 1)}>
                Retry
              </button>
            </div>
          )}
          <div className="plot-scroll" ref={plotRef}>
            {timeline &&
              [...timeline.streams]
                .sort((a, b) => {
                  if (a.modality === "eeg") return -1;
                  if (b.modality === "eeg") return 1;
                  return 0;
                })
                .map((st) => {
                  const tl = timeline;
                  const status = (st.channel_status || st.channels.map(() => "unknown")).map((s, i) => {
                    if (!pendingBadChannels.includes(st.channels[i])) return s;
                    // pending click flips current status (bad↔good)
                    return s === "bad" ? "good" : "bad";
                  });
                  const evs = [
                    ...(st.modality === "eeg" ? tl.events : tl.events.filter((e) => e.modality === st.modality)),
                    ...pendingSegments.map((p, i) => ({
                      name: "mark",
                      timestamp: p.start,
                      end: p.end,
                      kind: "annotation",
                      artifact: true,
                      id: `pending-${i}`,
                    })),
                  ];
                  return (
                    <div key={st.stream_id} className="track">
                      <div className="track-head">
                        <strong>{st.modality.toUpperCase()}</strong>
                        <span>{st.channels.length} ch</span>
                        <span className="num">offset {st.offset_sec.toFixed(3)} s</span>
                        {st.error && <span className="track-err">{st.error}</span>}
                      </div>
                      {!st.error && st.data.length > 0 ? (
                        <StackedStreamPlot
                          times={st.times}
                          data={st.data}
                          channels={st.channels}
                          channelStatus={status}
                          events={evs}
                          start={tl.start}
                          duration={tl.duration}
                          gain={tlGain}
                          width={plotW}
                          rowH={st.modality === "eeg" ? 16 : 20}
                          onChannelClick={st.modality === "eeg" ? togglePendingBadChannel : undefined}
                          onRegionSelect={st.modality === "eeg" ? markPendingSegment : undefined}
                          onArtifactClick={
                            st.modality === "eeg"
                              ? (id) =>
                                  setPendingUnrejectAnnIds((prev) =>
                                    prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
                                  )
                              : undefined
                          }
                          pendingUnrejectIds={pendingUnrejectAnnIds}
                        />
                      ) : (
                        <div className="track-empty">No samples in this window.</div>
                      )}
                    </div>
                  );
                })}
          </div>
        </>
      )}

      {vizMode === "ica" && (
        <>
          <div className="toolbar">
            <button type="button" className="btn btn-primary" onClick={() => void loadIca()} disabled={!idle}>
              {icaData ? "Refit ICA" : `Fit ICA (${ICA_COMPONENTS} components)`}
            </button>
            <button type="button" className="btn btn-danger" onClick={() => void applyIcaRemovals()} disabled={!idle || !icaData}>
              Apply removals → new working FIF
            </button>
            <span className="help">FastICA. Click a component to mark it for removal; applying writes a new file and leaves the source untouched.</span>
          </div>
          {icaData?.components?.length ? (
            <div className="plot-scroll" ref={plotRef}>
              <div className="track">
                <div className="track-head">
                  <strong>ICA sources</strong>
                  <span>{icaData.n_components} components</span>
                  <span>{icaData.components.filter((c: any) => c.rejected).length} marked for removal</span>
                </div>
                <StackedStreamPlot
                  times={icaData.components[0].timeseries_times || []}
                  data={icaData.components.map((c: any) => c.timeseries_preview || [])}
                  channels={icaData.components.map((c: any) => (c.rejected ? `IC${c.index}×` : `IC${c.index}`))}
                  channelStatus={icaData.components.map((c: any) => (c.rejected ? "bad" : "good"))}
                  events={[]}
                  start={0}
                  duration={(icaData.components[0].timeseries_times || []).slice(-1)[0] || 1}
                  gain={tlGain}
                  width={plotW}
                  rowH={18}
                  onChannelClick={(label) => {
                    const m = /IC(\d+)/.exec(label);
                    if (m && idle) void toggleIcaReject(Number(m[1]));
                  }}
                />
              </div>
              <div className="ica-grid">
                {icaData.components.slice(0, 8).map((c: any) => {
                  const max = Math.max(...(c.spectrum_power || [0]), 1e-12);
                  const pts = (c.spectrum_power || [])
                    .map((p: number, i: number) => {
                      const x = 4 + (i / Math.max(1, c.spectrum_power.length - 1)) * 100;
                      const y = 36 - (p / max) * 32;
                      return `${x},${y}`;
                    })
                    .join(" ");
                  return (
                    <button
                      key={c.index}
                      type="button"
                      className={`ica-card ${c.rejected ? "rejected" : ""}`}
                      onClick={() => void toggleIcaReject(c.index)}
                      disabled={!idle}
                      aria-pressed={!!c.rejected}
                    >
                      <span className="ica-name">
                        IC{c.index} {c.rejected && <Badge tone="danger">remove</Badge>}
                      </span>
                      <svg width={110} height={40} className="spark" aria-hidden>
                        <polyline fill="none" stroke={c.rejected ? "var(--flagged)" : "var(--trace)"} strokeWidth={1} points={pts} />
                      </svg>
                      <span className="ica-sub">spectrum preview</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <EmptyState title="ICA not computed for this view">
              Fitting decomposes the current working signal into {ICA_COMPONENTS} independent components. It can take a
              while on long recordings.
            </EmptyState>
          )}
        </>
      )}

      {vizMode === "erp" && (
        <>
          <div className="toolbar">
            <Field label="Event">
              <input value={erpEvent} onChange={(e) => setErpEvent(e.target.value)} placeholder="All events" />
            </Field>
            {erpData?.channels?.length ? (
              <Field label="Channel">
                <select value={erpChannel} onChange={(e) => setErpChannel(e.target.value)}>
                  <option value="">All (butterfly)</option>
                  {erpData.channels.map((c: string) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </Field>
            ) : null}
            <button type="button" className="btn btn-primary" onClick={() => void loadErp()} disabled={!idle}>
              {erpData ? "Recompute ERP" : "Compute ERP"}
            </button>
            <span className="help">
              Window {EPOCH_WINDOW.tmin * 1000} to {EPOCH_WINDOW.tmax * 1000} ms around each event.
              {erpData?.status === "ok" ? ` Averaged over ${erpData.nave} epochs.` : ""}
            </span>
          </div>
          {erpData?.status === "ok" && erpData.data?.length ? (
            <div className="plot-area" ref={plotRef}>
              <div className="track">
                <div className="track-head">
                  <strong>{erpChannel ? `ERP at ${erpChannel}` : "Channel ERPs (butterfly)"}</strong>
                  <span>{erpData.channels.length} ch</span>
                </div>
                <ErpButterflyPlot
                  times={erpData.times}
                  data={erpData.data}
                  channels={erpData.channels}
                  highlight={erpChannel || undefined}
                  width={plotW}
                  height={260}
                />
              </div>
              {erpData.erpimage?.trials?.length ? (
                <div className="track">
                  <div className="track-head">
                    <strong>ERP image</strong>
                    <span>{erpData.erpimage.channel}</span>
                    <span>{erpData.erpimage.n_trials} trials</span>
                  </div>
                  <ErpImagePlot
                    times={erpData.erpimage.times}
                    trials={erpData.erpimage.trials}
                    vmin={erpData.erpimage.vmin}
                    vmax={erpData.erpimage.vmax}
                    width={plotW}
                    height={220}
                  />
                </div>
              ) : null}
            </div>
          ) : erpData?.status === "no_events" ? (
            <EmptyState title="No events in this recording">
              ERPs need event markers. Import a format that stores events (e.g. EEGLAB .set), or add events in the
              Preprocess step.
            </EmptyState>
          ) : erpData ? (
            <EmptyState title={`ERP not available (${erpData.status ?? "unknown status"})`}>
              <RawResult value={erpData} />
            </EmptyState>
          ) : (
            <EmptyState title="ERP not computed yet">Choose an event (or leave blank for all) and compute.</EmptyState>
          )}
        </>
      )}

      {vizMode === "epochs" && (
        <>
          <div className="toolbar">
            <button
              type="button"
              className="btn"
              disabled={!idle}
              onClick={async () => {
                const r = await createEpochs();
                if (r?.epochset?.id) await loadEpochSet(r.epochset.id);
              }}
            >
              Create epochs ({EPOCH_WINDOW.tmin} to {EPOCH_WINDOW.tmax} s)
            </button>
            {recEpochsets.length > 1 && (
              <Field label="Epoch set">
                <select value={epochSet?.id ?? ""} onChange={(e) => void loadEpochSet(e.target.value)} disabled={!idle}>
                  {recEpochsets.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name} · {e.n_trials} trials · {fmtDate(e.created_at)}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            <button type="button" className="btn" onClick={() => void loadEpochSet(epochSet?.id)} disabled={!idle}>
              Reload
            </button>
            <span className="help num">
              {epochSet
                ? `${epochSet.trials?.filter((t: any) => t.rejected).length || 0} rejected of ${epochSet.trials?.length || 0}`
                : ""}
            </span>
            <div className="tool-end tool-group">
              <button type="button" className="btn" onClick={() => setPendingEpochReject([])} disabled={!pendingEpochReject.length}>
                Clear
              </button>
              <button type="button" className="btn btn-danger" onClick={() => void applyEpochReject()} disabled={!idle || !pendingEpochReject.length}>
                Toggle {pendingEpochReject.length || ""} selected
              </button>
            </div>
          </div>
          <p className="help">
            Select trials, then toggle: kept trials become rejected and rejected trials are restored. A clean epochs FIF
            is rewritten; the original epochs file is kept.
          </p>
          {epochSet?.trials?.length ? (
            <div className="epoch-grid">
              {epochSet.trials.map((t: any) => {
                const pending = pendingEpochReject.includes(t.index);
                return (
                  <button
                    key={t.index}
                    type="button"
                    className={`epoch ${t.rejected ? "rejected" : ""} ${pending ? "pending" : ""}`}
                    onClick={() => togglePendingEpoch(t.index)}
                    title={`${t.event_name} @ ${Number(t.onset).toFixed(2)} s${t.rejected ? " · rejected" : ""}`}
                    aria-pressed={pending}
                  >
                    {t.index}
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState title="No epochs for this recording">
              Epochs are cut around event markers. Create them here or in the Preprocess step.
            </EmptyState>
          )}
        </>
      )}
    </div>
  );

  // ── NEUROFLOW: Preprocess ─────────────────────────────────────────────────
  const selectedPlan = plans.find((p) => p.id === effPlanId) ?? null;
  const planRun = results.planRun as { artifacts?: Array<{ id: string; operation?: string }> } | undefined;
  const flowPlan = !selectedRecId ? (
    needRecording("Preprocessing")
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

  // ── NEUROFLOW: Analyze ────────────────────────────────────────────────────
  const flowReview = !selectedRecId ? (
    needRecording("Analysis")
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

  // ── NEUROSTUDIO ───────────────────────────────────────────────────────────
  const selectedDataset = datasets.find((d) => d.id === effDatasetId) ?? null;
  const hasAnySplit = datasets.some((d) => splits.some((sp) => sp.dataset_id === d.id));
  const expBlock = !effDatasetId ? "Build a dataset first." : !effSplitId ? "Create a split for this dataset first." : null;
  const modelBlock = !selExperiment ? "Create an experiment first." : !isTrained(selExperiment) ? "Train this experiment first." : null;
  const evalMetrics = (results.eval as any)?.metrics as Record<string, any> | undefined;

  const studioData =
    !epochsets.length ? (
      <EmptyState
        title="No epochs in this study yet"
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setPage("flow");
              setFlowStage(recRows.length ? "plan" : "recording");
            }}
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

  const studioTrain = (
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
          The template recommender is a placeholder that always suggests EEGNet. Training currently fits a scikit-learn
          logistic regression (standardized features) on the training split; Braindecode/EEGNet training is not wired
          yet.
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
            Recommended: {(results.recommend as any).recommendations.map((r: any) => r.template_id).join(", ")} (placeholder)
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
                  void studioRun("infer", "Running inference", "neurostudio.infer.run", { experiment_id: selExperiment.id }, (r) => `Predicted ${r.labels?.length ?? 0} samples`)
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

  const report = results.report as { markdown?: string; path?: string } | undefined;
  const studioExport = (
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

  // ── Layout ────────────────────────────────────────────────────────────────
  // Step states come only from backend data: "done" means the step's output exists.
  const noStudyHint = "Create or choose a study first.";
  const noRecHint = recRows.length ? "Choose a recording first." : "Import a recording first.";
  const flowSteps: StepDef[] = FLOW_STAGES.map((s) => {
    if (!selectedId) return { id: s.id, label: s.label, status: "unavailable", hint: noStudyHint };
    if (s.id === "recording") {
      return selectedRec
        ? { id: s.id, label: s.label, status: "done", hint: "A recording is imported and selected." }
        : { id: s.id, label: s.label, status: "available" };
    }
    if (!selectedRec) return { id: s.id, label: s.label, status: "unavailable", hint: noRecHint };
    if (s.id === "plan" && recEpochsets.length) {
      return { id: s.id, label: s.label, status: "done", hint: "Epochs exist for this recording." };
    }
    if (s.id === "review" && (featuresets.length || analyses.length)) {
      return { id: s.id, label: s.label, status: "done", hint: "Features or statistics exist for this recording." };
    }
    return { id: s.id, label: s.label, status: "available" };
  });
  const studioSteps: StepDef[] = STUDIO_STAGES.map((s) => {
    if (!selectedId) return { id: s.id, label: s.label, status: "unavailable", hint: noStudyHint };
    if (s.id === "data") {
      if (hasAnySplit) return { id: s.id, label: s.label, status: "done", hint: "A dataset with a split exists." };
      if (!epochsets.length) return { id: s.id, label: s.label, status: "unavailable", hint: "Create epochs in NeuroFlow first." };
      return { id: s.id, label: s.label, status: "available" };
    }
    if (s.id === "train") {
      if (trainedExperiments.length) return { id: s.id, label: s.label, status: "done", hint: "At least one experiment has a trained model." };
      if (!hasAnySplit) return { id: s.id, label: s.label, status: "unavailable", hint: "Build a dataset and create a split first." };
      return { id: s.id, label: s.label, status: "available" };
    }
    return { id: s.id, label: s.label, status: "available" };
  });

  const inModule = page === "flow" || page === "studio";
  const inWorkflow = inModule && !!selectedId;
  const steps = page === "flow" ? flowSteps : studioSteps;
  const stepIndex = page === "flow" ? flowIndex : studioIndex;
  const prevLabel =
    page === "flow" ? (FLOW_STAGES[flowIndex - 1]?.label ?? "Home") : (STUDIO_STAGES[studioIndex - 1]?.label ?? "Home");
  const nextLabel =
    page === "flow" ? (FLOW_STAGES[flowIndex + 1]?.label ?? "NeuroStudio") : (STUDIO_STAGES[studioIndex + 1]?.label ?? null);
  const nextStepDef = steps[stepIndex + 1];
  const nextReady = page === "flow" && !nextStepDef ? true : nextStepDef?.status !== "unavailable";

  function goPrev() {
    if (page === "flow") {
      const p = FLOW_STAGES[flowIndex - 1];
      if (p) setFlowStage(p.id);
      else setPage("home");
    } else {
      const p = STUDIO_STAGES[studioIndex - 1];
      if (p) setStudioStage(p.id);
      else setPage("home");
    }
  }
  function goNext() {
    if (page === "flow") {
      const n = FLOW_STAGES[flowIndex + 1];
      if (n) setFlowStage(n.id);
      else {
        setPage("studio");
        setStudioStage("data");
      }
    } else {
      const n = STUDIO_STAGES[studioIndex + 1];
      if (n) setStudioStage(n.id);
    }
  }

  const moduleHead = inModule && (
    <div className={`module-head mod-${page}`}>
      <div className="module-id">
        <span className="module-badge">
          <Icon name={page === "flow" ? "flow" : "studio"} size={15} />
          {page === "flow" ? "NeuroFlow" : "NeuroStudio"}
        </span>
        <span className="module-purpose">
          {page === "flow"
            ? "Process one recording at a time: import, inspect, preprocess, analyze."
            : "Model across the whole study: datasets, experiments, training, evaluation, export."}
        </span>
      </div>
      <div className="module-row">
        <div className="module-title">
          <h1>{page === "flow" ? flowMeta.title : studioMeta.title}</h1>
          {selectedId && <p className="page-desc">{page === "flow" ? flowMeta.description : studioMeta.description}</p>}
        </div>
        {page === "flow" ? (
          <Stepper
            steps={flowSteps}
            current={flowStage}
            running={!!busy}
            onSelect={(id) => setFlowStage(id as FlowStage)}
            label="NeuroFlow steps"
          />
        ) : (
          <Stepper
            steps={studioSteps}
            current={studioStage}
            running={!!busy}
            onSelect={(id) => setStudioStage(id as StudioStage)}
            label="NeuroStudio steps"
          />
        )}
      </div>
    </div>
  );

  return (
    <div className={`app page-${page} ${sidebarOpen ? "rail-open" : ""}`}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <nav className="rail" aria-label="Main">
        <div className="brand" title="NeuroTendrils Suite">
          <span className="brand-mark">NT</span>
          {sidebarOpen && (
            <span className="brand-word">
              NeuroTendrils <span>Suite</span>
            </span>
          )}
        </div>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`rail-item mod-${item.id} ${page === item.id ? "active" : ""}`}
            title={sidebarOpen ? undefined : `${item.label} — ${item.sub}`}
            aria-label={sidebarOpen ? undefined : item.label}
            aria-current={page === item.id ? "page" : undefined}
            onClick={() => goPage(item.id)}
          >
            <span className="rail-icon">
              <Icon name={item.icon} size={19} />
            </span>
            {sidebarOpen && (
              <span className="rail-text">
                <span className="rail-label">{item.label}</span>
                <span className="rail-sub">{item.sub}</span>
              </span>
            )}
          </button>
        ))}
        <div className="rail-spacer" />
        <button
          type="button"
          className="rail-item rail-toggle"
          title={sidebarOpen ? "Collapse navigation" : "Expand navigation"}
          aria-label={sidebarOpen ? "Collapse navigation" : "Expand navigation"}
          aria-expanded={sidebarOpen}
          onClick={() => setSidebarOpen((v) => !v)}
        >
          <span className="rail-icon">
            <Icon name={sidebarOpen ? "chevronLeft" : "chevronRight"} size={17} />
          </span>
          {sidebarOpen && <span className="rail-label">Collapse</span>}
        </button>
      </nav>

      <div className="shell">
        <header className="topbar">
          {studies.length ? (
            <label className="topbar-study" title="The active study. NeuroFlow and NeuroStudio work on this study.">
              <span className="topbar-key">Study</span>
              <select value={selectedId ?? ""} onChange={(e) => void selectStudy(e.target.value)} aria-label="Active study">
                {!selectedId && <option value="">Choose a study…</option>}
                {studies.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <span className="topbar-study topbar-empty">
              <span className="topbar-key">Study</span>
              {studiesLoaded ? "None yet" : "—"}
            </span>
          )}
          {selectedRow && (
            <button
              type="button"
              className="topbar-rec"
              title={`Active recording ${selectedRow.rec.id}. Click to inspect it.`}
              onClick={() => {
                setPage("flow");
                if (flowStage === "recording") setFlowStage("inspect");
              }}
            >
              <span className="topbar-key">Recording</span>
              <span className="topbar-rec-name">{recordingLabel(selectedRow)}</span>
            </button>
          )}
          {pendingCount > 0 && (
            <span title="Rejection marks not yet applied to the recording">
              <Badge tone="warn">{pendingCount} unapplied mark{pendingCount === 1 ? "" : "s"}</Badge>
            </span>
          )}
          <div className="topbar-right">
            <BusyIndicator busy={busy} />
            <ConnectionStatus conn={conn} onRetry={() => void refresh()} />
            <button
              type="button"
              className="btn-icon"
              title="Reload studies and status from the backend"
              aria-label="Reload from backend"
              onClick={() => void refresh()}
              disabled={!!busy}
            >
              <Icon name="refresh" size={17} />
            </button>
            <button
              type="button"
              className="btn-icon"
              title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            >
              <Icon name={theme === "dark" ? "sun" : "moon"} size={17} />
            </button>
          </div>
        </header>

        <NoticeBar notice={notice} onDismiss={() => setNotice(null)} />

        {moduleHead}

        <main
          id="main"
          tabIndex={-1}
          className={`content ${page === "flow" && flowStage === "inspect" && selectedId ? "content-wide" : ""}`}
        >
          {page === "home" && homePage}
          {page === "flow" && !selectedId && noStudy("NeuroFlow")}
          {page === "studio" && !selectedId && noStudy("NeuroStudio")}
          {page === "flow" && selectedId && (
            <>
              {flowStage !== "recording" && recordingPicker}
              {flowStage === "recording" && flowImport}
              {flowStage === "inspect" && flowInspect}
              {flowStage === "plan" && flowPlan}
              {flowStage === "review" && flowReview}
            </>
          )}
          {page === "studio" && selectedId && (
            <>
              {studioStage === "data" && studioData}
              {studioStage === "train" && studioTrain}
              {studioStage === "export" && studioExport}
            </>
          )}
        </main>

        {inWorkflow && (
          <footer className="stage-footer">
            <button type="button" className="btn" onClick={goPrev}>
              <Icon name="chevronLeft" size={15} /> {prevLabel}
            </button>
            <span className="stage-pos">
              Step {stepIndex + 1} of {steps.length}
              {nextStepDef?.status === "unavailable" && nextStepDef.hint ? ` · Next: ${nextStepDef.hint}` : ""}
            </span>
            {nextLabel && (
              <button type="button" className={`btn ${nextReady ? "btn-primary" : ""}`} onClick={goNext}>
                {nextLabel} <Icon name="chevronRight" size={15} />
              </button>
            )}
          </footer>
        )}

        <ActivityLog
          entries={logEntries}
          open={logOpen}
          busy={busy}
          onToggle={() => setLogOpen((v) => !v)}
          onClear={() => setLogEntries([])}
        />
      </div>
    </div>
  );
}

function ValidationBadge({ ok, errors, warnings }: { ok: boolean | null; errors: number; warnings: number }) {
  if (ok == null) return <Badge>not validated</Badge>;
  if (!ok) return <Badge tone="danger">{errors} error{errors === 1 ? "" : "s"}</Badge>;
  if (warnings) return <Badge tone="warn">{warnings} warning{warnings === 1 ? "" : "s"}</Badge>;
  return <Badge tone="ok">valid</Badge>;
}

function EpochTable({ rows }: { rows: EpochSetSummary[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th className="r">Trials</th>
            <th>Events</th>
            <th className="r">Window (s)</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id}>
              <td>{e.name}</td>
              <td className="r num">{e.n_trials}</td>
              <td>{e.event_names.join(", ") || "—"}</td>
              <td className="r num">
                {e.tmin} – {e.tmax}
              </td>
              <td className="muted">{fmtDate(e.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SplitTable({ rows, selected, onSelect }: { rows: Split[]; selected: string; onSelect: (id: string) => void }) {
  return (
    <div className="table-wrap">
      <table className="table table-click">
        <thead>
          <tr>
            <th />
            <th>Method</th>
            <th className="r">Train</th>
            <th className="r">Val</th>
            <th className="r">Test</th>
            <th className="r">Seed</th>
            <th>Leakage check</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id} className={s.id === selected ? "selected" : ""} onClick={() => onSelect(s.id)}>
              <td>
                <input type="radio" readOnly checked={s.id === selected} aria-label="Select split" />
              </td>
              <td>{s.method}</td>
              <td className="r num">{s.train_indices.length}</td>
              <td className="r num">{s.val_indices.length}</td>
              <td className="r num">{s.test_indices.length}</td>
              <td className="r num">{fmtMetric(s.parameters?.seed)}</td>
              <td>
                {s.leakage_check?.ok === false ? (
                  <span title={(s.leakage_check.warnings || []).join("\n")}>
                    <Badge tone="warn">{s.leakage_check.warnings?.length ?? 0} warning(s)</Badge>
                  </span>
                ) : s.leakage_check?.ok ? (
                  <Badge tone="ok">ok</Badge>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td className="muted">{fmtDate(s.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
