import { useState } from "react";

import type { Block } from "./api";

const CALLOUT_KINDS = ["tip", "limit", "myth", "warning"] as const;
const SIMS = [
  "artifact-detective",
  "band-playground",
  "filter-playground",
  "closed-loop",
] as const;

export const BLOCK_KINDS = [
  { type: "hook", label: "Hook", hint: "One question that earns the next paragraph" },
  { type: "heading", label: "Heading", hint: "Section break" },
  { type: "prose", label: "Prose", hint: "Explanation" },
  { type: "callout", label: "Callout", hint: "Tip, limit, myth, or warning" },
  { type: "figure", label: "Figure", hint: "Image from the content pack" },
  { type: "sim", label: "Simulation", hint: "Interactive the learner runs" },
  { type: "check", label: "Check", hint: "Questions — every lesson needs one" },
] as const;

export function emptyBlock(type: string): Block {
  switch (type) {
    case "callout":
      return { type, kind: "tip", text: "" };
    case "figure":
      return { type, asset: "", alt: "", caption: "" };
    case "sim":
      return { type, sim_id: "artifact-detective", goal: "" };
    case "check":
      return {
        type,
        pass_score: 0.7,
        questions: [
          {
            id: `q${Date.now().toString(36)}`,
            prompt: "",
            explain: "",
            choices: [
              { text: "", correct: true },
              { text: "", correct: false },
            ],
          },
        ],
      };
    default:
      return { type, text: "" };
  }
}

type Props = {
  blocks: Block[];
  onChange: (next: Block[]) => void;
  /** Server-reported path like "blocks[2].text" so the bad block can be flagged. */
  errorPath?: string;
};

export function BlockEditor({ blocks, onChange, errorPath }: Props) {
  const [adding, setAdding] = useState(false);

  const errorIndex = errorPath?.match(/^blocks\[(\d+)\]/)?.[1];

  const update = (i: number, patch: Partial<Block>) =>
    onChange(blocks.map((b, j) => (i === j ? { ...b, ...patch } : b)));

  const remove = (i: number) => onChange(blocks.filter((_, j) => j !== i));

  const move = (i: number, delta: number) => {
    const j = i + delta;
    if (j < 0 || j >= blocks.length) return;
    const next = [...blocks];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };

  return (
    <div className="blocks">
      {blocks.map((block, i) => {
        const flagged = String(i) === errorIndex;
        return (
          <div key={i} className={`block${flagged ? " block--error" : ""}`}>
            <div className="block__bar">
              <span className="block__kind">{block.type}</span>
              <div className="block__spacer" />
              <button type="button" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up">↑</button>
              <button type="button" onClick={() => move(i, 1)} disabled={i === blocks.length - 1} aria-label="Move down">↓</button>
              <button type="button" onClick={() => remove(i)} aria-label="Remove block">×</button>
            </div>
            <BlockBody block={block} onChange={(patch) => update(i, patch)} />
          </div>
        );
      })}

      {adding ? (
        <div className="adder">
          {BLOCK_KINDS.map((k) => (
            <button
              key={k.type}
              type="button"
              className="adder__item"
              onClick={() => {
                onChange([...blocks, emptyBlock(k.type)]);
                setAdding(false);
              }}
            >
              <b>{k.label}</b>
              <span>{k.hint}</span>
            </button>
          ))}
          <button type="button" className="adder__cancel" onClick={() => setAdding(false)}>
            Cancel
          </button>
        </div>
      ) : (
        <button type="button" className="add" onClick={() => setAdding(true)}>
          + Add block
        </button>
      )}
    </div>
  );
}

