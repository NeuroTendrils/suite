---
version: alpha
name: NeuroTendrils
description: NeuroLearn's blue and pink identity across learning and EEG research.
colors:
  primary: "#176BC1"
  primary-hover: "#114A87"
  background: "#F7F9FB"
  surface: "#FFFFFF"
  text: "#172B3A"
  muted: "#536676"
  pink: "#FFB8CB"
  pink-wash: "#FFF0F4"
  success: "#557564"
  danger: "#BA3535"
typography:
  sans:
    fontFamily: '"Source Sans 3", system-ui, sans-serif'
  mono:
    fontFamily: 'ui-monospace, "SF Mono", Menlo, Consolas, monospace'
rounded:
  sm: "4px"
  DEFAULT: "6px"
  lg: "8px"
spacing:
  unit: "4px"
  panel: "16px"
  section: "24px"
---

# NeuroTendrils design

## Overview

Use NeuroLearn's established blue, pink, and pale blue-gray identity across the
repository. One Tauri desktop window provides Learn, NeuroFlow, and NeuroStudio.
Learning serves STEM learners; research modules serve EEG researchers. Share color and type;
retain the density and navigation each task requires. The learning map and pink
brain remain the learner signature, while signal plots remain the research focus.
Do not turn research tables into a mobile course map or introduce marketing heroes.
English is the current interface language; no additional market is inferred.

## Colors

Runtime ownership stays with `NeuroColors` in
`apps/neurolearn/app/lib/theme/app_theme.dart`. Run `npm run sync:theme` after
changing that palette. `scripts/sync_theme.py` exports it into
`packages/theme/neurolearn.css`; `npm run check:theme` checks exact drift.
This document mirrors accepted values rather than generating them.

| Role | Shared CSS | Consumer |
|---|---|---|
| Brand/action | `--neuro-tide`, `--neuro-deep-blue` | Suite `--accent`, authoring `--tide` |
| Background/text | `--neuro-mist`, `--neuro-ink`, `--neuro-muted` | Both React stylesheets |
| Pink decoration | `--neuro-brain-wash`, `--neuro-blush` | Suite module selection backgrounds |
| Status | `--neuro-moss`, `--neuro-danger`, `--neuro-limit` | Suite badges/plots; authoring feedback |

Light mode is the default. Suite retains its existing dark adaptation and saved
theme preference. Pale pink is a background/accent, never body text. Status also
uses text or icons. Signal categories keep separate semantic tokens.
The embedded learner retains NeuroLearn's supported light theme even when the
research shell uses its optional dark adaptation.

## Typography

Source Sans 3 is bundled in NeuroLearn and included in the generated CSS with a
relative asset URL, so both Vite builds bundle it for offline use. Use it for
headings and body text; retain monospace for comparable scientific numbers.
Suite keeps its existing 12–22px scale and 1.45 body line height.

## Layout

Preserve Suite's rail, shared study context, stage headers and workflow footer.
Keep its existing responsive behavior and 4px spacing scale. NeuroLearn retains
its 460px learner shell and Learn / Practice / You navigation. Authoring retains
its 840px editor. Shared colors do not require shared component geometry.
`pages/learn/LearnPage` owns a full-height local frame inside the content area.
Only Learn uses that viewport; research pages retain their existing scrolling.

## Elevation & Depth

Use existing borders and tonal surfaces for research data. Keep the learner's
tactile blue lesson buttons. Authoring uses blue primary buttons with the deep
blue lower edge. Avoid decorative gradients and new shadows.

## Shapes

Suite retains 4/6/8px radii for dense controls and panels. The Flutter client
retains its 16px controls and 24px surfaces. These are intentional product variants.

## Components

`apps/desktop/src/components` owns research chrome and primitives; Flutter's
theme and widgets own learner components; the authoring app owns lesson editing.
The desktop navigation opens the bundled Flutter learner in place. Retain its
frame across module changes so quizzes, scroll position, and lesson state survive.
Use shared semantic colors in hover, selected, focus, and feedback states.
Keep visible focus and disabled/busy controls. Preserve native select behavior.
Global research scrollbars follow text/surface/accent tokens and system colors
in forced-colors mode. Reduced motion continues to use each app's existing policy.

## Do's and Don'ts

- Derive web colors from the generated palette; change the Dart owner first.
- Keep labels, workflow state, scientific results, and learner progress intact.
- Keep blue actions legible on white and pink surfaces.
- Do not use decorative pinks as text or replace status labels with color alone.

## Acquisition and export controls

Insight acquisition uses the existing Card, Field, checkbox, task/busy and notice primitives in NeuroFlow Import. Recording consent starts unchecked and resets after successful capture. Privacy export defaults to a redacted summary; raw-data selection resets when redaction is enabled or the study changes. Native selects retain platform popup behavior. Study switching is disabled while a backend operation runs to preserve result ownership. No new visual tokens are introduced.
