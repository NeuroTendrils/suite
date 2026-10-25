import { beforeEach, expect, test } from "vitest";
import { button, change, click, fireEvent, freshBackend, nav, screen, start, step, settle, studySelect } from "./harness";
import type { FakeBackend } from "./fakeBackend";

let backend: FakeBackend;
beforeEach(() => { backend = freshBackend(); });

async function openImport() {
  backend.addStudy("Insight study");
  await start();
  await nav("NeuroFlow");
  await step("Import");
}

test("Insight capture requires consent, validates duration and stages a 128 Hz import", async () => {
  await openImport();
  const capture = button("Capture Insight EEG");
  expect(capture.disabled).toBe(true);
  await click(screen.getByRole("checkbox", { name: /I consent to local EEG storage/ }));
  await change(screen.getByLabelText(/Capture duration/), "1");
  expect(capture.disabled).toBe(true);
  await change(screen.getByLabelText(/Capture duration/), "2");
  expect(capture.disabled).toBe(false);
  const release = backend.hold("insight.capture");
  fireEvent.click(capture);
  await settle();
  expect(studySelect().disabled).toBe(true);
  expect(capture.disabled).toBe(true);
  release();
  await settle();
  expect(backend.callsOf("insight.capture")[0].params).toMatchObject({ seconds: 2, consent_to_record: true });
  expect((screen.getAllByLabelText(/Sampling rate \(Hz\)/)[0] as HTMLInputElement).value).toBe("128");
  expect((screen.getByRole("checkbox", { name: /I consent to local EEG storage/ }) as HTMLInputElement).checked).toBe(false);
  expect(button("Import recording").disabled).toBe(false);
});

test("capture failure is shown and preserves the form for retry", async () => {
  await openImport();
  backend.statusErrors["insight.capture"] = "Approve the app in EMOTIV Launcher";
  await click(screen.getByRole("checkbox", { name: /I consent to local EEG storage/ }));
  await click(button("Capture Insight EEG"));
  expect(document.querySelector(".notice-error")?.textContent).toContain("Approve the app");
  expect(button("Capture Insight EEG").disabled).toBe(false);
  expect(button("Import recording").disabled).toBe(true);
});

test("export defaults to a redacted summary and resets raw-data consent", async () => {
  const study = backend.addStudy("Study");
  const dataset = backend.addDataset(study);
  const split = backend.addSplit(study, dataset.id);
  backend.addExperiment(study, dataset.id, split.id, { model_id: "m" });
  await start();
  await nav("NeuroStudio");
  await step("Report & export");
  const redact = screen.getByRole("checkbox", { name: /Redact identifying metadata/ }) as HTMLInputElement;
  const data = screen.getByRole("checkbox", { name: /Include data and binaries/ }) as HTMLInputElement;
  expect(redact.checked).toBe(true);
  expect(data.disabled).toBe(true);
  await click(button("Export study package"));
  expect(backend.callsOf("study.export")[0].params).toMatchObject({ deidentify: true, include_samples: false });
  await click(redact);
  await click(data);
  expect(data.checked).toBe(true);
  await click(redact);
  expect(data.checked).toBe(false);
  expect(data.disabled).toBe(true);
});
