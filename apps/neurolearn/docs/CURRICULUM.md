# NeuroLearn Curriculum

## Hierarchy

One hard high-school STEM track. No Beginner / Intermediate / Advanced trees. No parallel audience tracks.

```text
Library
  └── Course: BCI Foundations
        └── Unit          (thematic chapter)
              └── Lesson  (5–12 min, MDX)
                    ├── body (prose, figures, callouts)
                    ├── Simulation (optional)
                    └── Check (quiz)
```

Units are grouped on the course map under section labels for orientation only:

| Section | Role |
|---|---|
| **Spark** | What BCIs are/aren’t; neurons; brain map; control loop |
| **Signal** | EEG measurement, hardware, bands, acquisition, artifacts |
| **Pipeline** | Preprocess → features → ML → closed loop → model limits |
| **World** | Applications, ethics, next steps |

## Progression

- Soft gating: prior unit Check ≥ 70%, or explicit “Skip ahead” with a warning.
- Mastery: unit Check average + simulation completion flags.
- Hard ideas use a three-pass pattern **in the main path**:
  1. Intuition (analogy + one picture)
  2. Mechanism (what actually happens—including math when needed)
  3. Boundary (failures, myths, ethics)

## Lesson rules

- One primary learning objective (front matter `objective`)
- 5–12 minutes typical; up to ~15 if a sim is central
- Never introduce two new mechanisms in one lesson
- Quiz items test the objective, not trivia
- Sims only when visualization is the pedagogy
- Myth / limit callouts whenever hype risk is high

## Course outline: Introduction to EEG (current pack)

### Lesson 1 — The brain's electrical currents

- Na/K pumps, polarization, action-potential intuition
- Why one neuron is too weak; aligned population firing
- CSF / skull / skin–hair attenuation → microvolt scalp signals

### Lesson 2 — Introduction to EEGs

- BCI framing; EEG as non-invasive sensing
- Potential differences, poor localization, Ag/AgCl, gel/impedance
- Passive vs active electrodes; differential amplification
- 10–20 system (nasion/inion, F/C/T/P/O, odd/even, references)
- Why massive amplification is required (~5–100 µV)

### Later expansion (not in pack yet)

Bands, artifacts, filtering, features, decoding, closed loop, ethics.

## Signature simulations (MVP)

1. Brain-wave band playground
2. Artifact detective
3. Filter playground
4. Closed-loop BCI (cursor or simple arm)

## Simulation placement

A sim belongs in a lesson when the learner’s misconception is visual or dynamic (e.g. “filtering deletes the brain”). Completion = interact until a target state, or answer a predict-then-reveal prompt inside the sim.
