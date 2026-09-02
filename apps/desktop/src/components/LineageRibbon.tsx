import "./LineageRibbon.css";

export type LineageStep = {
  id: string;
  /** Short verb phrase shown under the knob. */
  label: string;
  /** Parameters in one glance — "1 Hz", "2 flagged". */
  detail?: string;
  /** "human" steps are judgment calls; they read differently from automation. */
  kind: "io" | "filter" | "human";
  artifactId?: string;
  at?: string;
};

export type LineageRibbonProps = {
  steps: LineageStep[];
  /** Index currently being viewed. steps.length - 1 is the live head. */
  cursor: number;
  onCursorChange: (index: number) => void;
  onReturnToHead: () => void;
  /** Transient message replacing the subtitle, e.g. after a commit. */
  notice?: string | null;
};

export function LineageRibbon({
  steps,
  cursor,
  onCursorChange,
  onReturnToHead,
  notice,
}: LineageRibbonProps) {
  const head = steps.length - 1;
  const rewound = cursor !== head;

  return (
    <section className="lineage" aria-label="Processing lineage">
      <div className="lineage__head">
        <b>Lineage</b>
        <em className={notice ? "is-notice" : undefined}>
          {notice ?? "every step is reversible — click one to see the signal as it was"}
        </em>
        <div className="lineage__actions">
          {rewound && (
            <span className="lineage__warn">Viewing an earlier state — read only</span>
          )}
          <button
            type="button"
            className="btn"
            onClick={onReturnToHead}
            disabled={!rewound}
          >
            Return to head
          </button>
        </div>
      </div>

      <ol className="lineage__chain">
        {steps.map((step, i) => {
          const done = i <= cursor;
          const classes = [
            "lineage__step",
            done ? "is-done" : "",
            i === cursor ? "is-current" : "",
            step.kind === "human" && done ? "is-human" : "",
          ]
            .filter(Boolean)
            .join(" ");

          return (
            <li key={step.id}>
              <button
                type="button"
                className={classes}
                aria-current={i === cursor ? "step" : undefined}
                onClick={() => onCursorChange(i)}
                title={step.at ? `${step.label} — ${step.at}` : step.label}
              >
                <i className="lineage__rail" aria-hidden="true" />
                <i className="lineage__knob" aria-hidden="true" />
                <span className="lineage__label">{step.label}</span>
                {step.detail && (
                  <span className="lineage__detail num">{step.detail}</span>
                )}
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
