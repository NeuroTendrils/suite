# MDX authoring guide

Lessons live under `content/courses/<course-id>/`. Each lesson is an `.mdx` file with YAML front matter and NeuroLearn components.

## Front matter

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Stable slug, e.g. `spark-01-what-is-bci` |
| `title` | yes | Shown on map and lesson header |
| `unit` | yes | Unit id, e.g. `spark-01` |
| `objective` | yes | One learning objective |
| `estMinutes` | yes | Integer, typically 5–12 |

## Components

### `Hook`

Opening question or provocation. One per lesson recommended.

```mdx
<Hook>
Why isn’t EEG the same as reading thoughts?
</Hook>
```

### Markdown body

Ordinary paragraphs, headings, lists, and emphasis become `markdown` blocks.

### `Figure`

```mdx
<Figure
  src="bci-loop.svg"
  alt="Sense, process, actuate loop"
  caption="Every BCI closes a loop."
/>
```

Put asset files next to the lesson or under the unit `assets/` folder. Paths are resolved relative to the lesson file.

### `Callout`

`kind`: `myth` | `limit` | `glossary` | `tip`

```mdx
<Callout kind="myth">
EEG cannot decode arbitrary private thoughts with consumer headsets today.
</Callout>
```

### `Sim`

References a Flutter-registered simulation by id.

```mdx
<Sim id="band-playground" goal="Isolate an alpha-dominant segment from noise." />
```

### `Check`

Wraps quiz items. `passScore` defaults to `0.7` if omitted in source (compiler normalizes).

```mdx
<Check passScore={0.7}>
  <MCQ id="q1" prompt="What does a BCI need to close the loop?" explain="Sensing alone is not control.">
    <Choice correct>A way to sense, decode, and actuate</Choice>
    <Choice>Only a brain scan image</Choice>
    <Choice>A clinical MRI</Choice>
  </MCQ>
</Check>
```

## Authoring rules

- One objective per lesson
- Prefer short chunks over long essays
- Put myths/limits near claims that invite hype
- Only add `<Sim>` when interaction teaches the idea
- At least one `<Check>` item before the lesson can complete

## Build

From repo root:

```bash
npm --prefix tools/content-compiler install
npm --prefix tools/content-compiler run compile
```

The compiler writes `packs/bci-foundations/` and copies into `app/assets/packs/` when the Flutter app is present.
