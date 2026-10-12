import { act, render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import { createElement } from "react";
import App from "../../src/App";
import { FakeBackend } from "./fakeBackend";

/** Shared mutable state read by the mocks in setup.ts. Reset by `start()`. */
export const harness = {
  backend: new FakeBackend(),
  dialogs: [] as string[],
  dialogAnswer: true,
  openPath: null as string | null,
};

export function freshBackend(): FakeBackend {
  harness.backend = new FakeBackend();
  harness.dialogs = [];
  harness.dialogAnswer = true;
  harness.openPath = null;
  return harness.backend;
}

/** Render the real App against the current fake backend and wait until it is online. */
export async function start() {
  const utils = render(createElement(App));
  await waitFor(() => {
    if (!document.querySelector(".conn-online")) throw new Error("backend not online yet");
  });
  await settle();
  return utils;
}

/** Let pending backend replies and effects flush. */
export async function settle() {
  const tick = () => act(() => new Promise<void>((r) => setTimeout(r, 2)));
  let quiet = 0;
  for (let i = 0; i < 500 && quiet < 3; i++) {
    await tick();
    quiet = harness.backend.inflight === 0 ? quiet + 1 : 0;
  }
}

export function button(name: string | RegExp, root: HTMLElement = document.body): HTMLButtonElement {
  return within(root).getByRole("button", { name }) as HTMLButtonElement;
}

export async function click(el: Element) {
  fireEvent.click(el);
  await settle();
}

export async function nav(label: "Home" | "NeuroFlow" | "NeuroStudio") {
  const rail = screen.getByRole("navigation", { name: "Main" });
  await click(within(rail).getByText(label).closest("button")!);
}

export async function step(label: string) {
  const stepper = document.querySelector(".stepper")!;
  await click(within(stepper as HTMLElement).getByText(label).closest("button")!);
}

export function studySelect(): HTMLSelectElement {
  return document.querySelector(".topbar-study select") as HTMLSelectElement;
}

export function activeRecordingLabel(): string | null {
  return document.querySelector(".topbar-rec-name")?.textContent ?? null;
}

export function noticeTitle(kind?: "error" | "success" | "info" | "warn"): string | null {
  const sel = kind ? `.notice-${kind} .notice-title` : ".notice .notice-title";
  return document.querySelector(sel)?.textContent ?? null;
}

export function stepClasses(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const li of document.querySelectorAll(".stepper .step")) {
    const label = li.querySelector(".step-label")?.textContent ?? "";
    const status = /step-(done|available|unavailable)/.exec(li.className)?.[1] ?? "";
    out[label] = status;
  }
  return out;
}

export async function change(el: Element, value: string) {
  fireEvent.change(el, { target: { value } });
  await settle();
}

export { screen, waitFor, within, fireEvent };
