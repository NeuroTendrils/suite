import { beforeEach, describe, expect, test } from "vitest";
import { button, change, click, fireEvent, freshBackend, harness, nav, screen, settle, start, step, studySelect } from "./harness";
import type { FakeBackend, FakeStudy } from "./fakeBackend";

let b: FakeBackend;
let s: FakeStudy;
beforeEach(() => {
  b = freshBackend();
  s = b.addStudy("Alpha");
});

function channelLabel(name: string): SVGTextElement {
  const el = [...document.querySelectorAll("svg.eegplot text")].find(
    (t) => t.textContent === name || t.textContent === `×${name}`,
  );
  if (!el) throw new Error(`no channel label ${name}`);
  return el as SVGTextElement;
}

const marksText = () => document.querySelector(".marks-count")?.textContent ?? "";
const topbarBadge = () => document.querySelector(".topbar .badge-warn")?.textContent ?? null;

async function openInspect(label = "S001") {
  await start();
  await click(screen.getByRole("row", { name: new RegExp(`Open ${label}`) }));
  await settle();
}

describe("pending rejection marks", () => {
  test("clicking a channel marks it pending; apply writes it and clears the mark", async () => {
    const rec = b.addRecording(s, b.addSubject(s, "S001"));
    await openInspect();
    await click(channelLabel("Fz"));
    expect(marksText()).toMatch(/1 channel/);
    expect(topbarBadge()).toBe("1 unapplied mark");
    expect(b.callsOf("channels.update")).toHaveLength(0);

    await click(button(/^Apply 1 mark/));
    expect(b.callsOf("channels.update")[0].params).toEqual({ study_id: s.id, recording_id: rec.id, channel_name: "Fz", bad: true });
    expect(marksText()).toBe("No pending marks");
    expect(topbarBadge()).toBeNull();
    expect(document.querySelector(".notice-success .notice-title")?.textContent).toMatch(/^Applied 1 change/);
  });

  test("a channel already marked bad is restored to good", async () => {
    const rec = b.addRecording(s, b.addSubject(s, "S001"));
    s.badChannels[rec.id] = ["Cz"];
    await openInspect();
    await click(channelLabel("Cz"));
    await click(button(/^Apply 1 mark/));
    expect(b.callsOf("channels.update")[0].params).toMatchObject({ channel_name: "Cz", bad: false });
  });

  test("dragging across the plot marks a bad segment inside the visible window", async () => {
    b.addRecording(s, b.addSubject(s, "S001"));
    await openInspect();
    const svg = document.querySelector("svg.eegplot")!;
    fireEvent.mouseDown(svg, { clientX: 120 });
    fireEvent.mouseMove(svg, { clientX: 400 });
    fireEvent.mouseUp(svg, { clientX: 400 });
    await settle();
    expect(marksText()).toMatch(/^1 segment/);
    await click(button(/^Apply 1 mark/));
    const sug = b.callsOf("artifacts.apply")[0].params.suggestion;
    expect(sug.kind).toBe("bad_segment");
    expect(sug.start).toBeGreaterThanOrEqual(0);
    expect(sug.end).toBeGreaterThan(sug.start);
    expect(sug.end).toBeLessThanOrEqual(4);
  });

  test("clicking an existing rejected band queues an un-reject", async () => {
    const rec = b.addRecording(s, b.addSubject(s, "S001"));
    s.annotations.push({ id: "ann_1", recording_id: rec.id, start: 1, end: 2 });
    await openInspect();
    const band = document.querySelector('svg.eegplot rect[style*="pointer"]')!;
    await click(band);
    expect(marksText()).toMatch(/1 un-reject/);
    await click(button(/^Apply 1 mark/));
    expect(b.callsOf("artifacts.revert")[0].params).toMatchObject({ annotation_id: "ann_1" });
  });

  test("on partial failure only the failed marks stay pending", async () => {
    b.addRecording(s, b.addSubject(s, "S001"));
    b.failWhen = (c) => (c.command === "channels.update" && c.params.channel_name === "Cz" ? "channel locked" : null);
    await openInspect();
    await click(channelLabel("Fz"));
    await click(channelLabel("Cz"));
    expect(marksText()).toMatch(/2 channels/);
    await click(button(/^Apply 2 marks/));
    expect(document.querySelector(".notice-error .notice-title")?.textContent).toMatch(/^Applying rejections/);
    expect(marksText()).toMatch(/0 segments, 1 channel,/);
    expect(s.badChannels[s.subjects[0].sessions[0].runs[0].recordings[0].id]).toEqual(["Fz"]);
  });

  test("marks survive moving between steps and pages", async () => {
    b.addRecording(s, b.addSubject(s, "S001"));
    await openInspect();
    await click(channelLabel("Fz"));
    await step("Preprocess");
    await nav("Home");
    expect(topbarBadge()).toBe("1 unapplied mark");
    await nav("NeuroFlow");
    await step("Inspect");
    expect(marksText()).toMatch(/1 channel/);
  });

  test("switching recording with pending marks asks first; 'Keep editing' keeps both", async () => {
    const r1 = b.addRecording(s, b.addSubject(s, "S001"));
    const r2 = b.addRecording(s, b.addSubject(s, "S002"));
    await openInspect();
    await click(channelLabel("Fz"));
    harness.dialogAnswer = false;
    await change(document.querySelector(".picker select")!, r2.id);
    expect(harness.dialogs).toHaveLength(1);
    expect(document.querySelector(".topbar-rec")?.getAttribute("title")).toContain(r1.id);
    expect(marksText()).toMatch(/1 channel/);

    harness.dialogAnswer = true;
    await change(document.querySelector(".picker select")!, r2.id);
    expect(harness.dialogs).toHaveLength(2);
    expect(document.querySelector(".topbar-rec")?.getAttribute("title")).toContain(r2.id);
    expect(marksText()).toBe("No pending marks");
  });

  test("switching study with pending marks asks first and discards them on confirm", async () => {
    b.addRecording(s, b.addSubject(s, "S001"));
    const other = b.addStudy("Beta");
    await openInspect();
    await click(channelLabel("Fz"));
    harness.dialogAnswer = false;
    await change(studySelect(), other.id);
    expect(studySelect().selectedOptions[0].text).toBe("Alpha");
    expect(topbarBadge()).toBe("1 unapplied mark");
    harness.dialogAnswer = true;
    await change(studySelect(), other.id);
    expect(studySelect().selectedOptions[0].text).toBe("Beta");
    expect(topbarBadge()).toBeNull();
  });

  test("Clear drops pending marks without any backend write", async () => {
    b.addRecording(s, b.addSubject(s, "S001"));
    await openInspect();
    await click(channelLabel("Fz"));
    await click(button("Clear"));
    expect(marksText()).toBe("No pending marks");
    expect(b.callsOf("channels.update")).toHaveLength(0);
  });
});
