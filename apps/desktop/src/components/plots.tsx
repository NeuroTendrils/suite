import { useRef, useState } from "react";

/* SVG plots for EEG signal, ICA sources, and ERPs. Pure rendering from backend arrays; no IPC. */

const EVENT_COLORS = ["#3dcf6a", "#e85d5d", "#5db0e8", "#e8c55d", "#c77dff"];

/** Interactive stacked plot: click channel label = toggle bad; drag = reject segment. */
export function StackedStreamPlot({
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
export function ErpImagePlot({
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

export function ErpButterflyPlot({
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
