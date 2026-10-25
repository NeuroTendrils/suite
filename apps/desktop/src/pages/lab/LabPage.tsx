import { useEffect, useMemo, useRef, useState } from "react";
import { Badge, Card, Field } from "../../components/ui";
import { exec } from "../../lib/backend";
import { suiteCall } from "../../ipc";
import { describeError } from "../../lib/errors";
import { fmtDate, shortId } from "../../lib/format";
import { isTrained } from "../../lib/study";
import {
  gate,
  MAX_THRESHOLD,
  MIN_THRESHOLD,
  SAFE_COMMANDS,
  SOURCE_LABEL,
  type EegSource,
  type Mapping,
  type SafeCommand,
} from "../../lib/decoder";
import {
  bandPower,
  buildDemoModel,
  features,
  generateTrial,
  IMAGERY_CLASSES,
  IMAGERY_LABEL,
  MU_BAND,
  predictProba,
  rng,
  SFREQ,
  type ImageryClass,
  type Trial,
} from "../../lib/simEeg";
import type { RobotSession } from "../../hooks/useRobot";
import type { StudySession } from "../../hooks/useStudySession";
import { RobotPanel } from "./RobotPanel";
import "./LabPage.css";

/** One decoder output, whatever the EEG source. */
type Prediction = {
  id: number;
  source: EegSource;
  label: string;
  confidence: number;
  proba: Array<{ cls: string; p: number }>;
  /** The label the data was recorded/generated with, when known. */
  truth: string | null;
  /** Confident labels seen before this prediction, for the agreement check. */
  historyBefore: string[];
};

type Experiment = { id: string; template_id: string | null; model: { model_id?: string } | null; metrics: Record<string, unknown> | null; created_at: string };
type InferResult = {
  labels: string[];
  confidence: number[] | null;
  proba: number[][] | null;
  classes: string[];
  true_labels: string[];
  indices: number[];
  split: string;
  model_kind: string;
};

const SIM_MAPPING: Mapping = { left_hand: "turn_left", right_hand: "turn_right" };
const STREAM_SCRIPT: ImageryClass[] = ["left_hand", "left_hand", "right_hand", "right_hand"];
const classLabel = (c: string) => (c in IMAGERY_LABEL ? IMAGERY_LABEL[c as ImageryClass] : c);
const pct = (v: number) => `${Math.round(v * 100)}%`;

function Trace({ trial }: { trial: Trial }) {
  const w = 560;
  const h = 64;
  const line = (x: number[]) => {
    const peak = Math.max(...x.map(Math.abs), 1);
    return x.map((v, i) => `${((i / (x.length - 1)) * w).toFixed(1)},${(h / 2 - (v / peak) * (h / 2 - 2)).toFixed(1)}`).join(" ");
  };
  return (
    <figure className="lab-trace">
      {(["c3", "c4"] as const).map((ch) => (
        <div key={ch} className="lab-trace-row">
          <span className="lab-trace-label">{ch.toUpperCase()}</span>
          <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label={`Simulated ${ch.toUpperCase()} signal, 2 seconds`}>
            <polyline points={line(trial[ch])} fill="none" className={`lab-line lab-line-${ch}`} />
          </svg>
        </div>
      ))}
      <figcaption>
        2 seconds of simulated EEG at {SFREQ} Hz from two scalp sites over the motor cortex: C3 (left hemisphere) and C4 (right
        hemisphere). Each trace is scaled to fit.
      </figcaption>
    </figure>
  );
}

function Bars({ rows, ariaLabel }: { rows: Array<{ label: string; value: number; display: string; highlight?: boolean }>; ariaLabel: string }) {
  const max = Math.max(...rows.map((r) => r.value), 1e-9);
  return (
    <ul className="lab-bars" aria-label={ariaLabel}>
      {rows.map((r) => (
        <li key={r.label} className={r.highlight ? "lab-bar-hi" : ""}>
          <span className="lab-bar-label">{r.label}</span>
          <span className="lab-bar-track">
            <span className="lab-bar-fill" style={{ width: `${Math.max(2, (r.value / max) * 100)}%` }} />
          </span>
          <span className="lab-bar-value num">{r.display}</span>
        </li>
      ))}
    </ul>
  );
}

