import { test } from "node:test";
import assert from "node:assert/strict";
import { bandPower, buildDemoModel, features, generateTrial, predictProba, rng, SFREQ } from "../src/lib/simEeg.ts";

test("band power isolates a sinusoid's frequency", () => {
  const x = Array.from({ length: 256 }, (_, i) => 10 * Math.sin((2 * Math.PI * 10 * i) / SFREQ));
  assert.ok(bandPower(x, SFREQ, 8, 12) > 100 * bandPower(x, SFREQ, 20, 30));
});

test("simulated imagery lowers mu power over the opposite hemisphere", () => {
  const r = rng(1);
  let leftLowerAtC4 = 0;
  for (let i = 0; i < 40; i++) {
    const [c3, c4] = features(generateTrial("left_hand", 2, r));
    if (c4 < c3) leftLowerAtC4++;
  }
  assert.ok(leftLowerAtC4 >= 32, `left-hand trials with lower C4 mu: ${leftLowerAtC4}/40`);
});

test("generation is deterministic for a seed", () => {
  assert.deepEqual(generateTrial("right_hand", 3, rng(7)).c3.slice(0, 5), generateTrial("right_hand", 3, rng(7)).c3.slice(0, 5));
});

test("the demo model is well above chance on held-out simulated trials at low noise", () => {
  const demo = buildDemoModel(42, 2);
  assert.ok(demo.testAccuracy >= 0.8, `held-out accuracy ${demo.testAccuracy}`);
  const p = predictProba(demo.model, features(generateTrial("left_hand", 2, rng(99))));
  assert.ok(Math.abs(p[0] + p[1] - 1) < 1e-9);
});

test("heavy noise lowers held-out accuracy, so confidence gating matters", () => {
  const clean = buildDemoModel(42, 2).testAccuracy;
  const noisy = buildDemoModel(42, 40).testAccuracy;
  assert.ok(noisy < clean, `clean ${clean} vs noisy ${noisy}`);
});
