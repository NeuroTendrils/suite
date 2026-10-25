import { FLOW_STAGES, NAV_ITEMS, STUDIO_STAGES, type FlowStage, type Page, type StudioStage } from "../lib/workflow";
import { recordingLabel } from "../lib/study";
import type { ThemeName } from "../lib/storage";
import type { StudySession } from "../hooks/useStudySession";
import type { RobotSession } from "../hooks/useRobot";
import { Badge, BusyIndicator, ConnectionStatus, Icon, Stepper, type Busy, type StepDef } from "./ui";

/* Application chrome: navigation rail, top bar, module header with the step indicator, and the step footer. */

export function NavRail({
  page,
  sidebarOpen,
  onNavigate,
  onToggleSidebar,
}: {
  page: Page;
  sidebarOpen: boolean;
  onNavigate: (page: Page) => void;
  onToggleSidebar: () => void;
}) {
  return (
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
          onClick={() => onNavigate(item.id)}
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
        onClick={onToggleSidebar}
      >
        <span className="rail-icon">
          <Icon name={sidebarOpen ? "chevronLeft" : "chevronRight"} size={17} />
        </span>
        {sidebarOpen && <span className="rail-label">Collapse</span>}
      </button>
    </nav>
  );
}

export function TopBar({
  learning = false,
  session,
  busy,
  pendingCount,
  theme,
  onToggleTheme,
  onSelectStudy,
  onShowRecording,
  robot,
}: {
  learning?: boolean;
  session: StudySession;
  busy: Busy | null;
  /** Unapplied rejection marks on the active recording. */
  pendingCount: number;
  theme: ThemeName;
  onToggleTheme: () => void;
  onSelectStudy: (id: string) => void;
  onShowRecording: () => void;
  /** Shows an emergency stop on every page while an arm is connected. */
  robot?: RobotSession;
}) {
  const { studies, studiesLoaded, selectedId, selectedRow, conn, refresh } = session;
  return (
    <header className="topbar">
      {learning ? (
        <span className="topbar-study"><Icon name="learn" /> NeuroLearn</span>
      ) : studies.length ? (
        <label className="topbar-study" title="The active study. NeuroFlow and NeuroStudio work on this study.">
          <span className="topbar-key">Study</span>
          <select value={selectedId ?? ""} disabled={!!busy} onChange={(e) => onSelectStudy(e.target.value)} aria-label="Active study">
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
      {!learning && selectedRow && (
        <button
          type="button"
          className="topbar-rec"
          title={`Active recording ${selectedRow.rec.id}. Click to inspect it.`}
          onClick={onShowRecording}
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
        {robot?.status?.state === "connected" && (
          <button type="button" className="btn btn-sm robot-estop robot-estop-top" onClick={() => void robot.estop()}>
            E-STOP arm
          </button>
        )}
        <BusyIndicator busy={busy} />
        {!learning && <ConnectionStatus conn={conn} onRetry={() => void refresh()} />}
        {!learning && <button
          type="button"
          className="btn-icon"
          title="Reload studies and status from the backend"
          aria-label="Reload from backend"
          onClick={() => void refresh()}
          disabled={!!busy}
        >
          <Icon name="refresh" size={17} />
        </button>}
        <button
          type="button"
          className="btn-icon"
          title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          onClick={onToggleTheme}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} size={17} />
        </button>
      </div>
    </header>
  );
}

/** NeuroFlow / NeuroStudio header: module identity, the current step's title, and the step indicator. */
export function ModuleHeader({
  page,
  flowStage,
  studioStage,
  flowSteps,
  studioSteps,
  studySelected,
  running,
  onFlowStage,
  onStudioStage,
}: {
  page: "flow" | "studio";
  flowStage: FlowStage;
  studioStage: StudioStage;
  flowSteps: StepDef[];
  studioSteps: StepDef[];
  studySelected: boolean;
  running: boolean;
  onFlowStage: (stage: FlowStage) => void;
  onStudioStage: (stage: StudioStage) => void;
}) {
  const flowMeta = FLOW_STAGES.find((s) => s.id === flowStage) ?? FLOW_STAGES[0];
  const studioMeta = STUDIO_STAGES.find((s) => s.id === studioStage) ?? STUDIO_STAGES[0];
  return (
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
          {studySelected && <p className="page-desc">{page === "flow" ? flowMeta.description : studioMeta.description}</p>}
        </div>
        {page === "flow" ? (
          <Stepper
            steps={flowSteps}
            current={flowStage}
            running={running}
            onSelect={(id) => onFlowStage(id as FlowStage)}
            label="NeuroFlow steps"
          />
        ) : (
          <Stepper
            steps={studioSteps}
            current={studioStage}
            running={running}
            onSelect={(id) => onStudioStage(id as StudioStage)}
            label="NeuroStudio steps"
          />
        )}
      </div>
    </div>
  );
}

/** Back / position / Next for the current module's steps. */
export function StageFooter({
  steps,
  current,
  prevLabel,
  nextLabel,
  nextReadyWhenLast,
  onPrev,
  onNext,
}: {
  steps: StepDef[];
  current: string;
  prevLabel: string;
  /** null when there is nowhere further to go. */
  nextLabel: string | null;
  /** Highlight Next even on the last step (NeuroFlow's last step leads on to NeuroStudio). */
  nextReadyWhenLast: boolean;
  onPrev: () => void;
  onNext: () => void;
}) {
  const stepIndex = steps.findIndex((s) => s.id === current);
  const nextStepDef = steps[stepIndex + 1];
  const nextReady = nextReadyWhenLast && !nextStepDef ? true : nextStepDef?.status !== "unavailable";
  return (
    <footer className="stage-footer">
      <button type="button" className="btn" onClick={onPrev}>
        <Icon name="chevronLeft" size={15} /> {prevLabel}
      </button>
      <span className="stage-pos">
        Step {stepIndex + 1} of {steps.length}
        {nextStepDef?.status === "unavailable" && nextStepDef.hint ? ` · Next: ${nextStepDef.hint}` : ""}
      </span>
      {nextLabel && (
        <button type="button" className={`btn ${nextReady ? "btn-primary" : ""}`} onClick={onNext}>
          {nextLabel} <Icon name="chevronRight" size={15} />
        </button>
      )}
    </footer>
  );
}
