import { useEffect, useState } from "react";
import { useOperations } from "./hooks/useOperations";
import { useStudySession } from "./hooks/useStudySession";
import { useStudyLists } from "./hooks/useStudyLists";
import { useResults } from "./hooks/useResults";
import { useInspector } from "./hooks/useInspector";
import { usePreprocess } from "./hooks/usePreprocess";
import { useNeuroStudio } from "./hooks/useNeuroStudio";
import { useImport } from "./hooks/useImport";
import { useStudyForms } from "./hooks/useStudyForms";
import { usePreferences } from "./hooks/usePreferences";
import { confirmDiscardMarks } from "./lib/dialogs";
import {
  flowStepStates,
  stageNeighbors,
  studioStepStates,
  type FlowStage,
  type NavState,
  type Page,
  type StudioStage,
} from "./lib/workflow";
import { ActivityLog, NoticeBar } from "./components/ui";
import { ModuleHeader, NavRail, StageFooter, TopBar } from "./components/layout";
import { NewStudyForm } from "./components/NewStudyForm";
import { HomePage } from "./pages/home/HomePage";
import { NoStudy } from "./pages/NoStudy";
import { RecordingPicker } from "./pages/flow/RecordingPicker";
import { ImportStage } from "./pages/flow/ImportStage";
import { InspectStage } from "./pages/flow/InspectStage";
import { PreprocessStage } from "./pages/flow/PreprocessStage";
import { AnalyzeStage } from "./pages/flow/AnalyzeStage";
import { DatasetStage } from "./pages/studio/DatasetStage";
import { TrainStage } from "./pages/studio/TrainStage";
import { ExportStage } from "./pages/studio/ExportStage";
import "./App.css";

/** Composition root: owns navigation, wires the state hooks together, and lays out the pages.
 *  Workflow state lives in hooks/ so it survives moving between pages and steps. */
