import { useEffect, useMemo, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { suiteCall, waitForSuiteRuntime } from "./ipc";
import "./App.css";

type StudySummary = {
  id: string;
  name: string;
  schema_version?: number;
  subjects: Array<{ id: string; label: string }>;
};

type ManagerStream = {
  id: string;
  name: string | null;
  modality: string;
  sfreq: number | null;
  n_channels: number;
  units: string | null;
  normalized: boolean;
};

type ManagerRec = {
  id: string;
  name: string | null;
  source_format: string | null;
  sampling_rate: number | null;
  duration: number | null;
  modalities: string[];
  stream_ids: string[];
  streams: ManagerStream[];
  validation_ok: boolean | null;
  validation_errors: number;
  validation_warnings: number;
  sync_group_ids: string[];
  sync_confidence: number | null;
};

type Manager = {
  study_id: string;
  name: string;
  schema_version: number;
  subjects: Array<{
    id: string;
    label: string;
    metadata: Record<string, unknown>;
    sessions: Array<{
      id: string;
      name: string;
      runs: Array<{
        id: string;
        name: string;
        recordings: ManagerRec[];
      }>;
    }>;
  }>;
  totals: { subjects: number; streams: number; recordings: number };
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

type VizMode = "signal" | "ica" | "erp";

type Tab =
  | "import"
  | "sync"
  | "validate"
  | "timeline"
  | "events"
  | "preprocess"
  | "epochs"
  | "features";

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
}: {
  times: number[];
  data: number[][];
  channels: string[];
  channelStatus?: string[];
  events: Array<{ name: string; timestamp: number; end?: number; kind?: string; artifact?: boolean }>;
  start: number;
  duration: number;
  gain?: number;
  width?: number;
  rowH?: number;
  onChannelClick?: (channel: string) => void;
  onRegionSelect?: (t0: number, t1: number) => void;
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
        return (
          <rect
            key={`art-${a.name}-${i}`}
            x={x0}
            y={4}
            width={Math.max(2, x1 - x0)}
            height={h - axisH - 4}
            fill="#a33"
            opacity={0.25}
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
  const [status, setStatus] = useState("starting…");
  const [error, setError] = useState<string | null>(null);
  const [studies, setStudies] = useState<StudySummary[]>([]);
  const [studyName, setStudyName] = useState("Motor Imagery");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [manager, setManager] = useState<Manager | null>(null);
  const [selectedRecId, setSelectedRecId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("import");
  const [subjectLabel, setSubjectLabel] = useState("S001");
  const [subjectMeta, setSubjectMeta] = useState("{}");
  const [importPath, setImportPath] = useState("");
  const [inspect, setInspect] = useState<InspectInfo | null>(null);
  const [sfreq, setSfreq] = useState("250");
  const [dataKey, setDataKey] = useState("");
  const [transpose, setTranspose] = useState(false);
  const [montage, setMontage] = useState("");
  const [columns, setColumns] = useState<Array<{ index: number; name: string; role: string }>>(
    [],
  );
  const [extPath, setExtPath] = useState("");
  const [extInspect, setExtInspect] = useState<InspectInfo | null>(null);
  const [extModality, setExtModality] = useState("gyroscope");
  const [extSfreq, setExtSfreq] = useState("100");
  const [extUnits, setExtUnits] = useState("");
  const [extRecordingId, setExtRecordingId] = useState("");
  const [syncMethod, setSyncMethod] = useState("shared_triggers");
  const [syncGroups, setSyncGroups] = useState<SyncGroup[]>([]);
  const [offsetEdits, setOffsetEdits] = useState<Record<string, string>>({});
  const [validationJson, setValidationJson] = useState("");
  const [tlStart, setTlStart] = useState(0);
  const [tlDur, setTlDur] = useState(4);
  const [tlGain, setTlGain] = useState(1);
  const [tlBusy, setTlBusy] = useState(false);
  const [tlRev, setTlRev] = useState(0);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [vizMode, setVizMode] = useState<VizMode>("signal");
  const [pendingSegments, setPendingSegments] = useState<
    Array<{ start: number; end: number }>
  >([]);
  const [pendingBadChannels, setPendingBadChannels] = useState<string[]>([]);
  const [erpChannel, setErpChannel] = useState<string>("");
  const [icaData, setIcaData] = useState<any | null>(null);
  const [icaBusy, setIcaBusy] = useState(false);
  const [erpData, setErpData] = useState<any | null>(null);
  const [erpBusy, setErpBusy] = useState(false);
  const [erpEvent, setErpEvent] = useState("");
  const [flowJson, setFlowJson] = useState("");
  const [eventName, setEventName] = useState("manual");
  const [eventTime, setEventTime] = useState("1.0");
  const [log, setLog] = useState("");

  function appendLog(msg: string) {
    setLog((p) => `${msg}\n${p}`.slice(0, 4000));
  }

  const selectedRec: ManagerRec | null = useMemo(() => {
    if (!manager || !selectedRecId) return null;
    for (const sub of manager.subjects) {
      for (const ses of sub.sessions) {
        for (const run of ses.runs) {
          const rec = run.recordings.find((r) => r.id === selectedRecId);
          if (rec) return rec;
        }
      }
    }
    return null;
  }, [manager, selectedRecId]);

  async function loadManager(studyId: string) {
    const mgr = await suiteCall<Manager>("studies.manager", { study_id: studyId });
    setManager(mgr);
    if (selectedRecId) {
      const still =
        mgr.subjects.some((s) =>
          s.sessions.some((ses) =>
            ses.runs.some((r) => r.recordings.some((rec) => rec.id === selectedRecId)),
          ),
        ) ?? false;
      if (!still) setSelectedRecId(null);
    }
    return mgr;
  }

  async function refresh() {
    try {
      await waitForSuiteRuntime();
      const health = await suiteCall<{ status: string; version: string }>("health");
      setStatus(`backend ${health.status} v${health.version}`);
      const listed = await suiteCall<{ studies: StudySummary[] }>("studies.list");
      setStudies(listed.studies);
      const id = selectedId ?? listed.studies[0]?.id ?? null;
      if (!selectedId && id) setSelectedId(id);
      if (id) await loadManager(id);
      else setManager(null);
      setError(null);
    } catch (e) {
      setError(String(e));
      setStatus("offline");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (selectedRecId && selectedId) {
      void suiteCall<{ sync_groups: SyncGroup[] }>("sync.list", {
        study_id: selectedId,
        recording_id: selectedRecId,
      })
        .then((r) => setSyncGroups(r.sync_groups))
        .catch(() => setSyncGroups([]));
    } else {
      setSyncGroups([]);
    }
  }, [selectedRecId, selectedId, manager]);

  async function createStudy() {
    const s = await suiteCall<StudySummary>("studies.create", { name: studyName });
    setSelectedId(s.id);
    appendLog(`created study ${s.id}`);
    await refresh();
  }

  async function selectStudy(id: string) {
    setSelectedId(id);
    setSelectedRecId(null);
    setTimeline(null);
    await loadManager(id);
  }

  async function addSubject() {
    if (!selectedId) return;
    let metadata: Record<string, unknown> = {};
    try {
      metadata = JSON.parse(subjectMeta || "{}");
    } catch {
      setError("Subject metadata must be valid JSON");
      return;
    }
    await suiteCall("subjects.add", {
      study_id: selectedId,
      label: subjectLabel,
      metadata,
    });
    appendLog(`added subject ${subjectLabel}`);
    await refresh();
  }

  async function ensureSubjectSession() {
    if (!selectedId) throw new Error("no study");
    let study = await suiteCall<any>("studies.get", { study_id: selectedId });
    let subject =
      study.subjects.find((s: any) => s.label === subjectLabel) ?? study.subjects[0];
    if (!subject) {
      const added = await suiteCall<any>("subjects.add", {
        study_id: selectedId,
        label: subjectLabel || "S001",
      });
      subject = added.subject;
      study = await suiteCall<any>("studies.get", { study_id: selectedId });
      subject = study.subjects.find((s: any) => s.id === subject.id) ?? study.subjects[0];
    }
    return { subject, session: subject.sessions[0], run: subject.sessions[0].runs[0] };
  }

  async function browseImport() {
    const selected = await open({
      multiple: false,
      title: "Import EEG recording",
      filters: [
        {
          name: "EEG",
          extensions: [
            "fif",
            "edf",
            "bdf",
            "gdf",
            "set",
            "vhdr",
            "cnt",
            "mat",
            "txt",
            "csv",
            "tsv",
            "asc",
          ],
        },
      ],
    });
    if (typeof selected !== "string" || !selected) return;
    setImportPath(selected);
    try {
      const info = await suiteCall<InspectInfo>("import.inspect", { path: selected });
      setInspect(info);
      if (info.suggested_data_key) setDataKey(info.suggested_data_key);
      if (typeof info.sfreq === "number") setSfreq(String(info.sfreq));
      if (Array.isArray(info.columns)) {
        setColumns(
          info.columns.map((c) => ({
            index: Number(c.index),
            name: String(c.name),
            role: String(c.role ?? "eeg"),
          })),
        );
      } else setColumns([]);
      appendLog(`inspect ${info.format}: ${info.status}`);
    } catch (e) {
      setInspect(null);
      setError(String(e));
    }
  }

  async function importRecording() {
    if (!selectedId || !importPath) {
      setError("Select a study and file first");
      return;
    }
    try {
      const { subject, session, run } = await ensureSubjectSession();
      const payload: Record<string, unknown> = {
        study_id: selectedId,
        subject_id: subject.id,
        session_id: session.id,
        run_id: run.id,
        path: importPath,
      };
      const needs = new Set(inspect?.required_config || []);
      if (needs.has("sfreq") || inspect?.status === "needs_config") {
        const hz = Number(sfreq);
        if (!Number.isFinite(hz) || hz <= 0) {
          setError("This format requires sampling rate (Hz)");
          return;
        }
        payload.sfreq = hz;
      }
      if (needs.has("data_key")) {
        if (!dataKey) {
          setError("MAT import requires data_key");
          return;
        }
        payload.data_key = dataKey;
      }
      if (transpose) payload.transpose = true;
      if (montage) payload.montage = montage;
      if (columns.length) payload.column_selection = columns;
      const res = await suiteCall<any>("import.recording", payload);
      setSelectedRecId(res.recording.id);
      appendLog(`imported EEG ${res.recording.id}`);
      setError(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function browseExternal() {
    const selected = await open({
      multiple: false,
      title: "Import external modality",
      filters: [{ name: "Streams", extensions: ["txt", "csv", "tsv", "asc", "mat", "npy"] }],
    });
    if (typeof selected !== "string" || !selected) return;
    setExtPath(selected);
    try {
      const info = await suiteCall<InspectInfo>("import.stream.inspect", { path: selected });
      setExtInspect(info);
      if (info.suggested_modality) setExtModality(info.suggested_modality);
      appendLog(`stream inspect ${info.format}`);
    } catch (e) {
      setExtInspect(null);
      setError(String(e));
    }
  }

  async function importExternalStream() {
    if (!selectedId || !extPath) {
      setError("Select study and external file");
      return;
    }
    const hz = Number(extSfreq);
    if (!Number.isFinite(hz) || hz <= 0) {
      setError("External stream requires sfreq (Hz)");
      return;
    }
    try {
      const { subject, session, run } = await ensureSubjectSession();
      const payload: Record<string, unknown> = {
        study_id: selectedId,
        subject_id: subject.id,
        session_id: session.id,
        run_id: run.id,
        path: extPath,
        modality: extModality,
        sfreq: hz,
      };
      if (extUnits) payload.units = extUnits;
      const attach = extRecordingId || selectedRecId || "";
      if (attach) payload.recording_id = attach;
      const res = await suiteCall<any>("import.stream", payload);
      setSelectedRecId(res.recording.id);
      appendLog(`imported ${res.stream.modality} → ${res.recording.id}`);
      setError(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function createSync() {
    if (!selectedId || !selectedRecId) {
      setError("Select a recording first");
      return;
    }
    try {
      const res = await suiteCall<{ sync_group: SyncGroup }>("sync.create", {
        study_id: selectedId,
        recording_id: selectedRecId,
        method: syncMethod,
      });
      appendLog(`sync ${res.sync_group.id} method=${res.sync_group.method}`);
      setError(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function applyOffset(syncGroupId: string, streamId: string) {
    if (!selectedId) return;
    const raw = offsetEdits[streamId] ?? "0";
    const offset = Number(raw);
    if (!Number.isFinite(offset)) {
      setError("offset must be a number (seconds)");
      return;
    }
    try {
      await suiteCall("sync.set_offset", {
        study_id: selectedId,
        sync_group_id: syncGroupId,
        stream_id: streamId,
        offset_sec: offset,
      });
      appendLog(`offset ${streamId.slice(0, 8)}… = ${offset}s`);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function runValidate(scope: "recording" | "study") {
    if (!selectedId) return;
    try {
      if (scope === "study") {
        const report = await suiteCall<any>("validate.study", { study_id: selectedId });
        setValidationJson(JSON.stringify(report, null, 2));
        appendLog(`validate study ok=${report.ok}`);
      } else {
        if (!selectedRecId) {
          setError("Select a recording to validate");
          return;
        }
        const report = await suiteCall<any>("validate.recording", {
          study_id: selectedId,
          recording_id: selectedRecId,
        });
        setValidationJson(JSON.stringify(report, null, 2));
        appendLog(
          `validate recording ok=${report.ok} errors=${report.blocking_errors?.length ?? 0} warns=${report.warnings?.length ?? 0}`,
        );
      }
      setError(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  // Auto-load timeline when recording/window changes — no manual Load button.
  useEffect(() => {
    if (tab !== "timeline" || !selectedId || !selectedRecId) {
      return;
    }
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
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setTlBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, selectedId, selectedRecId, tlStart, tlDur, tlRev]);

  function nudgeTime(delta: number) {
    setTlStart((s) => Math.max(0, +(s + delta).toFixed(4)));
  }

  async function runFlow(cmd: string, params: Record<string, unknown> = {}) {
    if (!selectedId) {
      setError("Select a study");
      return;
    }
    try {
      const res = await suiteCall<any>(cmd, {
        study_id: selectedId,
        ...(selectedRecId ? { recording_id: selectedRecId } : {}),
        ...params,
      });
      setFlowJson(JSON.stringify(res, null, 2));
      appendLog(`${cmd} ok`);
      setError(null);
      await refresh();
      return res;
    } catch (e) {
      setError(String(e));
      return null;
    }
  }

  function togglePendingBadChannel(channel: string) {
    setPendingBadChannels((prev) =>
      prev.includes(channel) ? prev.filter((c) => c !== channel) : [...prev, channel],
    );
  }

  function markPendingSegment(t0: number, t1: number) {
    setPendingSegments((prev) => [...prev, { start: t0, end: t1 }]);
    appendLog(`marked ${t0.toFixed(2)}–${t1.toFixed(2)}s (not applied yet)`);
  }

  async function applyRejectMarks() {
    if (!selectedId || !selectedRecId) return;
    if (!pendingSegments.length && !pendingBadChannels.length) {
      setError("Nothing marked — drag on the plot to mark a bad portion, or click a channel label");
      return;
    }
    for (const seg of pendingSegments) {
      await runFlow("artifacts.apply", {
        suggestion: {
          kind: "bad_segment",
          start: seg.start,
          end: seg.end,
          method: "manual_visualizer",
          reason: "REJECT in visualizer",
          placeholder: false,
        },
      });
    }
    for (const ch of pendingBadChannels) {
      await runFlow("channels.update", { channel_name: ch, bad: true });
    }
    setPendingSegments([]);
    setPendingBadChannels([]);
    setTlRev((n) => n + 1);
    appendLog("REJECT applied (annotations/decisions only — raw untouched)");
  }

  async function loadIca() {
    if (!selectedId || !selectedRecId) return;
    setIcaBusy(true);
    try {
      const res = await suiteCall<any>("ica.components.list", {
        study_id: selectedId,
        recording_id: selectedRecId,
        n_components: 15,
      });
      setIcaData(res);
      appendLog(`ICA ${res.n_components} components`);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setIcaBusy(false);
    }
  }

  async function toggleIcaReject(index: number) {
    if (!selectedId || !selectedRecId || !icaData) return;
    const comp = icaData.components?.find((c: any) => c.index === index);
    const action = comp?.rejected ? "keep" : "reject";
    await runFlow("ica.component.set_rejection", {
      component_indices: [index],
      action,
    });
    await loadIca();
  }

  async function loadErp() {
    if (!selectedId || !selectedRecId) return;
    setErpBusy(true);
    try {
      const res = await suiteCall<any>("erp.compute", {
        study_id: selectedId,
        recording_id: selectedRecId,
        event_name: erpEvent || null,
        tmin: -0.2,
        tmax: 0.8,
      });
      setErpData(res);
      appendLog(`ERP status=${res.status} nave=${res.nave ?? 0}`);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setErpBusy(false);
    }
  }

  const needsConfig = inspect?.status === "needs_config" || inspect?.self_describing === false;

  const recordingOptions =
    manager?.subjects.flatMap((sub) =>
      sub.sessions.flatMap((ses) =>
        ses.runs.flatMap((run) =>
          run.recordings.map((rec) => ({
            id: rec.id,
            label: `${sub.label}/${ses.name}/${run.name} · ${rec.modalities.join("+") || "?"} · ${rec.id.slice(0, 10)}`,
          })),
        ),
      ),
    ) ?? [];

  return (
    <div className="app">
      <header>
        <h1>NeuroTendrils Suite</h1>
        <span className="muted">{status}</span>
        <button type="button" onClick={() => void refresh()}>
          Refresh
        </button>
      </header>
      {error && <div className="error">{error}</div>}

      <div className="layout">
        <aside className="sidebar">
          <h2>Studies</h2>
          <div className="row">
            <input value={studyName} onChange={(e) => setStudyName(e.target.value)} />
            <button type="button" onClick={() => void createStudy()}>
              Create
            </button>
          </div>
          <ul className="study-list">
            {studies.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className={s.id === selectedId ? "active" : ""}
                  onClick={() => void selectStudy(s.id)}
                >
                  {s.name}
                  <span className="muted"> v{s.schema_version ?? 1}</span>
                </button>
              </li>
            ))}
          </ul>

          {manager && (
            <>
              <h2>
                Manager{" "}
                <span className="muted">
                  {manager.totals.subjects}s / {manager.totals.recordings}r /{" "}
                  {manager.totals.streams}str
                </span>
              </h2>
              <div className="row">
                <input
                  value={subjectLabel}
                  onChange={(e) => setSubjectLabel(e.target.value)}
                  placeholder="S001"
                  style={{ width: 70 }}
                />
                <input
                  value={subjectMeta}
                  onChange={(e) => setSubjectMeta(e.target.value)}
                  placeholder="{}"
                  style={{ flex: 1, minWidth: 0 }}
                />
                <button type="button" onClick={() => void addSubject()}>
                  +subj
                </button>
              </div>
              <div className="tree">
                {manager.subjects.map((sub) => (
                  <div key={sub.id} className="tree-sub">
                    <div className="tree-label">{sub.label}</div>
                    {sub.sessions.map((ses) =>
                      ses.runs.map((run) =>
                        run.recordings.map((rec) => (
                          <button
                            key={rec.id}
                            type="button"
                            className={`tree-rec ${rec.id === selectedRecId ? "active" : ""}`}
                            onClick={() => {
                              setSelectedRecId(rec.id);
                              setExtRecordingId(rec.id);
                              setTlStart(0);
                              setTab("timeline");
                            }}
                          >
                            <div>
                              {(rec.modalities.length ? rec.modalities : ["?"]).join("+")} ·{" "}
                              {rec.source_format ?? "—"}
                            </div>
                            <div className="muted tiny">
                              {rec.id.slice(0, 12)} · {rec.streams.length} streams
                              {rec.validation_ok === true
                                ? " · ok"
                                : rec.validation_ok === false
                                  ? " · FAIL"
                                  : ""}
                              {rec.sync_group_ids.length
                                ? ` · sync~${(rec.sync_confidence ?? 0).toFixed(2)}`
                                : " · no sync"}
                            </div>
                          </button>
                        )),
                      ),
                    )}
                    {!sub.sessions.some((s) => s.runs.some((r) => r.recordings.length)) && (
                      <div className="muted tiny">no recordings</div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>

        <main className="main">
          {!selectedId && <p className="muted">Create or select a study.</p>}
          {selectedId && (
            <>
              <div className="tabs">
                {(
                  [
                    ["import", "Import"],
                    ["timeline", "Visualizer"],
                    ["sync", "Sync"],
                    ["validate", "Validate"],
                    ["events", "Events"],
                    ["preprocess", "Preprocess"],
                    ["epochs", "Epochs"],
                    ["features", "Features"],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    className={tab === id ? "active" : ""}
                    onClick={() => setTab(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {selectedRec && (
                <p className="rec-banner">
                  Recording <code>{selectedRec.id.slice(0, 16)}</code> ·{" "}
                  {selectedRec.modalities.join(", ") || "no modalities"} ·{" "}
                  {selectedRec.streams.length} streams
                </p>
              )}

              {tab === "import" && (
                <section>
                  <h2>Import EEG</h2>
                  <div className="row">
                    <button type="button" onClick={() => void browseImport()}>
                      Browse…
                    </button>
                    <input
                      style={{ flex: 1 }}
                      value={importPath}
                      onChange={(e) => setImportPath(e.target.value)}
                      placeholder="FIF/EDF/… or TXT/CSV/MAT"
                    />
                    <button
                      type="button"
                      onClick={() => void importRecording()}
                      disabled={!importPath}
                    >
                      Import EEG
                    </button>
                  </div>
                  {inspect && (
                    <div className="box">
                      <p>
                        <strong>{inspect.format}</strong> · {inspect.status}
                      </p>
                      {needsConfig && (
                        <div className="row">
                          <label>
                            sfreq{" "}
                            <input
                              style={{ width: 70 }}
                              value={sfreq}
                              onChange={(e) => setSfreq(e.target.value)}
                            />
                          </label>
                          {(inspect.format === "mat" ||
                            inspect.required_config?.includes("data_key")) && (
                            <label>
                              data_key{" "}
                              <select
                                value={dataKey}
                                onChange={(e) => setDataKey(e.target.value)}
                              >
                                <option value="">(choose)</option>
                                {(inspect.candidates || []).map((c) => (
                                  <option key={c.key} value={c.key}>
                                    {c.key} {JSON.stringify(c.shape)}
                                  </option>
                                ))}
                              </select>
                            </label>
                          )}
                          <label>
                            <input
                              type="checkbox"
                              checked={transpose}
                              onChange={(e) => setTranspose(e.target.checked)}
                            />{" "}
                            transpose
                          </label>
                          <label>
                            montage{" "}
                            <input
                              value={montage}
                              onChange={(e) => setMontage(e.target.value)}
                              placeholder="optional"
                            />
                          </label>
                        </div>
                      )}
                      {columns.length > 0 && (
                        <div className="chan-table-wrap">
                          <table className="chan-table">
                            <thead>
                              <tr>
                                <th>#</th>
                                <th>Label</th>
                                <th>Role</th>
                              </tr>
                            </thead>
                            <tbody>
                              {columns.map((col, i) => (
                                <tr key={col.index}>
                                  <td>{col.index + 1}</td>
                                  <td>
                                    <input
                                      value={col.name}
                                      onChange={(e) => {
                                        const name = e.target.value;
                                        setColumns((cols) =>
                                          cols.map((c, j) => (j === i ? { ...c, name } : c)),
                                        );
                                      }}
                                    />
                                  </td>
                                  <td>
                                    <select
                                      value={col.role}
                                      onChange={(e) => {
                                        const role = e.target.value;
                                        setColumns((cols) =>
                                          cols.map((c, j) => (j === i ? { ...c, role } : c)),
                                        );
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
                      )}
                    </div>
                  )}

                  <h2>Import external stream</h2>
                  <div className="row">
                    <button type="button" onClick={() => void browseExternal()}>
                      Browse…
                    </button>
                    <input
                      style={{ flex: 1 }}
                      value={extPath}
                      onChange={(e) => setExtPath(e.target.value)}
                      placeholder="gyro/ECG/… CSV/MAT/NPY"
                    />
                    <button
                      type="button"
                      onClick={() => void importExternalStream()}
                      disabled={!extPath}
                    >
                      Import stream
                    </button>
                  </div>
                  <div className="row">
                    <label>
                      modality{" "}
                      <select
                        value={extModality}
                        onChange={(e) => setExtModality(e.target.value)}
                      >
                        {[
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
                        ].map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      sfreq{" "}
                      <input
                        style={{ width: 70 }}
                        value={extSfreq}
                        onChange={(e) => setExtSfreq(e.target.value)}
                      />
                    </label>
                    <label>
                      units{" "}
                      <input
                        style={{ width: 80 }}
                        value={extUnits}
                        onChange={(e) => setExtUnits(e.target.value)}
                      />
                    </label>
                    <label>
                      attach to{" "}
                      <select
                        value={extRecordingId || selectedRecId || ""}
                        onChange={(e) => setExtRecordingId(e.target.value)}
                      >
                        <option value="">(new recording)</option>
                        {recordingOptions.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {extInspect && (
                    <p className="muted">
                      {extInspect.format} · suggested={extInspect.suggested_modality ?? "—"}
                    </p>
                  )}
                </section>
              )}

              {tab === "sync" && (
                <section>
                  <h2>Synchronization</h2>
                  <p className="muted">
                    Never assumes streams are aligned from similar start times. Use triggers,
                    timestamps, or manual offsets.
                  </p>
                  {!selectedRecId && <p className="muted">Select a recording in the manager.</p>}
                  {selectedRecId && (
                    <>
                      <div className="row">
                        <label>
                          method{" "}
                          <select
                            value={syncMethod}
                            onChange={(e) => setSyncMethod(e.target.value)}
                          >
                            <option value="shared_triggers">shared_triggers</option>
                            <option value="timestamps">timestamps</option>
                            <option value="manual_offset">manual_offset</option>
                          </select>
                        </label>
                        <button type="button" onClick={() => void createSync()}>
                          Create SyncGroup
                        </button>
                      </div>
                      {selectedRec && (
                        <ul className="plain">
                          {selectedRec.streams.map((s) => (
                            <li key={s.id}>
                              {s.modality} · {s.sfreq ?? "?"} Hz · {s.n_channels} ch ·{" "}
                              <code>{s.id.slice(0, 10)}</code>
                            </li>
                          ))}
                        </ul>
                      )}
                      {syncGroups.map((g) => (
                        <div key={g.id} className="box">
                          <p>
                            <strong>{g.id.slice(0, 14)}</strong> · {g.method} · assumed_sync=
                            {String(g.quality?.assumed_synchronized ?? false)} · conf=
                            {Number(g.quality?.mean_confidence ?? 0).toFixed(2)}
                          </p>
                          <table className="chan-table">
                            <thead>
                              <tr>
                                <th>stream</th>
                                <th>method</th>
                                <th>offset (s)</th>
                                <th></th>
                              </tr>
                            </thead>
                            <tbody>
                              {g.links.map((l) => (
                                <tr key={l.stream_id}>
                                  <td>
                                    <code>{l.stream_id.slice(0, 10)}</code>
                                    {l.manual ? " *" : ""}
                                  </td>
                                  <td>{l.method}</td>
                                  <td>
                                    <input
                                      style={{ width: 80 }}
                                      value={
                                        offsetEdits[l.stream_id] ?? String(l.offset_sec)
                                      }
                                      onChange={(e) =>
                                        setOffsetEdits((m) => ({
                                          ...m,
                                          [l.stream_id]: e.target.value,
                                        }))
                                      }
                                    />
                                  </td>
                                  <td>
                                    <button
                                      type="button"
                                      onClick={() => void applyOffset(g.id, l.stream_id)}
                                    >
                                      Set
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ))}
                      {!syncGroups.length && (
                        <p className="muted">No SyncGroups yet for this recording.</p>
                      )}
                    </>
                  )}
                </section>
              )}

              {tab === "validate" && (
                <section>
                  <h2>Validation</h2>
                  <div className="row">
                    <button type="button" onClick={() => void runValidate("recording")}>
                      Validate recording
                    </button>
                    <button type="button" onClick={() => void runValidate("study")}>
                      Validate study
                    </button>
                  </div>
                  {selectedRec && (
                    <p className="muted">
                      cached: ok={String(selectedRec.validation_ok)} · errors=
                      {selectedRec.validation_errors} · warnings=
                      {selectedRec.validation_warnings}
                    </p>
                  )}
                  <pre className="log">{validationJson || "Run validation to see report."}</pre>
                </section>
              )}

              {tab === "events" && (
                <section>
                  <h2>Events / annotations</h2>
                  <div className="row">
                    <button type="button" onClick={() => void runFlow("events.list")}>
                      List events
                    </button>
                    <button type="button" onClick={() => void runFlow("annotations.list")}>
                      List annotations
                    </button>
                    <label>
                      t{" "}
                      <input
                        style={{ width: 60 }}
                        value={eventTime}
                        onChange={(e) => setEventTime(e.target.value)}
                      />
                    </label>
                    <label>
                      name{" "}
                      <input
                        style={{ width: 100 }}
                        value={eventName}
                        onChange={(e) => setEventName(e.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() =>
                        void runFlow("events.create", {
                          timestamp: Number(eventTime) || 0,
                          name: eventName || "manual",
                          source: "manual",
                        })
                      }
                    >
                      Add event
                    </button>
                  </div>
                  <pre className="log">{flowJson || "—"}</pre>
                </section>
              )}

              {tab === "preprocess" && (
                <section>
                  <h2>NeuroFlow plans</h2>
                  <p className="muted">Default plan is a fixed placeholder (not data-adaptive).</p>
                  <div className="row">
                    <button type="button" onClick={() => void runFlow("plans.default")}>
                      Create default plan
                    </button>
                    <button type="button" onClick={() => void runFlow("plans.list")}>
                      List plans
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        let planId = "";
                        try {
                          const parsed = JSON.parse(flowJson || "{}");
                          planId = parsed.plan?.id || parsed.plans?.[0]?.id || "";
                        } catch {
                          planId = "";
                        }
                        if (!planId) {
                          setError("Create/list a plan first");
                          return;
                        }
                        void runFlow("plans.execute", { plan_id: planId });
                      }}
                    >
                      Execute plan
                    </button>
                    <button
                      type="button"
                      onClick={() => void runFlow("neuroflow.recommend_preprocessing")}
                    >
                      Recommend (placeholder)
                    </button>
                  </div>
                  <pre className="log">{flowJson || "—"}</pre>
                </section>
              )}

              {tab === "epochs" && (
                <section>
                  <h2>Epochs / trials</h2>
                  <div className="row">
                    <button
                      type="button"
                      onClick={() =>
                        void runFlow("epochs.create", { tmin: -0.2, tmax: 0.8, name: "epochs" })
                      }
                    >
                      Create from events
                    </button>
                    <button type="button" onClick={() => void runFlow("epochs.list")}>
                      List
                    </button>
                  </div>
                  <pre className="log">{flowJson || "—"}</pre>
                </section>
              )}

              {tab === "features" && (
                <section>
                  <h2>Feature extraction</h2>
                  <div className="row">
                    <button
                      type="button"
                      onClick={() => void runFlow("features.extract", { kind: "band_power" })}
                    >
                      Band power
                    </button>
                    <button
                      type="button"
                      onClick={() => void runFlow("features.extract", { kind: "psd" })}
                    >
                      PSD summary
                    </button>
                    <button type="button" onClick={() => void runFlow("features.list")}>
                      List
                    </button>
                  </div>
                  <pre className="log">{flowJson || "—"}</pre>
                </section>
              )}

              {tab === "timeline" && (
                <section>
                  <h2>Visualizer</h2>
                  {!selectedRecId && (
                    <p className="muted">Select a recording in the manager — it loads automatically.</p>
                  )}
                  {selectedRecId && (
                    <>
                      <div className="row">
                        {(
                          [
                            ["signal", "Signal"],
                            ["ica", "ICA"],
                            ["erp", "ERP"],
                          ] as const
                        ).map(([id, label]) => (
                          <button
                            key={id}
                            type="button"
                            className={vizMode === id ? "active" : ""}
                            onClick={() => {
                              setVizMode(id);
                              if (id === "ica" && !icaData) void loadIca();
                              if (id === "erp" && !erpData) void loadErp();
                            }}
                          >
                            {label}
                          </button>
                        ))}
                      </div>

                      {vizMode === "signal" && (
                        <>
                          <p className="muted tiny">
                            Like EEGLAB eegplot: drag across time to mark a bad portion · click a
                            channel name to mark it bad · press REJECT to confirm (raw never deleted).
                          </p>
                          <div className="eegplot-toolbar">
                            <button type="button" onClick={() => nudgeTime(-tlDur)}>
                              {"<<"}
                            </button>
                            <button type="button" onClick={() => nudgeTime(-tlDur / 4)}>
                              {"<"}
                            </button>
                            <input
                              className="eegplot-time"
                              type="number"
                              step="0.1"
                              min={0}
                              value={tlStart}
                              onChange={(e) =>
                                setTlStart(Math.max(0, Number(e.target.value) || 0))
                              }
                              title="window start (s)"
                            />
                            <button type="button" onClick={() => nudgeTime(tlDur / 4)}>
                              {">"}
                            </button>
                            <button type="button" onClick={() => nudgeTime(tlDur)}>
                              {">>"}
                            </button>
                            <label>
                              win{" "}
                              <input
                                style={{ width: 52 }}
                                type="number"
                                step="0.5"
                                min={0.5}
                                value={tlDur}
                                onChange={(e) =>
                                  setTlDur(Math.max(0.5, Number(e.target.value) || 4))
                                }
                              />
                              s
                            </label>
                            <label>
                              scale{" "}
                              <button
                                type="button"
                                onClick={() => setTlGain((s) => Math.max(0.25, s / 2))}
                              >
                                −
                              </button>
                              <input
                                style={{ width: 52 }}
                                type="number"
                                step="0.25"
                                min={0.25}
                                value={tlGain}
                                onChange={(e) =>
                                  setTlGain(Math.max(0.25, Number(e.target.value) || 1))
                                }
                              />
                              <button type="button" onClick={() => setTlGain((s) => s * 2)}>
                                +
                              </button>
                            </label>
                            <button
                              type="button"
                              className="reject-btn"
                              onClick={() => void applyRejectMarks()}
                            >
                              REJECT
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setPendingSegments([]);
                                setPendingBadChannels([]);
                              }}
                            >
                              Clear marks
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                void runFlow("channels.apply_montage", {
                                  montage: "standard_1020",
                                })
                              }
                            >
                              Montage 10–20
                            </button>
                            <span className="muted tiny">
                              {tlBusy ? "loading…" : ""}{" "}
                              {timeline
                                ? `${timeline.start.toFixed(2)}–${(timeline.start + timeline.duration).toFixed(2)}s`
                                : ""}
                              {pendingSegments.length || pendingBadChannels.length
                                ? ` · pending: ${pendingSegments.length} seg, ${pendingBadChannels.length} ch`
                                : ""}
                            </span>
                          </div>
                          <div className="eegplot-scroll">
                            {[...(timeline?.streams ?? [])]
                              .sort((a, b) => {
                                if (a.modality === "eeg") return -1;
                                if (b.modality === "eeg") return 1;
                                return 0;
                              })
                              .map((st) => {
                                const status = (st.channel_status || st.channels.map(() => "unknown")).map(
                                  (s, i) =>
                                    pendingBadChannels.includes(st.channels[i]) ? "bad" : s,
                                );
                                const evs = [
                                  ...(st.modality === "eeg"
                                    ? timeline.events
                                    : timeline.events.filter((e) => e.modality === st.modality)),
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
                                    <strong>{st.modality}</strong> · {st.channels.length} ch ·
                                    offset={st.offset_sec.toFixed(3)}s
                                    {st.error ? ` · ERR ${st.error}` : ""}
                                  </div>
                                  {!st.error && st.data.length > 0 ? (
                                    <StackedStreamPlot
                                      times={st.times}
                                      data={st.data}
                                      channels={st.channels}
                                      channelStatus={status}
                                      events={evs}
                                      start={timeline.start}
                                      duration={timeline.duration}
                                      gain={tlGain}
                                      width={720}
                                      rowH={st.modality === "eeg" ? 16 : 20}
                                      onChannelClick={
                                        st.modality === "eeg"
                                          ? togglePendingBadChannel
                                          : undefined
                                      }
                                      onRegionSelect={
                                        st.modality === "eeg" ? markPendingSegment : undefined
                                      }
                                    />
                                  ) : (
                                    <div className="muted tiny">no samples in window</div>
                                  )}
                                </div>
                              );
                              })}
                          </div>
                        </>
                      )}

                      {vizMode === "ica" && (
                        <>
                          <div className="row">
                            <button type="button" onClick={() => void loadIca()} disabled={icaBusy}>
                              {icaBusy ? "Fitting ICA…" : "Fit / refresh ICA"}
                            </button>
                            <span className="muted tiny">
                              Click IC label to toggle reject (annotation only).
                            </span>
                          </div>
                          {icaData?.components?.length ? (
                            <div className="eegplot-scroll">
                              <div className="track">
                                <div className="track-head">
                                  ICA sources · {icaData.n_components} components
                                </div>
                                <StackedStreamPlot
                                  times={icaData.components[0].timeseries_times || []}
                                  data={icaData.components.map(
                                    (c: any) => c.timeseries_preview || [],
                                  )}
                                  channels={icaData.components.map((c: any) =>
                                    c.rejected ? `IC${c.index}×` : `IC${c.index}`,
                                  )}
                                  channelStatus={icaData.components.map((c: any) =>
                                    c.rejected ? "bad" : "good",
                                  )}
                                  events={[]}
                                  start={0}
                                  duration={
                                    (icaData.components[0].timeseries_times || []).slice(-1)[0] ||
                                    1
                                  }
                                  gain={tlGain}
                                  width={720}
                                  rowH={18}
                                  onChannelClick={(label) => {
                                    const m = /IC(\d+)/.exec(label);
                                    if (m) void toggleIcaReject(Number(m[1]));
                                  }}
                                />
                              </div>
                              <div className="box">
                                <strong>Component spectra (preview)</strong>
                                <div className="ica-maps">
                                  {icaData.components.slice(0, 8).map((c: any) => {
                                    const pts = (c.spectrum_power || [])
                                      .map((p: number, i: number) => {
                                        const x = 4 + (i / Math.max(1, c.spectrum_power.length - 1)) * 100;
                                        const max = Math.max(...c.spectrum_power, 1e-12);
                                        const y = 36 - (p / max) * 32;
                                        return `${x},${y}`;
                                      })
                                      .join(" ");
                                    return (
                                      <div key={c.index} className="ica-card">
                                        <button
                                          type="button"
                                          className={c.rejected ? "active" : ""}
                                          onClick={() => void toggleIcaReject(c.index)}
                                        >
                                          IC{c.index}
                                          {c.rejected ? " rejected" : ""}
                                        </button>
                                        <svg width={110} height={40} className="spark">
                                          <polyline
                                            fill="none"
                                            stroke={c.rejected ? "#844" : "#6af"}
                                            strokeWidth={1}
                                            points={pts}
                                          />
                                        </svg>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            </div>
                          ) : (
                            <p className="muted">
                              {icaBusy ? "Fitting…" : "Click Fit ICA to compute components."}
                            </p>
                          )}
                        </>
                      )}

                      {vizMode === "erp" && (
                        <>
                          <p className="muted tiny">
                            Channel ERPs (EEGLAB Plot → Channel ERPs style): butterfly of all
                            channels, or pick one. ERPimage / topo maps not yet.
                          </p>
                          <div className="row">
                            <label>
                              event{" "}
                              <input
                                style={{ width: 100 }}
                                value={erpEvent}
                                onChange={(e) => setErpEvent(e.target.value)}
                                placeholder="(all)"
                              />
                            </label>
                            <button type="button" onClick={() => void loadErp()} disabled={erpBusy}>
                              {erpBusy ? "Computing…" : "Compute ERP"}
                            </button>
                            {erpData?.channels?.length ? (
                              <label>
                                channel{" "}
                                <select
                                  value={erpChannel}
                                  onChange={(e) => setErpChannel(e.target.value)}
                                >
                                  <option value="">(butterfly all)</option>
                                  {erpData.channels.map((c: string) => (
                                    <option key={c} value={c}>
                                      {c}
                                    </option>
                                  ))}
                                </select>
                              </label>
                            ) : null}
                            <span className="muted tiny">
                              {erpData?.status === "ok" ? `nave=${erpData.nave}` : ""}
                            </span>
                          </div>
                          {erpData?.status === "ok" && erpData.data?.length ? (
                            <div className="track">
                              <div className="track-head">
                                {erpChannel
                                  ? `ERP at ${erpChannel}`
                                  : `Channel ERPs (butterfly) · ${erpData.channels.length} ch`}
                              </div>
                              <ErpButterflyPlot
                                times={erpData.times}
                                data={erpData.data}
                                channels={erpData.channels}
                                highlight={erpChannel || undefined}
                                width={720}
                                height={300}
                              />
                            </div>
                          ) : (
                            <p className="muted">
                              {erpData?.status === "no_events"
                                ? "No events — import .set or add events, then epoch-friendly events exist."
                                : erpBusy
                                  ? "Computing…"
                                  : "Compute ERP from events."}
                            </p>
                          )}
                        </>
                      )}
                    </>
                  )}
                </section>
              )}
            </>
          )}

          <section>
            <h3>Log</h3>
            <pre className="log">{log || "—"}</pre>
          </section>
        </main>
      </div>
    </div>
  );
}

export default App;
