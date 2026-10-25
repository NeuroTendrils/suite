/** Safety gate between a decoder prediction and a robot command.
 *  The Rust driver re-checks confidence and cooldown, so this gate is the explanation
 *  students see, not the only line of defence. */

export type SafeCommand = "home" | "turn_left" | "turn_right" | "gripper_open" | "gripper_close";
export type EegSource = "live" | "prerecorded" | "simulated";

export const SAFE_COMMANDS: Array<{ id: SafeCommand; label: string }> = [
  { id: "turn_left", label: "Turn base left" },
  { id: "turn_right", label: "Turn base right" },
  { id: "gripper_open", label: "Open gripper" },
  { id: "gripper_close", label: "Close gripper" },
  { id: "home", label: "Return home" },
];

export const SOURCE_LABEL: Record<EegSource, string> = {
  live: "Live EEG",
  prerecorded: "Prerecorded EEG",
  simulated: "Simulated EEG",
};

/** Must match `Config::min_decoder_confidence` in src-tauri/src/robot/controller.rs. */
export const MIN_THRESHOLD = 0.6;
export const MAX_THRESHOLD = 0.99;

export type GateConfig = { threshold: number; agreement: number; cooldownMs: number };
export type Mapping = Record<string, SafeCommand | "none">;
export type GateCheck = { id: "confidence" | "mapped" | "agreement" | "cooldown"; label: string; ok: boolean; detail: string };
export type GateResult = { approved: boolean; command: SafeCommand | null; checks: GateCheck[] };

/** Number of most recent predictions (newest last) that share the newest label. */
export function streak(history: string[]): number {
  if (!history.length) return 0;
  const last = history[history.length - 1];
  let n = 0;
  for (let i = history.length - 1; i >= 0 && history[i] === last; i--) n++;
  return n;
}

/** Decide whether a prediction may become a robot command.
 *  `history` holds the labels of earlier confident predictions in this session, oldest first. */
export function gate(input: {
  label: string;
  confidence: number;
  mapping: Mapping;
  history: string[];
  lastSentAt: number | null;
  now: number;
  config: GateConfig;
}): GateResult {
  const { label, confidence, mapping, history, lastSentAt, now, config } = input;
  const threshold = Math.min(MAX_THRESHOLD, Math.max(MIN_THRESHOLD, config.threshold));
  const confident = Number.isFinite(confidence) && confidence >= threshold;
  const mapped = mapping[label] && mapping[label] !== "none" ? (mapping[label] as SafeCommand) : null;
  const run = confident ? streak([...history, label]) : 0;
  const waited = lastSentAt === null ? Infinity : now - lastSentAt;
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  const checks: GateCheck[] = [
    {
      id: "confidence",
      label: "Confident enough",
      ok: confident,
      detail: Number.isFinite(confidence)
        ? `${pct(confidence)} ${confident ? "≥" : "<"} threshold ${pct(threshold)}`
        : "No probability available",
    },
    {
      id: "mapped",
      label: "Mapped to a safe command",
      ok: !!mapped,
      detail: mapped ? `“${label}” → ${SAFE_COMMANDS.find((c) => c.id === mapped)?.label}` : `“${label}” is not mapped to any movement`,
    },
    {
      id: "agreement",
      label: "Consistent predictions",
      ok: run >= config.agreement,
      detail: `${run} of ${config.agreement} confident prediction${config.agreement === 1 ? "" : "s"} in a row agree`,
    },
    {
      id: "cooldown",
      label: "Cooldown elapsed",
      ok: waited >= config.cooldownMs,
      detail: lastSentAt === null ? "No command sent yet" : `${(Math.min(waited, 99_000) / 1000).toFixed(1)} s since last command (need ${(config.cooldownMs / 1000).toFixed(1)} s)`,
    },
  ];
  const approved = checks.every((c) => c.ok);
  return { approved, command: approved ? mapped : null, checks };
}
