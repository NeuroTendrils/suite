import { beforeEach, describe, expect, test } from "vitest";
import { button, change, click, freshBackend, nav, screen, start, step, stepClasses, within } from "./harness";
import type { FakeBackend, FakeStudy } from "./fakeBackend";

let b: FakeBackend;
let s: FakeStudy;
let recId: string;
beforeEach(() => {
  b = freshBackend();
  s = b.addStudy("Alpha");
  recId = b.addRecording(s, b.addSubject(s, "S001")).id;
});

/** Study with epochs → dataset → split → one experiment (trained or not). */
function seedExperiment(model: { model_id?: string } | null) {
  b.addEpochset(s, recId);
  const ds = b.addDataset(s);
  const sp = b.addSplit(s, ds.id);
  const x = b.addExperiment(s, ds.id, sp.id, model);
  return { ds, sp, x };
}

function experimentRow(id: string): HTMLElement {
  return screen.getByRole("radio", { name: `Select ${id}` }).closest("tr") as HTMLElement;
}

function pipelineStat(label: string): string {
  const dt = [...document.querySelectorAll(".pipeline dt")].find((d) => d.textContent === label)!;
  return dt.nextElementSibling!.textContent!.trim();
}

async function openTrain() {
  await start();
  await nav("NeuroStudio");
  await step("Train");
}

describe("training status detection", () => {
  test("an experiment whose model is an empty object is NOT trained", async () => {
    const { x } = seedExperiment({});
    await openTrain();
    expect(within(experimentRow(x.id)).getByText("not trained")).toBeTruthy();
    expect(button("Evaluate").disabled).toBe(true);
    expect(button("Infer").disabled).toBe(true);
    expect(button("Train model")).toBeTruthy();
    expect(stepClasses().Train).toBe("available");
    expect(screen.getByText("Evaluate, Explain, and Infer need a trained model. Train this experiment first.")).toBeTruthy();
  });

  test("an experiment with a model id is trained and unlocks evaluation", async () => {
    const { x } = seedExperiment({ model_id: "m1" });
    await openTrain();
    expect(within(experimentRow(x.id)).getByText("trained")).toBeTruthy();
    expect(button("Evaluate").disabled).toBe(false);
    expect(button("Retrain model")).toBeTruthy();
    expect(stepClasses().Train).toBe("done");
  });

  test("Home counts only experiments with a model id as trained", async () => {
    seedExperiment({});
    const ds = s.datasets[0];
    b.addExperiment(s, ds.id, s.splits[0].id, { model_id: "m2" });
    b.addExperiment(s, ds.id, s.splits[0].id, null);
    await start();
    expect(pipelineStat("Experiments")).toBe("3");
    expect(pipelineStat("Trained")).toBe("1");
  });

  test("training marks the selected experiment trained after the list reloads", async () => {
    const { x } = seedExperiment({});
    await openTrain();
    await click(button("Train model"));
    expect(b.callsOf("neurostudio.train.start")[0].params).toEqual({ study_id: s.id, experiment_id: x.id });
    expect(within(experimentRow(x.id)).getByText("trained")).toBeTruthy();
    expect(button("Evaluate").disabled).toBe(false);
  });

  test("an evaluation error returned inside a successful reply is shown as a failure", async () => {
    seedExperiment({ model_id: "m1" });
    b.statusErrors["neurostudio.eval.run"] = "model file is missing";
    await openTrain();
    await click(button("Evaluate"));
    expect(document.querySelector(".notice-error .notice-title")?.textContent).toMatch(/^Evaluating on test split/);
    expect(document.querySelector(".notice-success")).toBeNull();
    expect(document.querySelector(".metrics")).toBeNull();
  });

  test("a successful evaluation shows metrics for the selected experiment", async () => {
    seedExperiment({ model_id: "m1" });
    await openTrain();
    await click(button("Evaluate"));
    expect(document.querySelector(".metrics")).toBeTruthy();
    expect(screen.getByText("Confusion matrix (rows: true, columns: predicted)")).toBeTruthy();
  });
});

describe("prerequisite detection", () => {
  test("without epochs the Dataset and Train steps explain what is missing", async () => {
    await start();
    await nav("NeuroStudio");
    expect(screen.getByText("No epochs in this study yet")).toBeTruthy();
    const steps = [...document.querySelectorAll(".stepper .step button")].map((x) => x.getAttribute("title"));
    expect(steps[0]).toContain("Create epochs in NeuroFlow first.");
    expect(steps[1]).toContain("Build a dataset and create a split first.");
    expect(stepClasses()).toMatchObject({ Dataset: "unavailable", Train: "unavailable" });
  });

  test("a dataset with a split completes the Dataset step and opens Train", async () => {
    b.addEpochset(s, recId);
    b.addSplit(s, b.addDataset(s).id);
    await start();
    await nav("NeuroStudio");
    expect(stepClasses()).toMatchObject({ Dataset: "done", Train: "available" });
  });

  test("Create experiment is blocked until the selected dataset has a split", async () => {
    b.addEpochset(s, recId);
    b.addDataset(s);
    await openTrain();
    expect(button("Create experiment").disabled).toBe(true);
    expect(screen.getByText("Create a split for this dataset first.")).toBeTruthy();
  });
});

