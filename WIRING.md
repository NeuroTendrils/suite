# Wiring guide — making the features visible

Everything before this was backend and components. This is the step that makes
them appear in the app.

Three insertions into `apps/desktop/src/App.tsx`. Each one is independent —
apply them one at a time and check the app still runs between each.

---

## 0. Copy the new files first

```powershell
cd ~\Documents\NT-clean\suite
New-Item -ItemType Directory -Force apps\desktop\src\hooks | Out-Null
Copy-Item <download>\apps\desktop\src\hooks\useLineage.ts apps\desktop\src\hooks\
Copy-Item -Force <download>\backend\src\suite_backend\neuroflow\batch.py backend\src\suite_backend\neuroflow\
Copy-Item -Force <download>\backend\tests\test_phase_26_batch.py backend\tests\
```

The `batch.py` overwrite matters — it fixes a real bug. `plan_executor` records
`plan_version`, but the original code read `plan_revision`. That mismatch meant
idempotence never fired, so every batch re-run would reprocess the entire study
instead of skipping work already done.

---

## 1. Imports

At the top of `App.tsx`, after the existing `import "./App.css";`:

```ts
import { LineageRibbon } from "./components/LineageRibbon";
import { BatchRunner } from "./components/BatchRunner";
import { useLineage } from "./hooks/useLineage";
```

---

## 2. The lineage ribbon

Find where the component tracks the selected recording. There is already a
state value holding the current recording id — that is what the hook needs.

Inside the main component body, near the other hooks:

```ts
const lineage = useLineage(selectedStudyId, selectedRecordingId);
```

Substitute your actual variable names. If they differ, `Ctrl+F` for
`recording_id:` in the `suiteCall` blocks — whatever is passed there is the
value to use.

Then, in the NeuroFlow view, directly **below** the signal tracks and above the
closing tag of that panel:

```tsx
{lineage.steps.length > 0 && (
  <LineageRibbon
    steps={lineage.steps}
    cursor={lineage.cursor}
    onCursorChange={(i) => void lineage.scrubTo(i, timeline.start, timeline.duration)}
    onReturnToHead={lineage.returnToHead}
    notice={lineage.error}
  />
)}
```

`timeline.start` and `timeline.duration` already exist in your component — they
are passed to `StackedStreamPlot` today.

**What you should see:** open a recording that has been through a plan, and a
chain of steps appears under the traces. Clicking one loads the signal as it
was at that point.

**If the ribbon is empty**, the recording has no artifacts yet. Run a plan on
it first — lineage is built from what `execute_plan` wrote.

---

## 3. The batch runner

Add one state value:

```ts
const [batchOpen, setBatchOpen] = useState(false);
```

Put a button wherever plans are run — next to the existing "Run plan" control:

```tsx
<button
  className="btn"
  onClick={() => setBatchOpen(true)}
  disabled={!selectedPlanId}
>
  Apply to whole study
</button>
```

And near the end of the component's returned JSX, just before the outermost
closing tag:

```tsx
{batchOpen && selectedPlanId && (
  <BatchRunner
    studyId={selectedStudyId}
    planId={selectedPlanId}
    planName={plans.find((p) => p.id === selectedPlanId)?.name ?? "plan"}
    onClose={() => setBatchOpen(false)}
    onComplete={() => void refreshStudy()}
  />
)}
```

Use whatever your refresh function is actually called.

**What you should see:** the button opens a dialog. "Check the study" runs a
preview that writes nothing and reports how many recordings are ready, blocked,
or already processed — grouped by cause, with the fix for each.

---

## 4. The signal canvas — read this before swapping

`SignalCanvas` is **not** a drop-in replacement for `StackedStreamPlot`, and I
would not swap it blind.

Your existing plot supports `onArtifactClick` and `pendingUnrejectIds` — the
flow where a learner clicks an existing rejection to un-reject it. `SignalCanvas`
does not implement that. Swapping as-is would silently remove a working feature
to gain nicer rendering, which is a bad trade.

Two honest options:

**Leave it.** The ribbon and batch runner are the features with real value.
The existing plot works.

**Use it for replay only.** When `lineage.replay` is non-null you are rendering
history, which is read-only by definition — so the missing interaction handlers
do not matter:

```tsx
{lineage.replay ? (
  <SignalCanvas
    data={lineage.replay.data}
    channels={lineage.replay.channels}
    windowStart={timeline.start}
    windowDuration={timeline.duration}
    sampleRate={250}
    gain={tlGain}
    readOnly
  />
) : (
  <StackedStreamPlot ...existing props... />
)}
```

That gives you the improved rendering exactly where the old component has
nothing to offer anyway, and it costs you no functionality.

---

## Verify

```powershell
cd backend
python -m pytest tests\test_phase_26_batch.py tests\test_phase_27_lineage.py -q
cd ..\apps\desktop
npx tsc --noEmit
npm run tauri:dev
```

34 tests, clean typecheck, and the app opens.

---

## What is still not done

**The ribbon shows lineage but cannot fork from it.** Clicking an earlier step
lets you look; it does not let you branch a new plan from that point. That is
the natural next feature and the backend already stores everything it needs.

**Batch progress is not streamed.** `run_batch` accepts a `progress` callback,
but the IPC handler does not emit events, so the dialog shows a spinner rather
than "12 of 34". Fine for a study of 20; worth wiring for 200.
