import { Badge, EmptyState, Field, RawResult } from "../../components/ui";
import { StackedStreamPlot, ErpButterflyPlot, ErpImagePlot } from "../../components/plots";
import { fmtDate } from "../../lib/format";
import { CLEAN_Z_THRESH, EPOCH_WINDOW, ICA_COMPONENTS } from "../../lib/constants";
import { useElementWidth } from "../../lib/useElementWidth";
import { NeedRecording } from "./RecordingPicker";
import type { VizMode } from "../../types";
import type { StudySession } from "../../hooks/useStudySession";
import type { StudyLists } from "../../hooks/useStudyLists";
import type { Results } from "../../hooks/useResults";
import type { Inspector } from "../../hooks/useInspector";
import type { Preprocess } from "../../hooks/usePreprocess";

/** NeuroFlow → Inspect: review the signal, mark bad channels/segments, and look at ICA, ERPs, and epochs. */
export function InspectStage({ session, lists, res, insp, pre, idle, onImport }: {
  session: StudySession;
  lists: StudyLists;
  res: Results;
  insp: Inspector;
  pre: Preprocess;
  idle: boolean;
  onImport: () => void;
}) {
  const { selectedRecId, recRows } = session;
  const { recEpochsets } = lists;
  const { runFlow } = res;
  const {
    tlStart,
    setTlStart,
    tlDur,
    setTlDur,
    tlGain,
    setTlGain,
    tlBusy,
    tlError,
    setTlRev,
    timeline,
    vizMode,
    setVizMode,
    pendingSegments,
    pendingBadChannels,
    pendingUnrejectAnnIds,
    erpChannel,
    setErpChannel,
    icaData,
    erpData,
    erpEvent,
    setErpEvent,
    epochSet,
    pendingEpochReject,
    setPendingEpochReject,
    marksPending,
    clearMarks,
    toggleUnreject,
    nudgeTime,
    togglePendingBadChannel,
    markPendingSegment,
    applyRejectMarks,
    loadIca,
    toggleIcaReject,
    loadErp,
    applyIcaRemovals,
    runCleanContinuous,
    loadEpochSet,
    togglePendingEpoch,
    applyEpochReject,
  } = insp;
  const { createEpochs } = pre;
  const [plotRef, plotWidth] = useElementWidth<HTMLDivElement>(720);
  // Plots draw in pixel units; fit them to the container (minus the track border).
  const plotW = Math.max(480, plotWidth - 2);
  return !selectedRecId ? (
    <NeedRecording what="Inspection" recordingCount={recRows.length} onImport={onImport} />
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
              onClick={clearMarks}
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
                          onArtifactClick={st.modality === "eeg" ? toggleUnreject : undefined}
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
}
