import { useEffect, useRef, useState } from "react";
import { Icon } from "../../components/ui";
import "./LearnPage.css";

type Phase = "checking" | "starting" | "ready" | "error";

/** Keep this mounted when leaving Learn so an open lesson or quiz is retained. */
export function LearnPage({ active }: { active: boolean }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [phase, setPhase] = useState<Phase>("checking");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    let starting = false;
    setPhase("checking");
    const timer = window.setTimeout(() => {
      controller.abort();
      if (!disposed) setPhase("error");
    }, 30_000);

    function receive(event: MessageEvent) {
      if (disposed || !starting || !frame.current || event.source !== frame.current.contentWindow) return;
      if (event.data?.channel !== "neurolearn-desktop") return;
      if (event.data.type !== "ready" && event.data.type !== "error") return;
      window.clearTimeout(timer);
      setPhase(event.data.type === "ready" ? "ready" : "error");
    }
    window.addEventListener("message", receive);

    async function load() {
      try {
        // Check a build marker first: Vite's SPA fallback can otherwise return
        // Suite's own index.html for a missing learner and recursively embed it.
        const response = await fetch("/learn/desktop-build.json", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("Missing lesson bundle");
        const build = await response.json();
        if (build.app !== "neurolearn" || build.version !== 1) throw new Error("Invalid lesson bundle");
        if (!disposed && !controller.signal.aborted) {
          starting = true;
          setPhase("starting");
        }
      } catch {
        if (!disposed) {
          window.clearTimeout(timer);
          setPhase("error");
        }
      }
    }
    void load();
    return () => {
      disposed = true;
      controller.abort();
      window.clearTimeout(timer);
      window.removeEventListener("message", receive);
    };
  }, [attempt]);

  return (
    <section className="learn-page" aria-labelledby="learn-title" hidden={!active}>
      <header className="learn-header">
        <div>
          <h1 id="learn-title">Learn</h1>
          <p>EEG lessons, practice, and simulations</p>
        </div>
        <span className="learn-local"><Icon name="check" size={15} /> Works offline · Progress saved on this device</span>
      </header>
      <div className="learn-surface" aria-busy={phase === "checking" || phase === "starting"}>
        {(phase === "starting" || phase === "ready") && (
          <iframe
            ref={frame}
            className={`learn-frame ${phase === "starting" ? "learn-frame-starting" : ""}`}
            src="/learn/index.html?desktop=1"
            title="NeuroLearn lessons and practice"
            tabIndex={phase === "ready" ? 0 : -1}
            aria-hidden={phase !== "ready"}
          />
        )}
        {(phase === "checking" || phase === "starting") && (
          <div className="learn-status" role="status">
            <span className="spinner" aria-hidden />
            <p>Loading Learn…</p>
          </div>
        )}
        {phase === "error" && (
          <div className="learn-status" role="alert">
            <Icon name="alert" size={24} />
            <h2>Learn couldn’t load</h2>
            <p>Reload the bundled lessons to try again. Your saved progress is kept.</p>
            <button type="button" className="btn btn-primary" onClick={() => setAttempt((value) => value + 1)}>
              Reload Learn
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