function BlockBody({
  block,
  onChange,
}: {
  block: Block;
  onChange: (patch: Partial<Block>) => void;
}) {
  switch (block.type) {
    case "hook":
    case "heading":
    case "prose":
      return (
        <textarea className="resize-none"
          value={String(block.text ?? "")}
          rows={block.type === "prose" ? 5 : 2}
          placeholder={
            block.type === "hook"
              ? "How can a headset measure anything at all?"
              : block.type === "heading"
                ? "Section title"
                : "Plain text. **bold**, *italic*, `code`, [[glossary]] — no HTML."
          }
          onChange={(e) => onChange({ text: e.target.value })}
        />
      );

    case "callout":
      return (
        <>
          <div className="row">
            {CALLOUT_KINDS.map((k) => (
              <button
                key={k}
                type="button"
                className={`chip${block.kind === k ? " chip--on" : ""}`}
                onClick={() => onChange({ kind: k })}
              >
                {k}
              </button>
            ))}
          </div>
          <textarea className="resize-none"
            rows={3}
            value={String(block.text ?? "")}
            placeholder="EEG does not read thoughts."
            onChange={(e) => onChange({ text: e.target.value })}
          />
        </>
      );

    case "figure":
      return (
        <>
          <input
            value={String(block.asset ?? "")}
            placeholder="images/dipole.png — pack-relative, not a URL"
            onChange={(e) => onChange({ asset: e.target.value })}
          />
          <input
            value={String(block.alt ?? "")}
            placeholder="Alt text (required)"
            onChange={(e) => onChange({ alt: e.target.value })}
          />
          <input
            value={String(block.caption ?? "")}
            placeholder="Caption (optional)"
            onChange={(e) => onChange({ caption: e.target.value })}
          />
        </>
      );

    case "sim":
      return (
        <>
          <div className="row">
            {SIMS.map((s) => (
              <button
                key={s}
                type="button"
                className={`chip${block.sim_id === s ? " chip--on" : ""}`}
                onClick={() => onChange({ sim_id: s })}
              >
                {s}
              </button>
            ))}
          </div>
          <input
            value={String(block.goal ?? "")}
            placeholder="What should the learner accomplish here?"
            onChange={(e) => onChange({ goal: e.target.value })}
          />
        </>
      );

    case "check":
      return <CheckEditor block={block} onChange={onChange} />;

    default:
      return <p className="muted">Unknown block type.</p>;
  }
}

type Question = {
  id: string;
  prompt: string;
  explain: string;
  choices: { text: string; correct?: boolean }[];
};

function CheckEditor({
  block,
  onChange,
}: {
  block: Block;
  onChange: (patch: Partial<Block>) => void;
}) {
  const questions = (block.questions ?? []) as Question[];

  const setQuestions = (next: Question[]) => onChange({ questions: next });

  const updateQ = (i: number, patch: Partial<Question>) =>
    setQuestions(questions.map((q, j) => (i === j ? { ...q, ...patch } : q)));

  return (
    <div className="check">
      <label className="pass">
        Pass mark
        <input
          type="number"
          min={10}
          max={100}
          step={5}
          value={Math.round(Number(block.pass_score ?? 0.7) * 100)}
          onChange={(e) => onChange({ pass_score: Number(e.target.value) / 100 })}
        />
        %
      </label>

      {questions.map((q, i) => (
        <div key={q.id} className="q">
          <div className="q__head">
            <span>Question {i + 1}</span>
            <div className="block__spacer" />
            <button
              type="button"
              onClick={() => setQuestions(questions.filter((_, j) => j !== i))}
              disabled={questions.length === 1}
              aria-label="Remove question"
            >
              ×
            </button>
          </div>

          <textarea className="resize-none"
            rows={2}
            value={q.prompt}
            placeholder="What does the skull do to the signal?"
            onChange={(e) => updateQ(i, { prompt: e.target.value })}
          />

          {q.choices.map((c, ci) => (
            <div key={ci} className="choice-row">
              {/* Radio, not checkbox: the server requires exactly one correct
                  answer, so the input should not let you express otherwise. */}
              <input
                type="radio"
                name={`correct-${q.id}`}
                checked={Boolean(c.correct)}
                onChange={() =>
                  updateQ(i, {
                    choices: q.choices.map((cc, cj) => ({ ...cc, correct: cj === ci })),
                  })
                }
                aria-label={`Mark option ${ci + 1} correct`}
              />
              <input
                value={c.text}
                placeholder={`Option ${ci + 1}`}
                onChange={(e) =>
                  updateQ(i, {
                    choices: q.choices.map((cc, cj) =>
                      cj === ci ? { ...cc, text: e.target.value } : cc,
                    ),
                  })
                }
              />
              <button
                type="button"
                onClick={() =>
                  updateQ(i, { choices: q.choices.filter((_, cj) => cj !== ci) })
                }
                disabled={q.choices.length <= 2}
                aria-label="Remove option"
              >
                ×
              </button>
            </div>
          ))}

          <button
            type="button"
            className="mini"
            onClick={() =>
              updateQ(i, { choices: [...q.choices, { text: "", correct: false }] })
            }
            disabled={q.choices.length >= 6}
          >
            + option
          </button>

          <textarea className="resize-none"
            rows={2}
            value={q.explain}
            placeholder="Why that answer is right — shown after they answer. Required."
            onChange={(e) => updateQ(i, { explain: e.target.value })}
          />
        </div>
      ))}

      <button
        type="button"
        className="mini"
        onClick={() =>
          setQuestions([
            ...questions,
            {
              id: `q${Date.now().toString(36)}`,
              prompt: "",
              explain: "",
              choices: [
                { text: "", correct: true },
                { text: "", correct: false },
              ],
            },
          ])
        }
        disabled={questions.length >= 12}
      >
        + question
      </button>
    </div>
  );
}
