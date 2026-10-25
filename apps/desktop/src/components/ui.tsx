import { useEffect, useState, type ReactNode } from "react";
import type { FriendlyError } from "../lib/errors";
import type { StepStatus } from "../lib/study";

/* Small shared building blocks. Styling lives in App.css under the same class names. */

// ── Icons (inline SVG, 1.6px strokes, currentColor) ───────────────────────────
const ICON_PATHS: Record<string, ReactNode> = {
  home: (
    <>
      <path d="M3.5 10.5 12 4l8.5 6.5" />
      <path d="M5.5 9.5V20h13V9.5" />
      <path d="M10 20v-5h4v5" />
    </>
  ),
  flow: <path d="M2.5 12h3l2-5 3 10 3-12 3 9 2-2h3" />,
  learn: (
    <>
      <path d="M12 5.5C9 3.5 5.5 3.5 3 4.5v15c2.5-1 6-1 9 1 3-2 6.5-2 9-1v-15c-2.5-1-6-1-9 1Z" />
      <path d="M12 5.5v15" />
    </>
  ),
  studio: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.2" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.2" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.2" />
      <path d="M17 13.5v7M13.5 17h7" />
    </>
  ),
  chevronLeft: <path d="m14.5 6-6 6 6 6" />,
  chevronRight: <path d="m9.5 6 6 6-6 6" />,
  chevronDown: <path d="m6 9.5 6 6 6-6" />,
  refresh: (
    <>
      <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" />
      <path d="M19.5 4.5v4h-4" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" />
    </>
  ),
  moon: <path d="M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10Z" />,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  lock: (
    <>
      <rect x="5.5" y="10.5" width="13" height="9" rx="1.5" />
      <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" />
    </>
  ),
  alert: (
    <>
      <path d="M12 3.5 21.5 20h-19Z" />
      <path d="M12 10v4.5M12 17.2v.1" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5.5M12 7.8v.1" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  lab: (
    <>
      <path d="M5 20.5h9M7.5 20.5v-3h4v3" />
      <path d="m9.5 17.5 2-8 6 -3" />
      <circle cx="11.5" cy="9.5" r="1.4" />
      <path d="m17.5 6.5 2.5 1.5M17.5 6.5l1-2.5" />
    </>
  ),
  close: <path d="m6 6 12 12M18 6 6 18" />,
};

export function Icon({ name, size = 18, className = "" }: { name: keyof typeof ICON_PATHS | string; size?: number; className?: string }) {
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      focusable="false"
    >
      {ICON_PATHS[name]}
    </svg>
  );
}

// ── Connection & busy ─────────────────────────────────────────────────────────
export type Connection =
  | { state: "connecting" }
  | { state: "online"; version: string }
  | { state: "offline"; detail: string };

export function ConnectionStatus({ conn, onRetry }: { conn: Connection; onRetry: () => void }) {
  if (conn.state === "online") {
    return (
      <span className="conn conn-online" role="status" title={`Analysis backend v${conn.version} is running`}>
        <span className="conn-dot" aria-hidden />
        Connected
        <span className="conn-version">v{conn.version}</span>
      </span>
    );
  }
  if (conn.state === "connecting") {
    return (
      <span className="conn conn-connecting" role="status">
        <span className="conn-dot" aria-hidden />
        Connecting…
      </span>
    );
  }
  return (
    <span className="conn conn-offline" role="status" title={conn.detail}>
      <span className="conn-dot" aria-hidden />
      Backend offline
      <button type="button" className="btn-link" onClick={onRetry}>
        Retry
      </button>
    </span>
  );
}

export type Busy = { label: string; startedAt: number };

function useElapsed(busy: Busy | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!busy) return;
    setNow(Date.now());
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [busy]);
  return busy ? Math.max(0, Math.floor((now - busy.startedAt) / 1000)) : 0;
}

/** Indeterminate progress for one running backend operation. The backend does not
 *  stream progress, so this shows elapsed time rather than a fabricated percentage. */
export function BusyIndicator({ busy }: { busy: Busy | null }) {
  const sec = useElapsed(busy);
  if (!busy) return null;
  return (
    <span className="busy" role="status" aria-live="polite">
      <span className="spinner" aria-hidden />
      <span className="busy-label">{busy.label}</span>
      <span className="busy-time num">{sec}s</span>
    </span>
  );
}

