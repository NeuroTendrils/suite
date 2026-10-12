import { beforeEach, describe, expect, test } from "vitest";
import {
  activeRecordingLabel,
  button,
  change,
  click,
  fireEvent,
  freshBackend,
  harness,
  nav,
  screen,
  start,
  step,
  stepClasses,
} from "./harness";
import type { FakeBackend } from "./fakeBackend";

let b: FakeBackend;
beforeEach(() => {
  b = freshBackend();
});

function pathInput(): HTMLInputElement {
  return screen.getByPlaceholderText("/path/to/recording.fif") as HTMLInputElement;
}

async function inspectPath(path: string) {
  fireEvent.change(pathInput(), { target: { value: path } });
  await click(button("Inspect", pathInput().closest(".input-group") as HTMLElement));
}

function eegSubjectSelect(): HTMLSelectElement {
  return screen.getAllByLabelText(/^Subject/)[0] as HTMLSelectElement;
}

async function openImport() {
  await start();
  await nav("NeuroFlow");
  await step("Import");
}

describe("recording import", () => {
  test("importing into a new subject creates it and imports with the ids the backend returned", async () => {
    b.addStudy("Alpha");
    await openImport();
    await inspectPath("/data/s1.fif");
    expect(eegSubjectSelect().value).toBe("__new_subject__");
    await click(button("Import recording"));

    const add = b.callsOf("subjects.add");
    expect(add).toHaveLength(1);
    expect(add[0].params.label).toBe("S001");
    const sub = b.studies[0].subjects[0];
    expect(b.callsOf("import.recording")[0].params).toMatchObject({
      subject_id: sub.id,
      session_id: sub.sessions[0].id,
      run_id: sub.sessions[0].runs[0].id,
      path: "/data/s1.fif",
    });
    expect(activeRecordingLabel()).toMatch(/^S001 · ses-01\/run-01/);
    expect(stepClasses().Import).toBe("done");
    expect(document.querySelector(".notice-success .notice-title")?.textContent).toBe("Recording imported");
    // form is cleared for the next file
    expect(pathInput().value).toBe("");
  });

  test("a recording imported for a second subject becomes the active recording (not the first subject's)", async () => {
    const s = b.addStudy("Alpha");
    const s1 = b.addSubject(s, "S001");
    b.addRecording(s, s1);
    const s2 = b.addSubject(s, "S002");
    await start();
    // make S001's recording active first
    await click(screen.getByRole("row", { name: /Open S001/ }));
    expect(activeRecordingLabel()).toMatch(/^S001/);

    await step("Import");
    await inspectPath("/data/s2.fif");
    await change(eegSubjectSelect(), s2.id);
    await click(button("Import recording"));

    const params = b.callsOf("import.recording")[0].params;
    expect(params).toMatchObject({ subject_id: s2.id, session_id: s2.sessions[0].id, run_id: s2.sessions[0].runs[0].id });
    const newRecId = s2.sessions[0].runs[0].recordings[0].id;
    expect(activeRecordingLabel()).toMatch(/^S002/);
    expect(document.querySelector(".topbar-rec")?.getAttribute("title")).toContain(newRecId);
  });

  test("a new recording id is selected only after the study reloads (it is not dropped as stale)", async () => {
    b.addStudy("Alpha");
    await openImport();
    await inspectPath("/data/s1.fif");
    await click(button("Import recording"));
    const managerCalls = b.calls.map((c) => c.command);
    const importAt = managerCalls.indexOf("import.recording");
    expect(managerCalls.indexOf("studies.manager", importAt)).toBeGreaterThan(importAt);
    expect(activeRecordingLabel()).not.toBeNull();
  });

  test("attaching a stream to another subject's recording uses that recording's own subject/session/run", async () => {
    const s = b.addStudy("Alpha");
    b.addRecording(s, b.addSubject(s, "S001"));
    const s2 = b.addSubject(s, "S002");
    const r2 = b.addRecording(s, s2);
    harness.openPath = "/data/gyro.csv";
    await openImport();
    await click(screen.getAllByRole("button", { name: "Browse…" })[1]);
    await change(screen.getByLabelText(/^Attach to/), r2.id);
    await click(button("Import stream"));

    expect(b.callsOf("import.stream")[0].params).toMatchObject({
      subject_id: s2.id,
      session_id: s2.sessions[0].id,
      run_id: s2.sessions[0].runs[0].id,
      recording_id: r2.id,
      modality: "gyroscope",
      sfreq: 100,
    });
    expect(document.querySelector(".notice-error")).toBeNull();
    expect(document.querySelector(".topbar-rec")?.getAttribute("title")).toContain(r2.id);
  });

  test("formats without a stored sampling rate block import until one is entered", async () => {
    b.addStudy("Alpha");
    b.inspect["/data/x.txt"] = { format: "text", status: "needs_config", required_config: ["sfreq"], self_describing: false, columns: [] };
    await openImport();
    await inspectPath("/data/x.txt");
    expect(button("Import recording").disabled).toBe(true);
    expect(screen.getByText("Enter the sampling rate. It cannot be read from this file format.")).toBeTruthy();
    fireEvent.change(screen.getAllByLabelText(/^Sampling rate \(Hz\)/)[0], { target: { value: "512" } });
    expect(button("Import recording").disabled).toBe(false);
    await click(button("Import recording"));
    expect(b.callsOf("import.recording")[0].params.sfreq).toBe(512);
  });

  test("an unreadable file (error inside a successful reply) blocks import", async () => {
    b.addStudy("Alpha");
    b.inspect["/data/broken.edf"] = { format: "edf", status: "error", error: "header is corrupt" };
    await openImport();
    await inspectPath("/data/broken.edf");
    expect(document.querySelector(".notice-error")).toBeTruthy();
    expect(button("Import recording").disabled).toBe(true);
  });

  test("a failed import keeps the form and the previous selection", async () => {
    const s = b.addStudy("Alpha");
    b.addRecording(s, b.addSubject(s, "S001"));
    b.transportErrors["import.recording"] = "file vanished";
    await start();
    await click(screen.getByRole("row", { name: /Open S001/ }));
    const before = document.querySelector(".topbar-rec")?.getAttribute("title");
    await step("Import");
    await inspectPath("/data/s1.fif");
    await click(button("Import recording"));
    expect(document.querySelector(".notice-error .notice-title")?.textContent).toMatch(/^Importing recording/);
    expect(pathInput().value).toBe("/data/s1.fif");
    expect(document.querySelector(".topbar-rec")?.getAttribute("title")).toBe(before);
  });
});

