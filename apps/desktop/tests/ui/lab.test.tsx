import { beforeEach, describe, expect, test } from "vitest";
import { button, click, fireEvent, freshBackend, harness, nav, screen, settle, start, within } from "./harness";

beforeEach(() => {
  freshBackend();
});

const radio = (name: RegExp) => screen.getByRole("radio", { name }) as HTMLInputElement;
const slider = (name: RegExp) => screen.getByRole("slider", { name }) as HTMLInputElement;
const verdict = () => document.querySelector(".lab-verdict")?.textContent ?? null;

async function openLab() {
  await start();
  await nav("BCI Lab");
}

async function confirmSafety() {
  const box = screen.getByRole("group", { name: /Before connecting or moving/ });
  for (const cb of within(box).getAllByRole("checkbox")) await click(cb);
}

/** A clean, confident simulated trial with a one-prediction gate. */
async function approvedSimulatedPrediction() {
  fireEvent.change(slider(/Sensor noise/), { target: { value: "0" } });
  fireEvent.change(slider(/Confidence threshold/), { target: { value: "0.6" } });
  fireEvent.change(screen.getByRole("combobox", { name: "Agreeing predictions needed" }), { target: { value: "1" } });
  await click(button("Generate simulated trial"));
}

async function connectAndArm() {
  await confirmSafety();
  await click(button("Connect"));
  await click(button("Enable motion"));
}

