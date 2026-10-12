import { test } from "node:test";
import assert from "node:assert/strict";
import {
  findRecording,
  flattenRecordings,
  formatDuration,
  importGate,
  newestFirst,
  nextStep,
  parseMetadata,
  parsePositive,
  trainGate,
  validateSeed,
  validateSplitFractions,
  validateStudyName,
  validateSubjectLabel,
  type Manager,
  type ManagerRec,
} from "../src/lib/study.ts";

function rec(id: string, extra: Partial<ManagerRec> = {}): ManagerRec {
  return {
    id,
    name: null,
    source_format: "fif",
    sampling_rate: 250,
    duration: 10,
    modalities: ["eeg"],
    stream_ids: [],
    streams: [],
    validation_ok: null,
    validation_errors: 0,
    validation_warnings: 0,
    sync_group_ids: [],
    sync_confidence: null,
    ...extra,
  };
}

function manager(subjects: Manager["subjects"]): Manager {
  const recordings = subjects.reduce(
    (n, s) => n + s.sessions.reduce((m, ses) => m + ses.runs.reduce((k, r) => k + r.recordings.length, 0), 0),
    0,
  );
  return {
    study_id: "study_1",
    name: "Study",
    schema_version: 1,
    subjects,
    totals: { subjects: subjects.length, streams: 0, recordings },
  };
}

const twoSubjects = manager([
  {
    id: "sub_a",
    label: "S001",
    metadata: {},
    sessions: [{ id: "ses_a", name: "session-001", runs: [{ id: "run_a", name: "run-001", recordings: [rec("rec_a")] }] }],
  },
  {
    id: "sub_b",
    label: "S002",
    metadata: {},
    sessions: [{ id: "ses_b", name: "session-001", runs: [{ id: "run_b", name: "run-001", recordings: [rec("rec_b")] }] }],
  },
]);

test("flattenRecordings keeps each recording's own subject/session/run ids", () => {
  const rows = flattenRecordings(twoSubjects);
  assert.equal(rows.length, 2);
  const b = findRecording(twoSubjects, "rec_b");
  // Regression: attaching a stream to rec_b must use S002's ids, not the first subject's.
  assert.deepEqual(
    b && { subjectId: b.subjectId, sessionId: b.sessionId, runId: b.runId },
    { subjectId: "sub_b", sessionId: "ses_b", runId: "run_b" },
  );
  assert.equal(findRecording(twoSubjects, "missing"), null);
  assert.equal(findRecording(null, "rec_a"), null);
});

test("validateStudyName requires a non-empty name and warns on duplicates", () => {
  assert.equal(validateStudyName("   ", []).ok, false);
  assert.equal(validateStudyName("x".repeat(121), []).ok, false);
  assert.deepEqual(validateStudyName("Pilot", []), { ok: true });
  const dup = validateStudyName(" pilot ", [{ name: "Pilot" }]);
  assert.equal(dup.ok, true);
  assert.match(dup.warning ?? "", /already exists/);
});

test("validateSubjectLabel rejects empty and duplicate labels", () => {
  assert.equal(validateSubjectLabel("", []).ok, false);
  assert.equal(validateSubjectLabel("S001", [{ label: "S001" }]).ok, false);
  assert.equal(validateSubjectLabel("S002", [{ label: "S001" }]).ok, true);
});

test("parseMetadata accepts empty or JSON objects only", () => {
  assert.deepEqual(parseMetadata(""), { ok: true, value: {} });
  assert.deepEqual(parseMetadata('{"age": 24}'), { ok: true, value: { age: 24 } });
  assert.equal(parseMetadata("[1,2]").ok, false);
  assert.equal(parseMetadata("{bad").ok, false);
  assert.equal(parseMetadata("3").ok, false);
});

test("parsePositive never defaults a missing sampling rate", () => {
  assert.equal(parsePositive("", "Rate").ok, false);
  assert.equal(parsePositive("0", "Rate").ok, false);
  assert.equal(parsePositive("-5", "Rate").ok, false);
  assert.equal(parsePositive("abc", "Rate").ok, false);
  assert.deepEqual(parsePositive(" 250 ", "Rate"), { ok: true, value: 250 });
  assert.deepEqual(parsePositive("512.5", "Rate"), { ok: true, value: 512.5 });
});