function App() {
  // ── State ─────────────────────────────────────────────────────────────────
  const ops = useOperations();
  const session = useStudySession(ops);
  const [page, setPage] = useState<Page>("home");
  const [flowStage, setFlowStage] = useState<FlowStage>("recording");
  const [studioStage, setStudioStage] = useState<StudioStage>("data");
  const lists = useStudyLists(ops, session, page);
  const res = useResults(ops, session);
  const insp = useInspector(ops, session, { page, flowStage });
  const pre = usePreprocess(ops, session, lists, res.runFlow);
  const studio = useNeuroStudio(ops, session, lists, res.setResult);
  const imp = useImport(ops, session);
  const confirmDiscardPending = () => confirmDiscardMarks(insp.pendingCount);
  const forms = useStudyForms(ops, session, confirmDiscardPending);
  const prefs = usePreferences();
  const [logOpen, setLogOpen] = useState(false);

  const { busy, setNotice } = ops;
  const { online, studies, selectedId, selectedRecId, setSelectedRecId, recRows, selectedRec } = session;
  const idle = online && !busy;

  // A new screen starts at the top, and a confirmation about one screen doesn't linger on the next.
  useEffect(() => {
    document.getElementById("main")?.scrollTo({ top: 0 });
    setNotice((n) => (n && (n.kind === "success" || n.kind === "info") ? null : n));
  }, [page, flowStage, studioStage, setNotice]);

  // ── Navigation ────────────────────────────────────────────────────────────
  function go(to: NavState) {
    setPage(to.page);
    setFlowStage(to.flowStage);
    setStudioStage(to.studioStage);
  }

  function goPage(p: Page) {
    if (p === "flow" && page !== "flow" && selectedRecId && flowStage === "recording") setFlowStage("inspect");
    setPage(p);
  }

  function openFlow(stage: FlowStage) {
    setPage("flow");
    setFlowStage(stage);
  }

  function openStudio(stage: StudioStage) {
    setPage("studio");
    setStudioStage(stage);
  }

  function startNewStudy() {
    forms.openNewStudy();
    setPage("home");
  }

  // Switching study or recording discards unapplied marks, so ask first.
  async function selectStudy(id: string) {
    if (!id || id === selectedId) return;
    if (!(await confirmDiscardPending())) return;
    await session.switchStudy(id);
  }

  async function openRecording(id: string, stage: FlowStage = "inspect") {
    if (id !== selectedRecId && !(await confirmDiscardPending())) return;
    setSelectedRecId(id);
    openFlow(stage);
  }

  async function changeRecording(id: string) {
    if (id === selectedRecId) return;
    if (!(await confirmDiscardPending())) return;
    setSelectedRecId(id || null);
  }

  // ── Step indicators (derived only from saved backend data) ────────────────
  const flowSteps = flowStepStates({
    studySelected: !!selectedId,
    recordingSelected: !!selectedRec,
    recordingCount: recRows.length,
    recordingEpochsets: lists.recEpochsets.length,
    recordingResults: lists.featuresets.length + lists.analyses.length,
  });
  const studioSteps = studioStepStates({
    studySelected: !!selectedId,
    epochsets: lists.epochsets.length,
    hasAnySplit: studio.hasAnySplit,
    trainedExperiments: studio.trainedExperiments.length,
  });
  const inModule = page === "flow" || page === "studio";
  const neighbors = stageNeighbors({ page, flowStage, studioStage });

  // ── Layout ────────────────────────────────────────────────────────────────
  const newStudyForm = <NewStudyForm forms={forms} idle={idle} online={online} canCancel={studies.length > 0} />;
  const toImport = () => setFlowStage("recording");

  return (
    <div className={`app page-${page} ${prefs.sidebarOpen ? "rail-open" : ""}`}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <NavRail page={page} sidebarOpen={prefs.sidebarOpen} onNavigate={goPage} onToggleSidebar={prefs.toggleSidebar} />

      <div className="shell">
        <TopBar
          session={session}
          busy={busy}
          pendingCount={insp.pendingCount}
          theme={prefs.theme}
          onToggleTheme={prefs.toggleTheme}
          onSelectStudy={(id) => void selectStudy(id)}
          onShowRecording={() => openFlow(flowStage === "recording" ? "inspect" : flowStage)}
        />

        <NoticeBar notice={ops.notice} onDismiss={() => setNotice(null)} />

        {inModule && (
          <ModuleHeader
            page={page}
            flowStage={flowStage}
            studioStage={studioStage}
            flowSteps={flowSteps}
            studioSteps={studioSteps}
            studySelected={!!selectedId}
            running={!!busy}
            onFlowStage={setFlowStage}
            onStudioStage={setStudioStage}
          />
        )}

        <main
          id="main"
          tabIndex={-1}
          className={`content ${page === "flow" && flowStage === "inspect" && selectedId ? "content-wide" : ""}`}
        >
          {page === "home" && (
            <HomePage
              ops={ops}
              session={session}
              lists={lists}
              forms={forms}
              idle={idle}
              newStudyForm={newStudyForm}
              selectStudy={selectStudy}
              openRecording={openRecording}
              openImport={() => openFlow("recording")}
              startNewStudy={startNewStudy}
              openStudio={openStudio}
            />
          )}
          {inModule && !selectedId && (
            <NoStudy
              key={page}
              module={page === "flow" ? "NeuroFlow" : "NeuroStudio"}
              hasStudies={studies.length > 0}
              newStudyForm={newStudyForm}
              goHome={() => setPage("home")}
            />
          )}
          {page === "flow" && selectedId && (
            <>
              {flowStage !== "recording" && <RecordingPicker session={session} onChange={changeRecording} />}
              {flowStage === "recording" && <ImportStage session={session} imp={imp} idle={idle} />}
              {flowStage === "inspect" && (
                <InspectStage session={session} lists={lists} res={res} insp={insp} pre={pre} idle={idle} onImport={toImport} />
              )}
              {flowStage === "plan" && (
                <PreprocessStage session={session} lists={lists} res={res} pre={pre} idle={idle} onImport={toImport} />
              )}
              {flowStage === "review" && <AnalyzeStage session={session} lists={lists} res={res} idle={idle} onImport={toImport} />}
            </>
          )}
          {page === "studio" && selectedId && (
            <>
              {studioStage === "data" && <DatasetStage session={session} lists={lists} studio={studio} idle={idle} openFlow={openFlow} />}
              {studioStage === "train" && <TrainStage lists={lists} res={res} studio={studio} idle={idle} />}
              {studioStage === "export" && <ExportStage res={res} studio={studio} idle={idle} />}
            </>
          )}
        </main>

        {inModule && selectedId && (
          <StageFooter
            steps={page === "flow" ? flowSteps : studioSteps}
            current={page === "flow" ? flowStage : studioStage}
            prevLabel={neighbors.prev.label}
            nextLabel={neighbors.next?.label ?? null}
            nextReadyWhenLast={page === "flow"}
            onPrev={() => go(neighbors.prev.to)}
            onNext={() => neighbors.next && go(neighbors.next.to)}
          />
        )}

        <ActivityLog
          entries={ops.logEntries}
          open={logOpen}
          busy={busy}
          onToggle={() => setLogOpen((v) => !v)}
          onClear={ops.clearLog}
        />
      </div>
    </div>
  );
}

export default App;