describe("BCI Lab", () => {
  test("defaults to clearly labelled simulated EEG, and live EEG is unavailable", async () => {
    await openLab();
    expect(radio(/Simulated EEG/).checked).toBe(true);
    expect(radio(/Live EEG/).disabled).toBe(true);
    expect(document.querySelector(".lab-source")?.textContent).toContain("Data source: Simulated EEG");
    expect(document.querySelector(".lab-source")?.textContent).toContain("Not a measurement");
  });

  test("a simulated trial produces a prediction, probabilities, and gate checks", async () => {
    await openLab();
    await approvedSimulatedPrediction();
    expect(screen.getByLabelText("Predicted probability per class").querySelectorAll("li")).toHaveLength(2);
    expect(screen.getByLabelText("Safety gate checks").querySelectorAll("li")).toHaveLength(4);
    expect(verdict()).toMatch(/^Approved: Turn base (left|right)$/);
  });

  test("connecting is blocked until every safety item is confirmed, and sends no movement", async () => {
    await openLab();
    expect(button("Connect").disabled).toBe(true);
    await confirmSafety();
    await click(button("Connect"));
    const [connect] = harness.robot.callsOf("robot_connect");
    expect(connect.args).toEqual({ target: { kind: "serial", port: "/dev/cu.usbserial-0001" }, operatorConfirmedSafe: true });
    expect(harness.robot.callsOf("robot_preset")).toHaveLength(0);
    expect(harness.robot.callsOf("robot_decoder_command")).toHaveLength(0);
    expect(screen.getByText("connected")).toBeTruthy();
  });

  test("an approved prediction moves the arm once, only after motion is enabled", async () => {
    await openLab();
    await approvedSimulatedPrediction();
    expect(button("Send approved command to arm").disabled).toBe(true);
    await connectAndArm();
    const send = button("Send approved command to arm");
    expect(send.disabled).toBe(false);
    await click(send);
    const calls = harness.robot.callsOf("robot_decoder_command");
    expect(calls).toHaveLength(1);
    expect(calls[0].args.source).toBe("simulated");
    expect(calls[0].args.threshold).toBe(0.6);
    expect(calls[0].args.confidence).toBeGreaterThanOrEqual(0.6);
    expect(["turn_left", "turn_right"]).toContain(calls[0].args.command);
    expect(button("Send approved command to arm").disabled).toBe(true);
    expect(screen.getByText(/Already sent/)).toBeTruthy();
  });

  test("a rejected prediction cannot be sent", async () => {
    await openLab();
    await connectAndArm();
    await approvedSimulatedPrediction();
    // Unmap the predicted class: the gate must reject it.
    for (const sel of screen.getAllByRole("combobox", { name: /Command for/ })) {
      fireEvent.change(sel, { target: { value: "none" } });
    }
    await settle();
    expect(verdict()).toMatch(/^Rejected/);
    expect(button("Send approved command to arm").disabled).toBe(true);
  });

  test("emergency stop is on the lab and in the top bar while connected, and latches", async () => {
    await openLab();
    await connectAndArm();
    await click(button("E-STOP arm"));
    expect(harness.robot.callsOf("robot_estop")).toHaveLength(1);
    expect(screen.getByText("emergency stop latched")).toBeTruthy();
    expect(button("Turn base left").disabled).toBe(true);
    // The safety list resets, so clearing the stop requires confirming again.
    expect(button("Clear emergency stop").disabled).toBe(true);
    await confirmSafety();
    await click(button("Clear emergency stop"));
    expect(harness.robot.callsOf("robot_clear_estop")[0].args.operatorConfirmedSafe).toBe(true);
    expect(button("Enable motion")).toBeTruthy();
    await nav("Home");
    expect(button("E-STOP arm")).toBeTruthy();
  });

  test("a freshly loaded UI disables motion the driver may still have enabled", async () => {
    harness.robot.state = "connected";
    harness.robot.armed = true; // e.g. left over from before a webview reload
    await openLab();
    expect(harness.robot.calls[0].command).toBe("robot_disarm");
    expect(harness.robot.armed).toBe(false);
    expect(button("Turn base left").disabled).toBe(true);
  });

  test("the robot panel says plainly that commands move the real arm", async () => {
    await openLab();
    expect(screen.getByText(/There is no simulated arm/)).toBeTruthy();
    expect(screen.getByText(/real emergency stop/)).toBeTruthy();
  });

  test("the lab's emergency stop works even when nothing is connected", async () => {
    await openLab();
    await click(button("EMERGENCY STOP"));
    expect(harness.robot.callsOf("robot_estop")).toHaveLength(1);
  });

  test("a lost connection is reported with its reason and disables motion controls", async () => {
    await openLab();
    await connectAndArm();
    harness.robot.loseConnection();
    // The lab polls driver status every 500 ms.
    await new Promise((r) => setTimeout(r, 700));
    await settle();
    expect(screen.getByText("connection lost")).toBeTruthy();
    expect(screen.getByText(/No feedback from the arm 3 times in a row/)).toBeTruthy();
    expect(button("Connect").disabled).toBe(true);
  });

  test("connection errors are shown, not swallowed", async () => {
    await openLab();
    harness.robot.connectError = "/dev/cu.usbserial-0001 did not answer the RoArm-M2-S feedback query: unsupported firmware";
    await confirmSafety();
    await click(button("Connect"));
    expect(screen.getByRole("alert").textContent).toContain("unsupported firmware");
  });

  test("prerecorded mode runs the study's model on held-out trials and maps nothing by default", async () => {
    const backend = freshBackend();
    const study = backend.addStudy("Motor imagery");
    const ds = backend.addDataset(study, "mi-dataset");
    const split = backend.addSplit(study, ds.id);
    backend.addExperiment(study, ds.id, split.id, { model_id: "m1" });
    await openLab();
    await click(radio(/Prerecorded EEG/));
    expect(document.querySelector(".lab-source")?.textContent).toContain("Not happening in real time");
    await click(button("Run model on held-out trials"));
    const [infer] = backend.callsOf("neurostudio.infer.run");
    expect(infer.params.split).toBe("test");
    expect(screen.getByText(/Trial 1 of 3/)).toBeTruthy();
    expect(verdict()).toMatch(/^Rejected/);
    expect(screen.getByText(/“A” is not mapped to any movement/)).toBeTruthy();
    await click(button("Next trial"));
    expect(screen.getByText(/wrong: true label A/)).toBeTruthy();
  });
});