test("validateSplitFractions keeps data for training", () => {
  assert.deepEqual(validateSplitFractions("0.15", "0.2"), { ok: true, val: 0.15, test: 0.2 });
  assert.equal(validateSplitFractions("0", "0.2").ok, true);
  assert.equal(validateSplitFractions("0.5", "0.5").ok, false);
  assert.equal(validateSplitFractions("0.1", "0").ok, false);
  assert.equal(validateSplitFractions("-0.1", "0.2").ok, false);
  assert.equal(validateSplitFractions("x", "0.2").ok, false);
});

test("validateSeed requires a non-negative integer", () => {
  assert.deepEqual(validateSeed("0"), { ok: true, value: 0 });
  assert.equal(validateSeed("").ok, false);
  assert.equal(validateSeed("1.5").ok, false);
  assert.equal(validateSeed("-1").ok, false);
});

test("newestFirst orders by created_at, undated items last in original order", () => {
  const items = [
    { id: "a", created_at: "2026-01-01T00:00:00Z" },
    { id: "u1" },
    { id: "b", created_at: "2026-03-01T00:00:00Z" },
    { id: "u2", created_at: null },
  ];
  assert.deepEqual(
    newestFirst(items).map((x) => x.id),
    ["b", "a", "u1", "u2"],
  );
});

test("action gates explain why they are unavailable", () => {
  assert.equal(importGate(true, true).ok, true);
  const offline = importGate(true, false);
  assert.equal(offline.ok, false);
  assert.equal(importGate(false, true).ok, false);

  assert.equal(trainGate(true, true, 1).ok, true);
  const noRec = trainGate(true, true, 0);
  assert.equal(noRec.ok, false);
  assert.match(noRec.ok ? "" : noRec.reason, /recording/);
});

test("nextStep reflects only data that exists", () => {
  assert.equal(nextStep(null).action, "create");
  assert.equal(nextStep(manager([])).action, "import");
  assert.equal(nextStep(twoSubjects).action, "inspect");
  assert.match(nextStep(twoSubjects).detail, /2 of 2/);
});

test("formatDuration", () => {
  assert.equal(formatDuration(null), "—");
  assert.equal(formatDuration(12.34), "12.3 s");
  assert.equal(formatDuration(125), "2 min 05 s");
});

import { isTrained, recentActivity } from "../src/lib/study.ts";

test("isTrained requires a backend model id, not just a model object", () => {
  // Regression: Experiment.model defaults to {} on the backend; the UI showed "trained" before training.
  assert.equal(isTrained({ model: {} }), false);
  assert.equal(isTrained({ model: null }), false);
  assert.equal(isTrained({}), false);
  assert.equal(isTrained(null), false);
  assert.equal(isTrained({ model: { model_id: "" } }), false);
  assert.equal(isTrained({ model: { model_id: "mdl_1" } }), true);
});

test("recentActivity uses only dated backend records, newest first", () => {
  const items = recentActivity(
    {
      epochsets: [{ created_at: "2026-01-02T00:00:00Z", name: "epochs", n_trials: 38 }],
      datasets: [{ created_at: "2026-01-03T00:00:00Z", name: "ds", n_samples: 38, n_features: 65 }],
      experiments: [
        { created_at: "2026-01-04T00:00:00Z", id: "exp_a", model: {} },
        { id: "exp_undated", model: { model_id: "m" } },
      ],
      plans: [{ created_at: "2026-01-01T00:00:00Z", name: "default" }],
    },
    3,
  );
  assert.deepEqual(
    items.map((i) => [i.kind, i.label, i.detail]),
    [
      ["Experiment", "exp_a", "not trained"],
      ["Dataset", "ds", "38 × 65"],
      ["Epochs", "epochs", "38 trials"],
    ],
  );
  assert.deepEqual(recentActivity({}), []);
});
