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
  settle,
  start,
  studySelect,
} from "./harness";

beforeEach(() => {
  freshBackend();
});

describe("study creation", () => {
  test("first study is created from the welcome form with trimmed name and task", async () => {
    await start();
    expect(screen.getByRole("heading", { name: "Create your first study" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/^Study name/), { target: { value: "  Oddball pilot  " } });
    fireEvent.change(screen.getByLabelText(/^Task or paradigm/), { target: { value: " oddball " } });
    await click(button("Create study"));

    const create = harness.backend.callsOf("studies.create");
    expect(create).toHaveLength(1);
    expect(create[0].params).toEqual({ name: "Oddball pilot", task_name: "oddball" });
    expect(screen.getByRole("heading", { name: "Oddball pilot" })).toBeTruthy();
    expect(studySelect().selectedOptions[0].text).toBe("Oddball pilot");
    expect(localStorage.getItem("nt-study")).toBe(harness.backend.studies[0].id);
  });

  test("an empty name is rejected before any backend call", async () => {
    await start();
    await click(button("Create study"));
    expect(screen.getByText("Enter a study name.")).toBeTruthy();
    expect(harness.backend.callsOf("studies.create")).toHaveLength(0);
  });

  test("creating a second study selects it and clears the previous recording", async () => {
    const b = harness.backend;
    const s1 = b.addStudy("First");
    b.addRecording(s1, b.addSubject(s1, "S001"));
    await start();
    // open the recording so it becomes active
    await click(screen.getByRole("row", { name: /Open S001/ }));
    expect(activeRecordingLabel()).toMatch(/^S001/);

    await nav("Home");
    await click(button("New study"));
    fireEvent.change(screen.getByLabelText(/^Study name/), { target: { value: "Second" } });
    await click(button("Create study"));

    expect(studySelect().selectedOptions[0].text).toBe("Second");
    expect(screen.getByRole("heading", { name: "Second" })).toBeTruthy();
    expect(activeRecordingLabel()).toBeNull();
  });

  test("a backend status error on create is shown and nothing is selected", async () => {
    harness.backend.statusErrors["studies.create"] = "disk full";
    await start();
    fireEvent.change(screen.getByLabelText(/^Study name/), { target: { value: "X" } });
    await click(button("Create study"));
    expect(document.querySelector(".notice-error .notice-title")?.textContent).toMatch(/^Creating study/);
    expect(document.querySelector(".notice-error")?.textContent).not.toMatch(/created/);
    expect(screen.getByRole("heading", { name: "Create your first study" })).toBeTruthy();
  });
});

describe("study switching and refresh", () => {
  test("switching study loads that study's manager and drops the active recording", async () => {
    const b = harness.backend;
    const a = b.addStudy("Alpha");
    b.addRecording(a, b.addSubject(a, "S001"));
    const z = b.addStudy("Zeta");
    b.addSubject(z, "Z-subject");
    await start();
    expect(studySelect().selectedOptions[0].text).toBe("Alpha");
    await click(screen.getByRole("row", { name: /Open S001/ }));
    expect(activeRecordingLabel()).not.toBeNull();

    await change(studySelect(), z.id);
    expect(studySelect().selectedOptions[0].text).toBe("Zeta");
    expect(activeRecordingLabel()).toBeNull();
    expect(b.callsOf("studies.manager").at(-1)?.params).toEqual({ study_id: z.id });
    await nav("Home");
    expect(screen.getByText("Z-subject")).toBeTruthy();
    expect(localStorage.getItem("nt-study")).toBe(z.id);
  });

  test("the stored study is reopened on launch", async () => {
    const b = harness.backend;
    b.addStudy("Alpha");
    const z = b.addStudy("Zeta");
    localStorage.setItem("nt-study", z.id);
    await start();
    expect(studySelect().selectedOptions[0].text).toBe("Zeta");
  });

  test("a stored study that no longer exists falls back to the first study", async () => {
    const b = harness.backend;
    b.addStudy("Alpha");
    localStorage.setItem("nt-study", "study_deleted");
    await start();
    expect(studySelect().selectedOptions[0].text).toBe("Alpha");
  });

  test("reload picks up studies and subjects created outside the UI", async () => {
    const b = harness.backend;
    const a = b.addStudy("Alpha");
    await start();
    b.addStudy("Created elsewhere");
    b.addSubject(a, "S009");
    await click(button("Reload from backend"));
    expect([...studySelect().options].map((o) => o.text)).toContain("Created elsewhere");
    expect(studySelect().selectedOptions[0].text).toBe("Alpha");
    expect(screen.getByText("S009")).toBeTruthy();
  });

  test("adding a subject refreshes the manager and clears the form", async () => {
    const b = harness.backend;
    b.addStudy("Alpha");
    await start();
    const label = screen.getByLabelText("New subject label") as HTMLInputElement;
    fireEvent.change(label, { target: { value: "S002" } });
    fireEvent.change(screen.getByLabelText("Metadata (JSON, optional)"), { target: { value: '{"age": 30}' } });
    await click(button("Add subject"));
    expect(b.callsOf("subjects.add")[0].params).toMatchObject({ label: "S002", metadata: { age: 30 } });
    expect(screen.getByText("S002")).toBeTruthy();
    expect(label.value).toBe("");
  });

  test("offline backend is reported and retry reconnects", async () => {
    const b = harness.backend;
    b.addStudy("Alpha");
    await start();
    b.transportErrors.health = "ipc connect: Connection refused (os error 61)";
    await click(button("Reload from backend"));
    expect(document.querySelector(".conn-offline")).toBeTruthy();
    expect(document.querySelector(".notice-error")).toBeTruthy();
    delete b.transportErrors.health;
    await click(button("Retry"));
    await settle();
    expect(document.querySelector(".conn-online")).toBeTruthy();
    expect(document.querySelector(".notice-error")).toBeNull();
  });
});
