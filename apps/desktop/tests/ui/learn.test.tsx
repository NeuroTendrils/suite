import { createElement } from "react";
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "../../src/App";
import { LearnPage } from "../../src/pages/learn/LearnPage";
import { button, click, fireEvent, freshBackend, nav, screen, start, waitFor } from "./harness";

const title = "NeuroLearn lessons and practice";
const bundle = () => ({ ok: true, json: async () => ({ app: "neurolearn", version: 1 }) });
let fetchBundle = vi.fn();

beforeEach(() => {
  freshBackend();
  fetchBundle = vi.fn().mockResolvedValue(bundle());
  vi.stubGlobal("fetch", fetchBundle);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function frame() {
  return await waitFor(() => screen.getByTitle(title) as HTMLIFrameElement);
}

function signal(target: HTMLIFrameElement, type: string, source: Window | null = target.contentWindow) {
  fireEvent(window, new MessageEvent("message", { source, data: { channel: "neurolearn-desktop", type } }));
}

describe("Learn in the desktop app", () => {
  test("lessons open without a study or an available research backend", async () => {
    const backend = freshBackend();
    backend.transportErrors.health = "Research backend is offline";
    render(createElement(App));
    await waitFor(() => screen.getByText("Backend offline"));
    await nav("Learn");
    const learner = await frame();
    expect(learner.getAttribute("src")).toBe("/learn/index.html?desktop=1");
    expect(screen.queryByText("Backend offline")).toBeNull();
    expect(screen.queryByLabelText("Active study")).toBeNull();
    signal(learner, "ready");
    expect(learner.getAttribute("aria-hidden")).toBe("false");
    expect(screen.queryByText("Loading Learn…")).toBeNull();
  });

  test("switching modules preserves the learner instance and active research recording", async () => {
    const backend = freshBackend();
    const study = backend.addStudy("EEG lab");
    backend.addRecording(study, backend.addSubject(study, "S001"));
    await start();
    await click(screen.getByRole("row", { name: /Open S001/ }));
    const recording = document.querySelector(".topbar-rec")?.getAttribute("title");
    await nav("Learn");
    const learner = await frame();
    signal(learner, "ready");
    await nav("NeuroFlow");
    expect(document.querySelector(".topbar-rec")?.getAttribute("title")).toBe(recording);
    expect(screen.getByRole("heading", { name: "Inspect signal" })).toBeTruthy();
    expect(learner.closest("section")?.hidden).toBe(true);
    await nav("Learn");
    expect(screen.getByTitle(title)).toBe(learner);
    expect(learner.closest("section")?.hidden).toBe(false);
    expect(fetchBundle).toHaveBeenCalledTimes(1);
  });

  test("a missing or invalid bundle shows recovery instead of embedding the Suite fallback", async () => {
    fetchBundle.mockResolvedValueOnce({ ok: true, json: async () => { throw new Error("HTML fallback"); } });
    render(createElement(LearnPage, { active: true }));
    await waitFor(() => screen.getByRole("alert"));
    expect(screen.queryByTitle(title)).toBeNull();
    await click(button("Reload Learn"));
    const learner = await frame();
    signal(learner, "ready");
    expect(learner.getAttribute("aria-hidden")).toBe("false");
  });

  test("startup messages from unrelated windows cannot mark the learner ready", async () => {
    render(createElement(LearnPage, { active: true }));
    const learner = await frame();
    signal(learner, "ready", window);
    expect(screen.getByText("Loading Learn…")).toBeTruthy();
    signal(learner, "ready");
    expect(screen.queryByText("Loading Learn…")).toBeNull();
  });

  test("engine startup errors can be retried with a fresh frame", async () => {
    render(createElement(LearnPage, { active: true }));
    const original = await frame();
    signal(original, "error");
    expect(screen.getByRole("alert")).toBeTruthy();
    await click(button("Reload Learn"));
    const replacement = await frame();
    expect(replacement).not.toBe(original);
    signal(replacement, "ready");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("a stalled load times out and cancels its pending request", async () => {
    vi.useFakeTimers();
    fetchBundle.mockImplementation(() => new Promise(() => {}));
    const view = render(createElement(LearnPage, { active: true }));
    await act(async () => { vi.advanceTimersByTime(30_000); });
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(fetchBundle.mock.calls[0][1].signal.aborted).toBe(true);
    view.unmount();
  });
});