describe("recording selection", () => {
  test("opening a Home row opens that recording in NeuroFlow → Inspect", async () => {
    const s = b.addStudy("Alpha");
    b.addRecording(s, b.addSubject(s, "S001"));
    const r2 = b.addRecording(s, b.addSubject(s, "S002"));
    await start();
    await click(screen.getByRole("row", { name: /Open S002/ }));
    expect(document.querySelector(".topbar-rec")?.getAttribute("title")).toContain(r2.id);
    expect(screen.getByRole("heading", { name: "Inspect signal" })).toBeTruthy();
    expect(b.callsOf("recordings.timeline").at(-1)?.params.recording_id).toBe(r2.id);
  });

  test("the recording picker switches the recording that commands run on", async () => {
    const s = b.addStudy("Alpha");
    const r1 = b.addRecording(s, b.addSubject(s, "S001"));
    const r2 = b.addRecording(s, b.addSubject(s, "S002"));
    await start();
    await click(screen.getByRole("row", { name: /Open S001/ }));
    await step("Preprocess");
    await change(document.querySelector(".picker select")!, r2.id);
    await click(button("Validate recording"));
    expect(b.callsOf("validate.recording")[0].params).toEqual({ study_id: s.id, recording_id: r2.id });
    expect(b.callsOf("validate.recording")[0].params.recording_id).not.toBe(r1.id);
  });
});
