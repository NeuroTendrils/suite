import { beforeEach, describe, expect, test } from "vitest";
import { button, click, fireEvent, freshBackend, screen, settle, start, step } from "./harness";
import type { FakeBackend, FakeStudy } from "./fakeBackend";

let b: FakeBackend;
let s: FakeStudy;
beforeEach(() => {
  b = freshBackend();
  s = b.addStudy("Alpha");
  b.addRecording(s, b.addSubject(s, "S001"));
});

async function openPreprocess() {
  await start();
  await click(screen.getByRole("row", { name: /Open S001/ }));
  await step("Preprocess");
}

describe("duplicate operation prevention", () => {
  test("repeated clicks while an operation runs send it once and lock other actions", async () => {
    await openPreprocess();
    const release = b.hold("validate.recording");
    const validate = button("Validate recording");
    fireEvent.click(validate);
    fireEvent.click(validate);
    fireEvent.click(validate);
    await settle();

    expect(b.callsOf("validate.recording")).toHaveLength(1);
    expect(validate.disabled).toBe(true);
    expect(button("Validate study").disabled).toBe(true);
    expect(button("Reload from backend").disabled).toBe(true);
    expect(document.querySelector(".busy")?.textContent).toMatch(/Validating recording/);
    expect(document.querySelector(".step.running")).toBeTruthy();

    release();
    await settle();
    expect(document.querySelector(".busy")).toBeNull();
    expect(validate.disabled).toBe(false);
    expect(document.querySelector(".notice-success .notice-title")?.textContent).toMatch(/^Validation passed/);
    expect(b.callsOf("validate.recording")).toHaveLength(1);
  });

  test("a second operation started programmatically while busy is refused with a notice", async () => {
    await openPreprocess();
    const release = b.hold("validate.recording");
    fireEvent.click(button("Validate recording"));
    await settle();
    // Submitting the event form bypasses the disabled button.
    fireEvent.submit(button("Add event").closest("form")!);
    await settle();
    expect(b.callsOf("events.create")).toHaveLength(0);
    expect(document.querySelector(".notice-info .notice-title")?.textContent).toBe("Another operation is still running");
    release();
    await settle();
  });

  test("the busy lock is released after a failure", async () => {
    b.transportErrors["validate.recording"] = "boom";
    await openPreprocess();
    await click(button("Validate recording"));
    expect(document.querySelector(".notice-error")).toBeTruthy();
    expect(document.querySelector(".busy")).toBeNull();
    expect(button("Validate recording").disabled).toBe(false);
  });
});

describe("backend failures inside successful replies", () => {
  test("a {status:'error'} reply is reported as a failure with its message", async () => {
    b.statusErrors["validate.recording"] = "recording file unreadable";
    await openPreprocess();
    await click(button("Validate recording"));
    const notice = document.querySelector(".notice-error")!;
    expect(notice.querySelector(".notice-title")?.textContent).toMatch(/^Validating recording/);
    await click(screen.getByRole("button", { name: "Technical details" }));
    expect(notice.textContent).toContain("recording file unreadable");
    expect(screen.queryByText("Full validation report")).toBeNull();
    expect(screen.getByText("Not validated yet.")).toBeTruthy();
  });

  test("a {status:'not_implemented'} reply is a failure too", async () => {
    b.handlers["plans.default"] = () => ({ status: "not_implemented" });
    await openPreprocess();
    await click(button("Create default plan"));
    expect(document.querySelector(".notice-error .notice-title")?.textContent).toMatch(/^Creating default plan/);
    expect(document.querySelector(".notice-success")).toBeNull();
  });

  test("a failure is written to the activity log", async () => {
    b.statusErrors["validate.recording"] = "nope";
    await openPreprocess();
    await click(button("Validate recording"));
    await click(document.querySelector(".activity-toggle")!);
    expect(document.querySelector(".activity")?.textContent).toMatch(/Validating recording failed/);
  });
});
