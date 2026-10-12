import { test } from "node:test";
import assert from "node:assert/strict";
import { backendFailure, describeError } from "../src/lib/errors.ts";

test("backendFailure treats status:error replies as failures", () => {
  // Regression: NeuroStudio returns these as successful IPC replies; the UI used to log them as "ok".
  assert.equal(
    backendFailure({ status: "error", message: "training set has <2 classes — build a multi-condition dataset" }),
    "training set has <2 classes — build a multi-condition dataset",
  );
  assert.equal(backendFailure({ status: "not_implemented" }), 'backend reported status "not_implemented"');
  assert.equal(backendFailure({ status: "ok", model: {} }), null);
  assert.equal(backendFailure({ studies: [] }), null);
  assert.equal(backendFailure(null), null);
  assert.equal(backendFailure("text"), null);
});

test("describeError gives actionable titles and keeps the raw detail", () => {
  const cases: Array<[string, RegExp]> = [
    ["command not allowlisted: batch.preview", /not enabled/],
    ["python backend not running", /backend is not running/],
    ["ipc connect: Connection refused (os error 61)", /backend is not running/],
    ["ipc read: Resource temporarily unavailable (os error 35)", /120 seconds/],
    ["invalid params: 1 validation error for X", /rejected the request parameters/],
    ["no epochset — create epochs first", /No epochs/],
    ["training set has <2 classes — build a multi-condition dataset", /two classes/],
    ["no trained model for experiment", /no trained model/],
    ["'plan not found: plan_x'", /no longer exists/],
  ];
  for (const [raw, title] of cases) {
    const f = describeError(new Error(raw));
    assert.match(f.title, title, raw);
    assert.equal(f.detail, raw);
  }
  const unknown = describeError("something odd");
  assert.equal(unknown.title, "The operation failed");
  assert.equal(unknown.detail, "something odd");
  assert.equal(describeError({ code: 1 }).detail, '{"code":1}');
});

import { inspectProblem } from "../src/lib/errors.ts";

test("inspectProblem flags unreadable files that came back as successful replies", () => {
  // Regression: a corrupt .edf was shown as "ready" with a success message.
  const bad = inspectProblem({ format: "edf", status: "unreadable", error: "Bad EDF file provided." });
  assert.ok(bad);
  assert.match(bad.title, /EDF file couldn’t be read/);
  assert.equal(bad.detail, "Bad EDF file provided.");
  const missing = inspectProblem({ status: "error", error: "no importer can handle source" });
  assert.match(missing?.title ?? "", /isn’t supported|doesn’t exist/);
  assert.equal(inspectProblem({ format: "fif", status: "ok" }), null);
  assert.equal(inspectProblem({ format: "text_matrix", status: "needs_config" }), null);
  assert.equal(inspectProblem(null), null);
});
