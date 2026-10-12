import { beforeEach, describe, expect, test } from "vitest";
import { button, click, fireEvent, freshBackend, nav, screen, start, step, stepClasses } from "./harness";
import type { FakeBackend, FakeStudy } from "./fakeBackend";

let b: FakeBackend;
let s: FakeStudy;
beforeEach(() => {
  b = freshBackend();
  s = b.addStudy("Alpha");
});

const heading = () => document.querySelector(".module-title h1")?.textContent ?? null;

describe("navigation", () => {
  test("NeuroFlow without a recording opens on Import; with one it skips to Inspect", async () => {
    b.addRecording(s, b.addSubject(s, "S001"));
    await start();
    await nav("NeuroFlow");
    expect(heading()).toBe("Import recording");
    expect(stepClasses()).toMatchObject({ Import: "available", Inspect: "unavailable" });

    await nav("Home");
    await click(screen.getByRole("row", { name: /Open S001/ }));
    await nav("Home");
    await nav("NeuroFlow");
    expect(heading()).toBe("Inspect signal");
  });

  test("footer moves through the steps and on to NeuroStudio", async () => {
    b.addRecording(s, b.addSubject(s, "S001"));
    await start();
    await click(screen.getByRole("row", { name: /Open S001/ }));
    expect(heading()).toBe("Inspect signal");
    await click(button(/^Preprocess/, document.querySelector(".stage-footer") as HTMLElement));
    expect(heading()).toBe("Align, validate, and preprocess");
    await click(button(/^Analyze/, document.querySelector(".stage-footer") as HTMLElement));
    expect(heading()).toBe("Features and statistics");
    await click(button(/^NeuroStudio/, document.querySelector(".stage-footer") as HTMLElement));
    expect(heading()).toBe("Datasets and splits");
    await click(button(/^Home/, document.querySelector(".stage-footer") as HTMLElement));
    expect(screen.getByRole("heading", { name: "Alpha" })).toBeTruthy();
  });

  test("the topbar recording chip returns to Inspect from elsewhere", async () => {
    b.addRecording(s, b.addSubject(s, "S001"));
    await start();
    await click(screen.getByRole("row", { name: /Open S001/ }));
    await nav("NeuroStudio");
    await click(document.querySelector(".topbar-rec")!);
    expect(heading()).toBe("Inspect signal");
  });

  test("Home's next step opens the first unvalidated recording", async () => {
    const sub = b.addSubject(s, "S001");
    b.addRecording(s, sub, { validation_ok: true });
    const r2 = b.addRecording(s, b.addSubject(s, "S002"));
    await start();
    await click(button("Open in NeuroFlow"));
    expect(document.querySelector(".topbar-rec")?.getAttribute("title")).toContain(r2.id);
  });

  test("NeuroFlow without any study offers to create one in place", async () => {
    b.studies = [];
    await start();
    await nav("NeuroFlow");
    expect(screen.getByText("Create a study first")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/^Study name/), { target: { value: "Inline" } });
    await click(button("Create study"));
    expect(heading()).toBe("Import recording");
    expect(document.querySelector(".topbar-study select")).toBeTruthy();
  });
});

describe("state persistence", () => {
  test("theme and sidebar choices survive a restart", async () => {
    const first = await start();
    expect(document.documentElement.dataset.theme).toBe("dark");
    await click(button("Switch to light theme"));
    await click(button("Collapse navigation"));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("nt-theme")).toBe("light");
    expect(localStorage.getItem("nt-sidebar")).toBe("0");
    first.unmount();

    await start();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(button("Expand navigation")).toBeTruthy();
  });

  test("a typed import path is kept when leaving and returning to Import", async () => {
    await start();
    await nav("NeuroFlow");
    fireEvent.change(screen.getByPlaceholderText("/path/to/recording.fif"), { target: { value: "/data/keep.fif" } });
    await nav("Home");
    await nav("NeuroFlow");
    expect((screen.getByPlaceholderText("/path/to/recording.fif") as HTMLInputElement).value).toBe("/data/keep.fif");
  });

  test("the selected NeuroStudio step is kept across pages", async () => {
    await start();
    await nav("NeuroStudio");
    await step("Report & export");
    await nav("Home");
    await nav("NeuroStudio");
    expect(heading()).toBe("Reports and export");
  });
});