describe("dataset, split and experiment selection", () => {
  test("defaults follow the newest dataset and its split; experiments use the selection", async () => {
    b.addEpochset(s, recId);
    const d1 = b.addDataset(s, "older");
    const s1 = b.addSplit(s, d1.id);
    const d2 = b.addDataset(s, "newer");
    const s2 = b.addSplit(s, d2.id);
    await start();
    await nav("NeuroStudio");
    expect((screen.getByRole("radio", { name: "Select newer" }) as HTMLInputElement).checked).toBe(true);

    await step("Train");
    await click(button("Create experiment"));
    expect(b.callsOf("neurostudio.experiments.create")[0].params).toMatchObject({
      input_artifact_id: d2.id,
      split_definition: { split_id: s2.id },
    });

    await step("Dataset");
    await click(screen.getByRole("radio", { name: "Select older" }).closest("tr")!);
    await step("Train");
    await click(button("Create experiment"));
    expect(b.callsOf("neurostudio.experiments.create")[1].params).toMatchObject({
      input_artifact_id: d1.id,
      split_definition: { split_id: s1.id },
    });
  });

  test("building a dataset and creating a split select the new items", async () => {
    const e = b.addEpochset(s, recId);
    b.addDataset(s, "existing");
    await start();
    await nav("NeuroStudio");
    await click(button("Build dataset"));
    expect(b.callsOf("datasets.build")[0].params).toMatchObject({ epochset_id: e.id, recording_id: recId, source: "epochs" });
    const built = s.datasets.at(-1)!;
    expect((screen.getByRole("radio", { name: `Select ${built.name}` }) as HTMLInputElement).checked).toBe(true);

    await click(button("Create split"));
    expect(b.callsOf("datasets.splits.create")[0].params).toMatchObject({ dataset_id: built.id, method: "subject", val_frac: 0.15, test_frac: 0.2, seed: 0 });
  });

  test("clicking an older experiment makes training target it", async () => {
    const { ds, sp, x: older } = seedExperiment({});
    b.addExperiment(s, ds.id, sp.id, {});
    await openTrain();
    await click(experimentRow(older.id));
    await click(button("Train model"));
    expect(b.callsOf("neurostudio.train.start")[0].params.experiment_id).toBe(older.id);
  });

  test("invalid split fractions block split creation", async () => {
    b.addEpochset(s, recId);
    b.addDataset(s);
    await start();
    await nav("NeuroStudio");
    await change(screen.getByLabelText(/^Test fraction/), "0.9");
    expect(button("Create split").disabled).toBe(true);
    expect(screen.getByText("Validation + test must leave data for training (sum below 1).")).toBeTruthy();
  });
});

describe("preprocessing plan selection", () => {
  test("the newest plan is preselected; choosing another runs that plan", async () => {
    const older = b.addPlan(s, "older plan");
    b.addPlan(s, "newer plan");
    await start();
    await click(screen.getByRole("row", { name: /Open S001/ }));
    await step("Preprocess");
    const select = screen.getByLabelText(/^Plan/) as HTMLSelectElement;
    expect(select.selectedOptions[0].text).toMatch(/^newer plan/);
    await change(select, older.id);
    await click(button("Run on this recording"));
    expect(b.callsOf("plans.execute")[0].params).toEqual({ study_id: s.id, recording_id: recId, plan_id: older.id });
  });

  test("creating the default plan selects it", async () => {
    b.addPlan(s, "older plan");
    await start();
    await click(screen.getByRole("row", { name: /Open S001/ }));
    await step("Preprocess");
    await click(button("Create default plan"));
    const created = s.plans.at(-1)!;
    expect((screen.getByLabelText(/^Plan/) as HTMLSelectElement).value).toBe(created.id);
  });

  test("creating epochs marks the Preprocess step done", async () => {
    await start();
    await click(screen.getByRole("row", { name: /Open S001/ }));
    await step("Preprocess");
    expect(stepClasses().Preprocess).toBe("available");
    await click(screen.getAllByRole("button", { name: "Create epochs" })[0]);
    expect(b.callsOf("epochs.create")[0].params).toMatchObject({ tmin: -0.2, tmax: 0.8, recording_id: recId });
    expect(stepClasses().Preprocess).toBe("done");
  });
});