/** The BCI Lab: an educational walk from EEG to an AI prediction, through a safety gate, to the robot arm. */
export function LabPage({ r, session, openLearn }: { r: RobotSession; session: StudySession; openLearn: () => void }) {
  const [source, setSource] = useState<EegSource>("simulated");
  const [now, setNow] = useState(() => Date.now());
  const [predictions, setPredictions] = useState(0);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [lastSentAt, setLastSentAt] = useState<number | null>(null);
  const [sentId, setSentId] = useState<number | null>(null);
  const [threshold, setThreshold] = useState(0.8);
  const [agreement, setAgreement] = useState(2);
  const [mapping, setMapping] = useState<Mapping>(SIM_MAPPING);

  // Simulation
  const [noise, setNoise] = useState(12);
  const [imagined, setImagined] = useState<ImageryClass>("left_hand");
  const [trial, setTrial] = useState<Trial | null>(null);
  const demo = useMemo(() => buildDemoModel(2026, noise), [noise]);

  // Demo stream: a scripted run of simulated trials through the whole loop (predict, gate, optionally act).
  const [streaming, setStreaming] = useState(false);
  const [streamSendsToArm, setStreamSendsToArm] = useState(false);
  const [streamStep, setStreamStep] = useState(0);
  const stepRef = useRef<() => void>(() => {});

  // Prerecorded
  const [experiments, setExperiments] = useState<Experiment[] | null>(null);
  const [expId, setExpId] = useState("");
  const [infer, setInfer] = useState<InferResult | null>(null);
  const [sample, setSample] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const studyId = session.selectedId;

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(id);
  }, []);

  // A new source or study starts a fresh decoding session.
  useEffect(() => {
    setPrediction(null);
    setHistory([]);
    setSentId(null);
    setTrial(null);
    setInfer(null);
    setLoadError(null);
    setMapping(source === "simulated" ? SIM_MAPPING : {});
  }, [source, studyId]);

  useEffect(() => {
    if (source !== "prerecorded" || !studyId || !session.online) return;
    let cancelled = false;
    suiteCall<{ experiments: Experiment[] }>("neurostudio.experiments.list", { study_id: studyId })
      .then((res) => {
        if (cancelled) return;
        const trained = res.experiments.filter(isTrained);
        setExperiments(trained);
        setExpId((cur) => (trained.some((x) => x.id === cur) ? cur : (trained[0]?.id ?? "")));
      })
      .catch((e) => !cancelled && setLoadError(describeError(e).title));
    return () => {
      cancelled = true;
    };
  }, [source, studyId, session.online]);

  /** `fresh` starts a new run of predictions (e.g. a newly loaded model). */
  function publish(p: Omit<Prediction, "id" | "historyBefore">, fresh = false) {
    const id = predictions + 1;
    const before = fresh ? [] : history;
    setPredictions(id);
    setPrediction({ ...p, id, historyBefore: before });
    // Only confident predictions count toward agreement; a low-confidence one breaks the run.
    setHistory((p.confidence >= Math.max(threshold, MIN_THRESHOLD) ? [...before, p.label] : []).slice(-10));
  }

  function newTrial(cls: ImageryClass = imagined) {
    const t = generateTrial(cls, noise, rng(Date.now() ^ (predictions * 7919)));
    setTrial(t);
    const p = predictProba(demo.model, features(t));
    const best = p[1] > p[0] ? 1 : 0;
    publish({
      source: "simulated",
      label: IMAGERY_CLASSES[best],
      confidence: p[best],
      proba: IMAGERY_CLASSES.map((c, i) => ({ cls: c, p: p[i] })),
      truth: t.cls,
    });
  }

  async function loadPredictions() {
    if (!studyId || !expId) return;
    setLoading(true);
    setLoadError(null);
    try {
      const res = await exec<InferResult>("neurostudio.infer.run", { study_id: studyId, experiment_id: expId, split: "test" });
      setInfer(res);
      setMapping((m) => Object.fromEntries(res.classes.map((c) => [c, m[c] ?? "none"])));
      showSample(res, 0, true);
    } catch (e) {
      setLoadError(describeError(e).detail);
    } finally {
      setLoading(false);
    }
  }

  function showSample(res: InferResult, i: number, fresh = false) {
    setSample(i);
    const row = res.proba?.[i];
    publish({
      source: "prerecorded",
      label: res.labels[i],
      confidence: res.confidence?.[i] ?? Number.NaN,
      proba: row ? res.classes.map((c, k) => ({ cls: c, p: row[k] })) : [],
      truth: res.true_labels[i] ?? null,
    }, fresh);
  }

  const config = { threshold, agreement, cooldownMs: r.status?.decoder_cooldown_ms ?? 2500 };
  const decision = prediction
    ? gate({ label: prediction.label, confidence: prediction.confidence, mapping, history: prediction.historyBefore, lastSentAt, now, config })
    : null;
  const armed = !!r.status?.armed && r.status.state === "connected" && !r.status.estop_latched;
  const alreadySent = prediction !== null && sentId === prediction.id;

  async function sendToArm() {
    if (!prediction || !decision?.approved || !decision.command || alreadySent) return;
    const cmd: SafeCommand = decision.command;
    const res = await r.run("Sending decoder command", () => r.robot.decoder(cmd, prediction.confidence, threshold, prediction.source), r.moved);
    if (res) {
      setLastSentAt(Date.now());
      setSentId(prediction.id);
    }
  }

  // Each tick imagines the next movement in the script (two of each, so the agreement rule is visible).
  stepRef.current = () => {
    const cls = STREAM_SCRIPT[streamStep % STREAM_SCRIPT.length];
    setImagined(cls);
    setStreamStep(streamStep + 1);
    newTrial(cls);
  };
  const tickMs = Math.max(1500, config.cooldownMs + 500);
  useEffect(() => {
    if (!streaming) return;
    stepRef.current();
    const id = window.setInterval(() => stepRef.current(), tickMs);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming, tickMs]);
  useEffect(() => {
    if (source !== "simulated" || r.status?.estop_latched) setStreaming(false);
  }, [source, r.status?.estop_latched]);
  // The stream acts only through the same gate and armed check as the manual button.
  useEffect(() => {
    if (streaming && streamSendsToArm && decision?.approved && armed && !alreadySent && !r.pending) void sendToArm();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prediction?.id]);

  const classes = source === "simulated" ? IMAGERY_CLASSES : (infer?.classes ?? []);
  const trialPower = trial
    ? [
        { label: "C3 (left)", value: bandPower(trial.c3, SFREQ, ...MU_BAND) },
        { label: "C4 (right)", value: bandPower(trial.c4, SFREQ, ...MU_BAND) },
      ]
    : [];

  return (
    <div className="lab">
      <header className="lab-head">
        <p className="eyebrow">BCI Lab</p>
        <h1>From brain signal to robot arm</h1>
        <p className="page-desc">
          Follow one brain–computer interface loop from start to finish: record EEG, let an AI model classify it, check whether
          the prediction is trustworthy, and only then turn it into a small, safe robot movement.
        </p>
        <div className={`lab-source lab-source-${source}`} role="status" aria-live="polite">
          <strong>Data source: {SOURCE_LABEL[source]}</strong>
          <span>
            {source === "simulated" && "Generated by this app from a model of real brain rhythms. Not a measurement of anyone's brain."}
            {source === "prerecorded" && "Recorded earlier and replayed from a saved study. Not happening in real time."}
          </span>
        </div>
      </header>

      <Card title="1 · The science" className="lab-step">
        <div className="lab-science">
          <p>
            When you <strong>imagine</strong> moving your hand, neurons in the motor cortex on the <em>opposite</em> side of the
            brain stop firing in lock-step. Their shared 8–12 Hz <strong>mu rhythm</strong> gets weaker. This drop is called{" "}
            <strong>event-related desynchronization</strong>. Imagining your left hand weakens mu over the right hemisphere
            (electrode C4); imagining your right hand weakens it over the left (C3).
          </p>
          <ol className="lab-pipeline" aria-label="BCI pipeline">
            <li><strong>Sense</strong> EEG electrodes pick up microvolt signals.</li>
            <li><strong>Decode</strong> An AI model turns signal features into a prediction with a confidence.</li>
            <li><strong>Gate</strong> Safety rules reject uncertain or inconsistent predictions.</li>
            <li><strong>Act</strong> An approved prediction becomes one small, pre-approved arm movement.</li>
          </ol>
          <p className="help">
            New to EEG? <button type="button" className="btn-link" onClick={openLearn}>Review the EEG lessons in Learn</button> first.
          </p>
        </div>
      </Card>

      <Card title="2 · EEG input" description="Choose where the brain signal comes from.">
        <fieldset className="lab-sources">
          <legend className="sr-only">EEG source</legend>
          <label>
            <input type="radio" name="source" checked={source === "simulated"} onChange={() => setSource("simulated")} /> Simulated EEG
            <span className="help">Demonstration mode. Works without any hardware.</span>
          </label>
          <label>
            <input type="radio" name="source" checked={source === "prerecorded"} onChange={() => setSource("prerecorded")} /> Prerecorded EEG
            <span className="help">Held-out trials from a study you trained in NeuroStudio.</span>
          </label>
          <label className="lab-disabled">
            <input type="radio" name="source" disabled /> Live EEG
            <span className="help">Not available: this build has no interface to an EEG amplifier.</span>
          </label>
        </fieldset>

        {source === "simulated" && (
          <div className="lab-sim">
            <div className="form-row">
              <Field label="Imagined movement">
                <select value={imagined} onChange={(e) => setImagined(e.target.value as ImageryClass)}>
                  {IMAGERY_CLASSES.map((c) => <option key={c} value={c}>{IMAGERY_LABEL[c]}</option>)}
                </select>
              </Field>
              <Field label={`Sensor noise: ${noise} µV`} hint="More noise makes the brain rhythm harder to see.">
                <input type="range" min={0} max={40} step={1} value={noise} onChange={(e) => setNoise(Number(e.target.value))} />
              </Field>
              <button type="button" className="btn btn-primary" disabled={streaming} onClick={() => newTrial()}>Generate simulated trial</button>
            </div>
            <div className="form-row">
              <button type="button" className="btn" onClick={() => { setStreamStep(0); setStreaming(!streaming); }}>
                {streaming ? "Stop demo stream" : "Run demo stream"}
              </button>
              <label>
                <input type="checkbox" checked={streamSendsToArm} onChange={(e) => setStreamSendsToArm(e.target.checked)} /> Send approved commands to the arm
                <span className="help">Off by default. Needs the arm connected with motion enabled below; the safety gate still decides every move.</span>
              </label>
            </div>
            {streaming && <p className="help" role="status">Streaming simulated trials every {(tickMs / 1000).toFixed(1)} s: left, left, right, right, repeating. Not a measurement of anyone's brain.</p>}
            {trial ? (
              <>
                <Trace trial={trial} />
                <h4 className="lab-sub">Mu-band power (8–12 Hz)</h4>
                <Bars
                  ariaLabel="Mu-band power per electrode"
                  rows={trialPower.map((b) => ({ label: b.label, value: b.value, display: `${b.value.toFixed(1)} µV²` }))}
                />
                <p className="help">
                  This trial was generated as <strong>{IMAGERY_LABEL[trial.cls]}</strong>, so mu power should be lower at{" "}
                  {trial.cls === "left_hand" ? "C4" : "C3"}. With high noise it may not be.
                </p>
              </>
            ) : (
              <p className="help">Generate a trial to see the signal.</p>
            )}
          </div>
        )}

        {source === "prerecorded" && (
          <div className="lab-pre">
            {!studyId ? (
              <p className="help">Choose a study on Home first. It needs a model trained in NeuroStudio.</p>
            ) : !session.online ? (
              <p className="help">The analysis backend is offline, so saved studies cannot be read.</p>
            ) : experiments && !experiments.length ? (
              <p className="help">This study has no trained model yet. Train one in NeuroStudio → Train.</p>
            ) : (
              <div className="form-row">
                <Field label="Trained model">
                  <select value={expId} onChange={(e) => { setExpId(e.target.value); setInfer(null); }}>
                    {(experiments ?? []).map((x) => (
                      <option key={x.id} value={x.id}>{shortId(x.id, 14)} · {fmtDate(x.created_at)}</option>
                    ))}
                  </select>
                </Field>
                <button type="button" className="btn btn-primary" disabled={!expId || loading} onClick={() => void loadPredictions()}>
                  {loading ? "Running model…" : "Run model on held-out trials"}
                </button>
              </div>
            )}
            {loadError && <p className="inline-error" role="alert">{loadError}</p>}
            {infer && (
              <div className="lab-replay">
                <button type="button" className="btn btn-sm" disabled={sample <= 0} onClick={() => showSample(infer, sample - 1)}>Previous trial</button>
                <span>
                  Trial {sample + 1} of {infer.labels.length} (dataset sample #{infer.indices[sample]}) · recorded label{" "}
                  <strong>{infer.true_labels[sample]}</strong>
                </span>
                <button type="button" className="btn btn-sm" disabled={sample >= infer.labels.length - 1} onClick={() => showSample(infer, sample + 1)}>Next trial</button>
              </div>
            )}
          </div>
        )}
      </Card>

      <Card title="3 · AI prediction" description="What the model thinks this trial was, and how sure it is.">
        {prediction ? (
          <div className="lab-pred">
            <p className="lab-pred-main">
              Prediction: <strong>{classLabel(prediction.label)}</strong> · confidence <strong className="num">{Number.isFinite(prediction.confidence) ? pct(prediction.confidence) : "unknown"}</strong>
              {prediction.truth && (
                <> · {prediction.truth === prediction.label ? <Badge tone="ok">matches the true label</Badge> : <Badge tone="warn">wrong: true label {classLabel(prediction.truth)}</Badge>}</>
              )}
            </p>
            {!!prediction.proba.length && (
              <Bars
                ariaLabel="Predicted probability per class"
                rows={prediction.proba.map((c) => ({ label: classLabel(c.cls), value: c.p, display: pct(c.p), highlight: c.cls === prediction.label }))}
              />
            )}
            <p className="help">
              {prediction.source === "simulated"
                ? `Model: logistic regression trained in this app on ${demo.nTrain} simulated trials (features: log mu power at C3 and C4). On ${demo.nTest} other simulated trials it was right ${pct(demo.testAccuracy)} of the time at this noise level.`
                : `Model: ${infer?.model_kind === "sklearn" ? "scikit-learn logistic regression" : infer?.model_kind} from NeuroStudio, running locally on this computer. This trial was held out from training (${infer?.split} split).`}{" "}
              Confidence is the model's own probability for its top class. It is not a guarantee: models can be confidently wrong.
            </p>
          </div>
        ) : (
          <p className="help">No prediction yet. Produce EEG input in step 2.</p>
        )}
      </Card>

      <Card title="4 · Safety gate" description="A prediction only becomes a movement when every check passes.">
        <div className="form-row">
          <Field label={`Confidence threshold: ${pct(threshold)}`} hint={`Minimum ${pct(MIN_THRESHOLD)}; the robot driver enforces this too.`}>
            <input type="range" min={MIN_THRESHOLD} max={MAX_THRESHOLD} step={0.01} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
          </Field>
          <Field label="Agreeing predictions needed">
            <select value={agreement} onChange={(e) => setAgreement(Number(e.target.value))}>
              {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </Field>
        </div>
        {!!classes.length && (
          <table className="table lab-map">
            <caption>Which movement each predicted class may trigger</caption>
            <thead><tr><th>Predicted class</th><th>Robot command</th></tr></thead>
            <tbody>
              {classes.map((c) => (
                <tr key={c}>
                  <td>{classLabel(c)}</td>
                  <td>
                    <select aria-label={`Command for ${classLabel(c)}`} value={mapping[c] ?? "none"} onChange={(e) => setMapping({ ...mapping, [c]: e.target.value as SafeCommand | "none" })}>
                      <option value="none">No movement</option>
                      {SAFE_COMMANDS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {decision ? (
          <>
            <ul className="checklist lab-gate" aria-label="Safety gate checks">
              {decision.checks.map((c) => (
                <li key={c.id} className={c.ok ? "ok" : "lab-fail"}>
                  <span className="check-mark" aria-hidden>{c.ok ? "✓" : "✕"}</span>
                  <span className="check-label">
                    {c.label}
                    <span className="sr-only">{c.ok ? " (passed)" : " (failed)"}</span>
                  </span>
                  <span className="check-detail">{c.detail}</span>
                </li>
              ))}
            </ul>
            <p className={`lab-verdict ${decision.approved ? "lab-ok" : "lab-no"}`} role="status">
              {decision.approved
                ? `Approved: ${SAFE_COMMANDS.find((s) => s.id === decision.command)?.label}`
                : "Rejected: the arm will not move for this prediction."}
            </p>
          </>
        ) : (
          <p className="help">The gate runs once there is a prediction.</p>
        )}
      </Card>

      <Card title="5 · Robot arm" description="Waveshare RoArm-M2-S. The arm only moves for approved predictions or your manual commands.">
        <div className="lab-send">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!decision?.approved || !armed || alreadySent || !!r.pending}
            onClick={() => void sendToArm()}
          >
            Send approved command to arm
          </button>
          <span className="help">
            {alreadySent
              ? "Already sent. Each prediction can move the arm once."
              : !decision?.approved
                ? "Waiting for an approved prediction."
                : !armed
                  ? "Connect the arm and enable motion below."
                  : `Will send “${SAFE_COMMANDS.find((s) => s.id === decision.command)?.label}” to the real arm. The EEG is ${SOURCE_LABEL[prediction!.source].toLowerCase()}; the movement is physical.`}
          </span>
        </div>
        <RobotPanel r={r} />
      </Card>
    </div>
  );
}
