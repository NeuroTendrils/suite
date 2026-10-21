# NeuroLearn design

## Direction

NeuroLearn is a friendly neuroscience-learning app for high-school STEM learners (docs/PRODUCT.md). Learn is a mobile lesson journey, with a soft brain silhouette, tactile numbered buttons, and the existing pink brain companion. Use a clean light surface, strong blue, rounded shapes, and bold sans-serif headings. Avoid realistic anatomy, serif headings, desktop dashboards, lesson-card feeds, locks, currencies, or invented curriculum.

## Runtime ownership

`app/lib/theme/app_theme.dart` is the canonical runtime token source. `NeuroColors` owns primary blue (`tide`, #176BC1), lower button edge (`deepBlue`, #114A87), pink progress (#FFB8CB), brain fill (#FFF0F4), contour (#F0CDD8), route (#CC8FA7), ink (#172B3A), muted (#536676), and completion moss (#557564). Pale contour colors are decoration, never text. Source Sans 3 is bundled for all interface and heading roles; fonts and the 1024px mascot require no network download. The existing Fraunces asset remains available but is not used by the theme.

`NeuroLayout` owns the 460px maximum shell width, 20px page gutters, 24px surfaces, 16px controls, and 150ms interaction transitions. Reduced motion removes transitions. Light mode remains the supported theme.

## Composition and behavior

`HomeShell` owns the unchanged Learn / Practice / You destinations in an IndexedStack. Bottom navigation remains visible at all widths, with centered mobile content and navigation targets. Flutter Material NavigationBar owns selected, keyboard, and screen-reader behavior. Practice and You preserve their existing content.

`CourseMapPage` owns the compact course banner and lesson map. Titles, identifiers, order, and loading come from ContentRepository. ProgressRepository owns completion, persistence, and recommendation. The banner reports actual complete/total counts. Resume means in progress, Start lesson means available, and other states use Open lesson. All lessons remain tappable through the existing LessonOverviewPage route and progress callback.

The decorative CustomPainter has no interaction or semantics. It draws a simple brain silhouette and a curved route connecting the same row positions used by the buttons. Rows expand with measured bold lesson titles and text scaling; lesson count determines total map height. No filler nodes are added. Each lesson has one semantic button and one keyboard target, a visible focus outline, hover feedback, and a pressed lower edge. Completion has a checkmark and a text label; available lessons retain blue outlines and depth.

## Verification

Focused Flutter widget tests cover later/completed lesson opening, progress, keyboard activation, destination selection across viewport changes, and enlarged text. Opt-in rendered previews cover phone and wide Learn views plus sibling tabs. The visual direction here supersedes the previous serif/card/rail design and older conflicting presentation guidance in docs/UX.md, as requested in the current redesign brief. No lesson content, storage, backend, or progression rules change.
