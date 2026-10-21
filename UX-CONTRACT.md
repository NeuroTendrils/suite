# NeuroTendrils UI contract

Visual ownership and product-specific geometry are documented in [DESIGN.md](DESIGN.md).
Consolidation preserves the existing workflows described by
`docs/guides/USER_GUIDE.md`, `docs/architecture/OVERVIEW.md`, and
`apps/neurolearn/docs/PRODUCT.md`. Learning API roles and publication rules remain
defined by `apps/neurolearn/README.md` and its API implementation.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Select/Listbox | Existing native HTML selects; Flutter Material controls | Existing workflow components | Native platform popup, product-specific density | Suite navigation/import/dataset tests; Flutter shell tests |
| Form | Suite useStudyForms/useImport/usePreprocess hooks; authoring editor/API | Backend parameter validation and existing field checks | Study, subject, import, event, lesson editor | Suite study/import tests and learning API tests |
| Scrollbar | Suite index.css; authoring studio.css; Flutter platform | DESIGN.md and semantic tokens | Theme-aware research; light authoring; Flutter native | Browser inspection and static audit |
| Toast | Suite NoticeBar/useOperations; authoring Notice | Existing component state | Info, success, warning, error | Suite operations tests |
| CRUD | Existing application hooks and learning API | User guide, architecture, learning API | Local studies and server-owned lesson drafts remain separate | Existing Suite and API suites |

## Navigation and persistence

Suite retains the active study, recording, module stage, unapplied marks, and
display preferences when navigating as supported by its existing hooks. Persist
theme/sidebar using the existing keys; default to light for new or invalid values.
Do not reset a saved dark preference. Study/recording changes retain the current
discard-marks confirmation. Keep Tauri's native dialog integration.

NeuroLearn retains Learn / Practice / You, bundled offline content, local progress,
retries, and its existing content-driven lesson order inside the desktop window.
`pages/learn/LearnPage` owns the local embedded frame and loads it on first visit,
then hides rather than unmounts it when switching modules. Learning works without
a study or the research backend. It does not clear the selected research study,
recording, or unapplied marks. Parent startup messages must come from that exact frame.

Saved learning progress belongs to the desktop app's local origin, not the active
research study. Progress in a separately installed mobile/web app is not imported
or overwritten. Authoring and the optional learning API retain their existing
accounts and publication rules; this integration does not introduce account sync.

## States and accessibility

Preserve existing busy, empty, failure, retry, and success feedback and keyboard
semantics. Shared theme changes must not change operation availability. Controls
retain visible focus, semantic labels, and text/icon status alongside color.
Native select popup geometry is intentionally owned by the platform.
Research forms use existing app validation rather than browser validation bubbles.
Textareas retain sufficient height and scrolling with resizing disabled.
Learn has checking, engine-starting, ready, and retryable error states. A missing
or invalid bundle must not load the host SPA as a recursive frame. Requests and
startup waits time out after 30 seconds and are cancelled when the component is
removed. Research backend errors stay available on research pages, while Learn
shows its own startup/recovery state. The embedded learner owns lesson-load
errors, quiz feedback, and progress persistence.

## Scope and evidence

The current change shares source, visual tokens, and desktop navigation through
the Learn route. It does not redesign CRUD, add auth or introduce data handoff. The static audit
checks maintained frontend source roots and excludes dependency environments.
Runtime verification uses the project-owned Suite, learner, content, and API tests.
