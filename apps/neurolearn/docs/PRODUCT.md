# NeuroLearn Product

## Vision

NeuroLearn makes EEG and BCI literacy intuitive through short, structured lessons and interactive simulations. A high-school STEM student should be able to go from “what is a neuron?” to “why bandpass before features?” and into real decoding concepts—without a lab and without watering down the science.

**Positioning:** Interactive BCI literacy—short lessons, real concepts, no hype.

NeuroLearn is one peer product in the NeuroTendrils Suite story alongside NeuroFlow (preprocessing) and NeuroStudio (training). For v1 it ships as a **standalone Flutter app** (mobile primary, web secondary), not as a desktop Suite shell module.

## Audience

**Primary (only for v1):** High school STEM students (≈14–18) who want substantive neuroscience, EEG, and BCI content.

The curriculum is deliberately difficult. There is no separate middle-school path, no optional “Lab Notes” depth layer, and no educator/mentor product surface in MVP. College students, clubs, and curious adults may use the same single track; we do not design separate personas for them.

## Learning philosophy

1. **Concept before tooling** — understand why before how to click.
2. **Concrete before abstract** — signal pictures and sims before equations; equations appear in-line when they earn their keep.
3. **Literacy over hype** — every BCI claim paired with limits and myths.
4. **Short loops, long arcs** — 5–12 minute lessons; one hard multi-week spine.
5. **Feedback without punishment** — immediate quiz feedback; no hearts/lives; retries encouraged.
6. **Simulation as explanation** — interactives teach hard-to-visualize topics; they are not side demos.

## Non-goals

- Clinical training or medical advice
- Credentialing / certificates as a product
- Streak, hearts, energy, or lives systems
- Full research IDE (that is NeuroFlow / NeuroStudio)
- Multi-audience scaffolding (middle-school track, teacher dashboard) in MVP
- Requiring EEG hardware to learn

## Suite relationship

| Now | Later |
|---|---|
| Sibling Flutter app with its own content pack | Deep links / recipe handoff into NeuroFlow |
| Literacy and simulations only | Optional “continue in Suite” from late Pipeline lessons |
| Marketing may still say “desktop module”—update when shipping | Shared glossary IDs optional |

## Feature roadmap

### MVP

- One course, one track: **BCI Foundations**
- Course map, units, MDX-authored lessons
- Local progress (completion, quiz score, unit mastery)
- Offline content pack bundled with the app
- 3–5 signature simulations
- Glossary + myth / “why this matters” callouts
- Non-clinical disclaimer UX

### v1.1

- Remaining Pipeline / World units
- More sims (artifact removal, feature extraction, classifier viz)
- Light Practice queue from weak quiz items
- Flutter web parity; optional NeuroTendrils account sync

### v2

- Suite handoff from late Pipeline
- Additional courses (same player, new MDX packs)
- Community-created lessons (reviewed pipeline)
- Classroom / education kits only if explicitly prioritized

## Success criteria (MVP)

- A learner can complete Spark + Signal offline on a phone
- At least four signature sims feel like part of the lesson, not bolted-on toys
- Checks give immediate, explanatory feedback
- Content authors can add a lesson by writing MDX without touching Flutter UI code