// ── Notices ───────────────────────────────────────────────────────────────────
export type Notice =
  | ({ kind: "error" } & FriendlyError)
  | { kind: "success" | "info" | "warn"; title: string; hint?: string; detail?: string };

const NOTICE_ICON: Record<Notice["kind"], string> = { error: "alert", warn: "alert", success: "check", info: "info" };

export function NoticeBar({ notice, onDismiss }: { notice: Notice | null; onDismiss: () => void }) {
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [notice]);
  if (!notice) return null;
  return (
    <div className={`notice notice-${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>
      <Icon name={NOTICE_ICON[notice.kind]} size={18} className="notice-icon" />
      <div className="notice-body">
        <div className="notice-title">{notice.title}</div>
        {notice.hint && <div className="notice-hint">{notice.hint}</div>}
        {notice.detail && open && <pre className="notice-detail">{notice.detail}</pre>}
      </div>
      <div className="notice-actions">
        {notice.detail && (
          <button type="button" className="btn-link" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? "Hide technical details" : "Technical details"}
          </button>
        )}
        <button type="button" className="btn-icon" aria-label="Dismiss message" onClick={onDismiss}>
          <Icon name="close" size={16} />
        </button>
      </div>
    </div>
  );
}

// ── Stepper ───────────────────────────────────────────────────────────────────
export type StepDef = { id: string; label: string; status: StepStatus; hint?: string };

export function Stepper({
  steps,
  current,
  running,
  onSelect,
  label,
}: {
  steps: StepDef[];
  current: string;
  running?: boolean;
  onSelect: (id: string) => void;
  label: string;
}) {
  return (
    <nav className="stepper" aria-label={label}>
      <ol>
        {steps.map((s, i) => {
          const active = s.id === current;
          const stateText =
            active && running ? "running" : s.status === "done" ? "completed" : s.status === "unavailable" ? "not available yet" : "available";
          return (
            <li key={s.id} className={`step step-${s.status} ${active ? "active" : ""} ${active && running ? "running" : ""}`}>
              <button
                type="button"
                onClick={() => onSelect(s.id)}
                aria-current={active ? "step" : undefined}
                title={s.hint ? `${s.label}: ${s.hint}` : s.label}
              >
                <span className="step-n" aria-hidden>
                  {active && running ? (
                    <span className="spinner spinner-sm" />
                  ) : s.status === "done" ? (
                    <Icon name="check" size={13} />
                  ) : s.status === "unavailable" ? (
                    <Icon name="lock" size={12} />
                  ) : (
                    i + 1
                  )}
                </span>
                <span className="step-label">{s.label}</span>
                <span className="sr-only">, {stateText}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// ── Layout primitives ─────────────────────────────────────────────────────────
export function EmptyState({
  title,
  children,
  actions,
  icon,
}: {
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  icon?: string;
}) {
  return (
    <div className="empty">
      {icon && <Icon name={icon} size={22} className="empty-icon" />}
      <div className="empty-main">
        <div className="empty-title">{title}</div>
        {children && <div className="empty-body">{children}</div>}
        {actions && <div className="empty-actions">{actions}</div>}
      </div>
    </div>
  );
}

export function Card({
  title,
  description,
  actions,
  children,
  className = "",
  id,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section className={`card ${className}`} id={id}>
      <header className="card-head">
        <div className="card-heading">
          <h3 className="card-title">{title}</h3>
          {description && <p className="card-desc">{description}</p>}
        </div>
        {actions && <div className="card-actions">{actions}</div>}
      </header>
      {children && <div className="card-body">{children}</div>}
    </section>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
  wide,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <label className={`field ${wide ? "field-wide" : ""} ${error ? "has-error" : ""}`}>
      <span className="field-label">{label}</span>
      {children}
      {error ? (
        <span className="field-error" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span className="field-hint">{hint}</span>
      ) : null}
    </label>
  );
}

/** Explains why an adjacent action is unavailable. */
export function Reason({ text }: { text?: string | null }) {
  if (!text) return null;
  return (
    <p className="reason">
      <Icon name="info" size={15} />
      <span>{text}</span>
    </p>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "ok" | "warn" | "danger" | "accent"; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

/** A checklist of prerequisites, each verified from backend data. */
export function Checklist({ items }: { items: Array<{ label: string; ok: boolean; detail?: string }> }) {
  return (
    <ul className="checklist">
      {items.map((it) => (
        <li key={it.label} className={it.ok ? "ok" : "todo"}>
          <span className="check-mark" aria-hidden>
            {it.ok ? <Icon name="check" size={13} /> : null}
          </span>
          <span className="check-label">
            {it.label}
            <span className="sr-only">{it.ok ? " — done" : " — not done"}</span>
          </span>
          {it.detail && <span className="check-detail">{it.detail}</span>}
        </li>
      ))}
    </ul>
  );
}

/** Raw backend output, collapsed by default. */
export function RawResult({ value, label = "Raw backend response" }: { value: unknown; label?: string }) {
  if (value == null) return null;
  return (
    <details className="raw">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

// ── Activity ──────────────────────────────────────────────────────────────────
export type LogEntry = { id: number; at: number; level: "info" | "error" | "success"; text: string; detail?: string };

export function ActivityLog({
  entries,
  open,
  busy,
  onToggle,
  onClear,
}: {
  entries: LogEntry[];
  open: boolean;
  busy: Busy | null;
  onToggle: () => void;
  onClear: () => void;
}) {
  const [filter, setFilter] = useState<"all" | "error">("all");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const sec = useElapsed(busy);
  const errors = entries.filter((e) => e.level === "error").length;
  const shown = filter === "error" ? entries.filter((e) => e.level === "error") : entries;
  const last = entries[0];
  return (
    <section className={`activity ${open ? "open" : ""}`} aria-label="Activity log">
      <div className="activity-bar">
        <button type="button" className="activity-toggle" onClick={onToggle} aria-expanded={open} aria-controls="activity-list">
          <Icon name={open ? "chevronDown" : "chevronRight"} size={14} />
          <span className="activity-title">Activity</span>
          {entries.length > 0 && <span className="activity-count num">{entries.length}</span>}
          {errors > 0 && <Badge tone="danger">{errors} failed</Badge>}
          {busy ? (
            <span className="activity-last lvl-running">
              <span className="spinner spinner-sm" aria-hidden /> {busy.label} · {sec}s
            </span>
          ) : (
            !open && last && (
              <span className={`activity-last lvl-${last.level}`}>
                {new Date(last.at).toLocaleTimeString()} · {last.text}
              </span>
            )
          )}
        </button>
        {open && (
          <div className="activity-tools">
            <div className="seg" role="group" aria-label="Filter activity">
              <button type="button" className={filter === "all" ? "on" : ""} aria-pressed={filter === "all"} onClick={() => setFilter("all")}>
                All
              </button>
              <button type="button" className={filter === "error" ? "on" : ""} aria-pressed={filter === "error"} onClick={() => setFilter("error")}>
                Failures{errors ? ` (${errors})` : ""}
              </button>
            </div>
            <button
              type="button"
              className="btn btn-sm"
              disabled={!entries.length}
              onClick={() => {
                const text = entries
                  .map((e) => `${new Date(e.at).toISOString()} [${e.level}] ${e.text}${e.detail ? `\n  ${e.detail}` : ""}`)
                  .join("\n");
                void navigator.clipboard?.writeText(text).then(() => {
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 1500);
                });
              }}
            >
              {copied ? "Copied" : "Copy log"}
            </button>
            <button type="button" className="btn btn-sm" onClick={onClear} disabled={!entries.length}>
              Clear
            </button>
          </div>
        )}
      </div>
      {open && (
        <ol className="activity-list" id="activity-list">
          {shown.length === 0 && (
            <li className="activity-empty">{filter === "error" ? "No failures this session." : "Operations you run will be listed here."}</li>
          )}
          {shown.map((e) => (
            <li key={e.id} className={`lvl-${e.level}`}>
              <span className={`activity-dot lvl-${e.level}`} aria-hidden />
              <span className="activity-time num">{new Date(e.at).toLocaleTimeString()}</span>
              <span className="activity-text">
                <span>
                  {e.level === "error" && <span className="sr-only">Failed: </span>}
                  {e.text}
                </span>
                {e.detail && (
                  <>
                    <button
                      type="button"
                      className="btn-link activity-more"
                      aria-expanded={expanded === e.id}
                      onClick={() => setExpanded((x) => (x === e.id ? null : e.id))}
                    >
                      {expanded === e.id ? "Hide details" : "Details"}
                    </button>
                    {expanded === e.id && <pre className="activity-detail">{e.detail}</pre>}
                  </>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
