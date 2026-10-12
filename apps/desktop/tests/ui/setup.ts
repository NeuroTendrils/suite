/** jsdom setup for UI tests. Only the two native boundaries are replaced:
 *  the Tauri IPC bridge (→ FakeBackend) and the dialog plugin (→ scripted answers). */
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { harness } from "./harness";

vi.mock("../../src/ipc", () => ({
  suiteCall: (command: string, params: Record<string, unknown> = {}) => harness.backend.call(command, params),
  waitForSuiteRuntime: async () => {},
}));

vi.mock("@tauri-apps/plugin-dialog", () => ({
  ask: async (message: string) => {
    harness.dialogs.push(message);
    return harness.dialogAnswer;
  },
  open: async () => harness.openPath,
}));

// jsdom lacks layout APIs the app touches.
class ResizeObserverStub {
  observe() {}
  disconnect() {}
  unobserve() {}
}
(globalThis as any).ResizeObserver ??= ResizeObserverStub;
Element.prototype.scrollTo ??= function () {};
Element.prototype.scrollIntoView ??= function () {};

afterEach(() => {
  cleanup();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});
