import { test } from "node:test";
import assert from "node:assert/strict";
import { flowStepStates, studioStepStates } from "../src/lib/workflow.ts";

const status = (steps: Array<{ id: string; status: string }>) => Object.fromEntries(steps.map((s) => [s.id, s.status]));

const flowBase = { studySelected: true, recordingSelected: true, recordingCount: 1, recordingEpochsets: 0, recordingResults: 0 };
const studioBase = { studySelected: true, epochsets: 1, hasAnySplit: false, trainedExperiments: 0 };

test("flow: nothing is available without a study", () => {
  const steps = flowStepStates({ ...flowBase, studySelected: false });
  assert.ok(steps.every((s) => s.status === "unavailable" && s.hint === "Create or choose a study first."));
});

test("flow: without a selected recording only Import is available, with a hint that depends on the study", () => {
  const empty = flowStepStates({ ...flowBase, recordingSelected: false, recordingCount: 0 });
  assert.deepEqual(status(empty), { recording: "available", inspect: "unavailable", plan: "unavailable", review: "unavailable" });
  assert.equal(empty[1].hint, "Import a recording first.");
  const unpicked = flowStepStates({ ...flowBase, recordingSelected: false, recordingCount: 2 });
  assert.equal(unpicked[1].hint, "Choose a recording first.");
});

test("flow: steps are done only when their saved output exists for the selected recording", () => {
  assert.deepEqual(status(flowStepStates(flowBase)), { recording: "done", inspect: "available", plan: "available", review: "available" });
  assert.deepEqual(status(flowStepStates({ ...flowBase, recordingEpochsets: 1, recordingResults: 2 })), {
    recording: "done",
    inspect: "available",
    plan: "done",
    review: "done",
  });
});

test("studio: Dataset needs epochs; Train needs a split", () => {
  assert.deepEqual(status(studioStepStates({ ...studioBase, epochsets: 0 })), { data: "unavailable", train: "unavailable", export: "available" });
  assert.equal(studioStepStates({ ...studioBase, epochsets: 0 })[0].hint, "Create epochs in NeuroFlow first.");
  assert.deepEqual(status(studioStepStates(studioBase)), { data: "available", train: "unavailable", export: "available" });
  assert.deepEqual(status(studioStepStates({ ...studioBase, hasAnySplit: true })), { data: "done", train: "available", export: "available" });
});

test("studio: Train is done only when a trained experiment exists", () => {
  assert.equal(status(studioStepStates({ ...studioBase, hasAnySplit: true, trainedExperiments: 0 })).train, "available");
  assert.equal(status(studioStepStates({ ...studioBase, hasAnySplit: true, trainedExperiments: 1 })).train, "done");
});

test("footer: Back from a first step goes Home; Next from NeuroFlow's last step opens NeuroStudio", async () => {
  const { stageNeighbors } = await import("../src/lib/workflow.ts");
  const at = (page: "flow" | "studio", flowStage: any, studioStage: any = "data") => stageNeighbors({ page, flowStage, studioStage });

  const first = at("flow", "recording");
  assert.equal(first.prev.label, "Home");
  assert.equal(first.prev.to.page, "home");
  assert.deepEqual([first.next?.label, first.next?.to.flowStage], ["Inspect", "inspect"]);

  const last = at("flow", "review", "export");
  assert.deepEqual([last.prev.label, last.prev.to.flowStage], ["Preprocess", "plan"]);
  assert.deepEqual([last.next?.label, last.next?.to.page, last.next?.to.studioStage], ["NeuroStudio", "studio", "data"]);

  const studioFirst = at("studio", "inspect", "data");
  assert.equal(studioFirst.prev.to.page, "home");
  assert.equal(studioFirst.prev.to.flowStage, "inspect", "the NeuroFlow step is remembered");
  assert.deepEqual([studioFirst.next?.label, studioFirst.next?.to.studioStage], ["Train", "train"]);

  assert.equal(at("studio", "inspect", "export").next, null);
  assert.deepEqual([at("studio", "inspect", "export").prev.label], ["Train"]);
});
