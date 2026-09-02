import { useCallback, useEffect, useRef, useState } from "react";

import "./SignalCanvas.css";

export type ChannelStatus = "good" | "bad" | "unknown";

export type SignalEvent = {
  id: string;
  name: string;
  timestamp: number;
  end?: number;
  color?: string;
  artifact?: boolean;
};

export type Span = { start: number; end: number };

export type SignalCanvasProps = {
  /** Channel-major sample matrix for the visible window. */
  data: Float32Array[] | number[][];
  channels: string[];
  channelStatus?: ChannelStatus[];
  /** Absolute start time of data[0][0], in seconds. */
  windowStart: number;
  windowDuration: number;
  sampleRate: number;
  /** Microvolts represented by one channel row. Lower = taller traces. */
  gain: number;
  events?: SignalEvent[];
  rejectedSpans?: Span[];
  /** Spans marked but not yet committed. Drawn distinctly from rejected. */
  pendingSpans?: Span[];
  readOnly?: boolean;
  onToggleChannel?: (channel: string, index: number) => void;
  onSelectSpan?: (span: Span) => void;
  onScrub?: (nextStart: number) => void;
};

const PAD_L = 46;
const PAD_R = 12;
const PAD_T = 8;
const PAD_B = 18;

/** Read a CSS custom property so the canvas follows the active theme. */
function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export function SignalCanvas({
  data,
  channels,
  channelStatus,
  windowStart,
  windowDuration,
  sampleRate,
  gain,
  events = [],
  rejectedSpans = [],
  pendingSpans = [],
  readOnly = false,
  onToggleChannel,
  onSelectSpan,
  onScrub,
}: SignalCanvasProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sizeRef = useRef({ w: 0, h: 0 });
  const dragRef = useRef<{ x0: number; x1: number } | null>(null);

  const [hover, setHover] = useState<number | null>(null);
  const [readout, setReadout] = useState<string | null>(null);

  const nChannels = channels.length;

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { w, h } = sizeRef.current;
    if (w === 0 || h === 0) return;

    const plotW = w - PAD_L - PAD_R;
    const rowH = (h - PAD_T - PAD_B) / nChannels;
    const t1 = windowStart + windowDuration;
    const t2x = (t: number) => PAD_L + ((t - windowStart) / windowDuration) * plotW;

    const C = {
      ink: cssVar("--ink", "#080b11"),
      grid: cssVar("--line-soft", "#171e2c"),
      gridMajor: cssVar("--line", "#202839"),
      trace: cssVar("--trace", "#7fa8ff"),
      flagged: cssVar("--flagged", "#ff6b6b"),
      dim: cssVar("--dimmer", "#4a5468"),
      text: cssVar("--text", "#d9e1f0"),
    };

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = C.ink;
    ctx.fillRect(0, 0, w, h);

    // --- time grid -------------------------------------------------------
    ctx.lineWidth = 1;
    for (let s = Math.ceil(windowStart); s < t1; s += 1) {
      const x = Math.round(t2x(s)) + 0.5;
      ctx.strokeStyle = s % 5 === 0 ? C.gridMajor : C.grid;
      ctx.beginPath();
      ctx.moveTo(x, PAD_T);
      ctx.lineTo(x, h - PAD_B);
      ctx.stroke();
      if (s % 5 === 0) {
        ctx.fillStyle = C.dim;
        ctx.font = "10px var(--mono), monospace";
        ctx.textAlign = "center";
        ctx.fillText(`${s}s`, x, h - 6);
      }
    }

    // --- committed rejections -------------------------------------------
    for (const span of rejectedSpans) {
      if (span.end < windowStart || span.start > t1) continue;
      const xa = Math.max(PAD_L, t2x(span.start));
      const xb = Math.min(w - PAD_R, t2x(span.end));
      ctx.fillStyle = "rgba(255,107,107,.10)";
      ctx.fillRect(xa, PAD_T, xb - xa, h - PAD_T - PAD_B);
      ctx.strokeStyle = "rgba(255,107,107,.42)";
      ctx.beginPath();
      ctx.moveTo(xa + 0.5, PAD_T);
      ctx.lineTo(xa + 0.5, h - PAD_B);
      ctx.moveTo(xb - 0.5, PAD_T);
      ctx.lineTo(xb - 0.5, h - PAD_B);
      ctx.stroke();
    }

    // --- pending marks (hatched so they read as uncommitted) -------------
    for (const span of pendingSpans) {
      if (span.end < windowStart || span.start > t1) continue;
      const xa = Math.max(PAD_L, t2x(span.start));
      const xb = Math.min(w - PAD_R, t2x(span.end));
      ctx.save();
      ctx.beginPath();
      ctx.rect(xa, PAD_T, xb - xa, h - PAD_T - PAD_B);
      ctx.clip();
      ctx.strokeStyle = "rgba(240,180,41,.35)";
      ctx.lineWidth = 1;
      for (let x = xa - (h - PAD_T - PAD_B); x < xb; x += 7) {
        ctx.beginPath();
        ctx.moveTo(x, h - PAD_B);
        ctx.lineTo(x + (h - PAD_T - PAD_B), PAD_T);
        ctx.stroke();
      }
      ctx.restore();
    }

    // --- events ----------------------------------------------------------
    for (const ev of events) {
      if (ev.timestamp < windowStart || ev.timestamp > t1) continue;
      const x = Math.round(t2x(ev.timestamp)) + 0.5;
      const color = ev.color ?? cssVar("--event", "#f0b429");
      ctx.strokeStyle = color;
      ctx.globalAlpha = 0.5;
      ctx.beginPath();
      ctx.moveTo(x, PAD_T);
      ctx.lineTo(x, h - PAD_B);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = color;
      ctx.fillRect(x - 2.5, PAD_T, 5, 3);
    }

    // --- traces ----------------------------------------------------------
    const nSamples = data[0]?.length ?? 0;
    if (nSamples > 1) {
      const px = plotW / (nSamples - 1);
      // Decimate to roughly two samples per device pixel. Above this the
      // extra points cost time and change nothing on screen.
      const stride = Math.max(1, Math.floor(1 / px / 2));
      const amp = (rowH * 0.44) / gain;

      for (let c = 0; c < nChannels; c += 1) {
        const row = data[c];
        if (!row) continue;
        const yc = PAD_T + rowH * c + rowH / 2;
        const isBad = channelStatus?.[c] === "bad";

        ctx.beginPath();
        for (let i = 0; i < nSamples; i += stride) {
          const x = PAD_L + i * px;
          let y = yc - row[i] * amp;
          if (y < PAD_T) y = PAD_T;
          else if (y > h - PAD_B) y = h - PAD_B;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = isBad ? C.flagged : C.trace;
        ctx.globalAlpha = isBad ? 0.55 : hover !== null && hover !== c ? 0.45 : 0.92;
        ctx.lineWidth = hover === c ? 1.35 : 1;
        ctx.stroke();
        ctx.globalAlpha = 1;

        ctx.font = "10.5px var(--mono), monospace";
        ctx.textAlign = "right";
        ctx.textBaseline = "middle";
        ctx.fillStyle = isBad ? C.flagged : hover === c ? C.text : C.dim;
        ctx.fillText(channels[c], PAD_L - 9, yc);
        if (isBad) {
          ctx.fillStyle = C.flagged;
          ctx.fillRect(PAD_L - 5, yc - 4, 2, 8);
        }
      }
      ctx.textBaseline = "alphabetic";
    }

    // --- live drag -------------------------------------------------------
    const drag = dragRef.current;
    if (drag) {
      const xa = Math.min(drag.x0, drag.x1);
      const xb = Math.max(drag.x0, drag.x1);
      ctx.fillStyle = "rgba(127,168,255,.12)";
      ctx.fillRect(xa, PAD_T, xb - xa, h - PAD_T - PAD_B);
      ctx.strokeStyle = "rgba(127,168,255,.6)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(xa + 0.5, PAD_T);
      ctx.lineTo(xa + 0.5, h - PAD_B);
      ctx.moveTo(xb - 0.5, PAD_T);
      ctx.lineTo(xb - 0.5, h - PAD_B);
      ctx.stroke();
    }

    // --- amplitude scale bar --------------------------------------------
    const sbx = PAD_L + 7;
    const sby = h - PAD_B - 10;
    const sbh = rowH * 0.44;
    ctx.strokeStyle = C.gridMajor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(sbx, sby);
    ctx.lineTo(sbx, sby - sbh);
    ctx.moveTo(sbx - 3, sby);
    ctx.lineTo(sbx + 3, sby);
    ctx.moveTo(sbx - 3, sby - sbh);
    ctx.lineTo(sbx + 3, sby - sbh);
    ctx.stroke();
    ctx.fillStyle = C.dim;
    ctx.font = "9.5px var(--mono), monospace";
    ctx.textAlign = "left";
    ctx.fillText(`${gain}µV`, sbx + 6, sby - sbh / 2 + 3);
  }, [
    data,
    channels,
    channelStatus,
    windowStart,
    windowDuration,
    gain,
    events,
    rejectedSpans,
    pendingSpans,
    hover,
    nChannels,
  ]);

  // Redraw on any input change.
  useEffect(() => {
    draw();
  }, [draw]);

  // Track element size and device pixel ratio for crisp lines.
  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = wrap.getBoundingClientRect();
      sizeRef.current = { w: rect.width, h: rect.height };
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
      const ctx = canvas.getContext("2d");
      ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    };

    const ro = new ResizeObserver(resize);
    ro.observe(wrap);
    resize();
    return () => ro.disconnect();
  }, [draw]);

  const rowHeight = () => (sizeRef.current.h - PAD_T - PAD_B) / nChannels;
  const x2t = (x: number) =>
    windowStart +
    ((x - PAD_L) / (sizeRef.current.w - PAD_L - PAD_R)) * windowDuration;

  const onPointerDown = (e: React.PointerEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (x < PAD_L) {
      const c = Math.floor((y - PAD_T) / rowHeight());
      if (!readOnly && c >= 0 && c < nChannels) onToggleChannel?.(channels[c], c);
      return;
    }
    if (readOnly) return;
    dragRef.current = { x0: x, x1: x };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (dragRef.current) {
      dragRef.current.x1 = Math.max(
        PAD_L,
        Math.min(sizeRef.current.w - PAD_R, x),
      );
      draw();
      return;
    }

    const c = Math.floor((y - PAD_T) / rowHeight());
    const next = x >= PAD_L && c >= 0 && c < nChannels ? c : null;
    if (next !== hover) setHover(next);

    if (next !== null) {
      const t = x2t(x);
      const i = Math.round((t - windowStart) * sampleRate);
      const v = data[next]?.[i];
      setReadout(
        v === undefined
          ? null
          : `${channels[next]}  ${t.toFixed(3)}s  ${v.toFixed(1)} µV`,
      );
    } else {
      setReadout(null);
    }
  };

  const onPointerUp = () => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (!drag) return;
    const a = x2t(Math.min(drag.x0, drag.x1));
    const b = x2t(Math.max(drag.x0, drag.x1));
    if (b - a > 0.04) onSelectSpan?.({ start: a, end: b });
    draw();
  };

  const onWheel = (e: React.WheelEvent) => {
    if (!onScrub) return;
    const delta = e.deltaX || e.deltaY;
    onScrub(windowStart + (delta * windowDuration) / 600);
  };

  return (
    <div
      ref={wrapRef}
      className="signal-canvas"
      data-readonly={readOnly || undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={() => {
        setHover(null);
        setReadout(null);
      }}
      onWheel={onWheel}
    >
      <canvas ref={canvasRef} />
      {readout && (
        <div className="signal-canvas__readout num" role="status">
          {readout}
        </div>
      )}
    </div>
  );
}
