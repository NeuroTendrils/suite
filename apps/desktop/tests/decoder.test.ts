import { test } from "node:test";
import assert from "node:assert/strict";
import { gate, MIN_THRESHOLD, streak, type Mapping } from "../src/lib/decoder.ts";

const mapping: Mapping = { left_hand: "turn_left", right_hand: "turn_right", rest: "none" };
const config = { threshold: 0.75, agreement: 2, cooldownMs: 2500 };
const base = { mapping, history: ["left_hand"], lastSentAt: null, now: 10_000, config };
const failed = (r: ReturnType<typeof gate>) => r.checks.filter((c) => !c.ok).map((c) => c.id);

test("a confident, mapped, consistent prediction after the cooldown is approved", () => {
  const r = gate({ ...base, label: "left_hand", confidence: 0.9 });
  assert.equal(r.approved, true);
  assert.equal(r.command, "turn_left");
});

test("low confidence is rejected and does not count toward agreement", () => {
  const r = gate({ ...base, label: "left_hand", confidence: 0.7 });
  assert.equal(r.approved, false);
  assert.equal(r.command, null);
  assert.deepEqual(failed(r), ["confidence", "agreement"]);
});

test("a NaN confidence is never approved", () => {
  assert.equal(gate({ ...base, label: "left_hand", confidence: Number.NaN }).approved, false);
});

test("an unmapped class never moves the arm", () => {
  const r = gate({ ...base, history: ["rest"], label: "rest", confidence: 0.99 });
  assert.deepEqual(failed(r), ["mapped"]);
  assert.equal(gate({ ...base, label: "unknown", confidence: 0.99, history: ["unknown"] }).approved, false);
});

test("a single prediction is not enough when agreement is 2, and a flip resets the run", () => {
  assert.deepEqual(failed(gate({ ...base, history: [], label: "left_hand", confidence: 0.95 })), ["agreement"]);
  assert.deepEqual(failed(gate({ ...base, history: ["right_hand"], label: "left_hand", confidence: 0.95 })), ["agreement"]);
});

test("cooldown blocks rapid repeats", () => {
  const r = gate({ ...base, label: "left_hand", confidence: 0.95, lastSentAt: 9_000 });
  assert.deepEqual(failed(r), ["cooldown"]);
  assert.equal(gate({ ...base, label: "left_hand", confidence: 0.95, lastSentAt: 7_000 }).approved, true);
});

test("thresholds below the driver floor are raised to it", () => {
  const r = gate({ ...base, label: "left_hand", confidence: MIN_THRESHOLD - 0.05, config: { ...config, threshold: 0.1 } });
  assert.deepEqual(failed(r), ["confidence", "agreement"]);
});

test("streak counts trailing equal labels", () => {
  assert.equal(streak([]), 0);
  assert.equal(streak(["a", "b", "b"]), 2);
  assert.equal(streak(["b", "a"]), 1);
});
