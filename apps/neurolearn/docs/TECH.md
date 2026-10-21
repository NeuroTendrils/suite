# NeuroLearn Technical Design

## Stack

| Layer | Choice |
|---|---|
| Client | **Flutter** (iOS / Android primary, web secondary) |
| Progress | SQLite via `drift` |
| Lesson authoring | **MDX** sources |
| Runtime content | Compiled JSON AST + assets (content pack) |
| Sims | Flutter widgets registered by `simId` |

Flutter does **not** execute MDX at runtime. Authors write MDX; a Node compiler validates components and emits AST JSON consumed by `LessonPlayer`.

## Repository layout

```text
neurolearn/
  app/                 # Flutter application
  content/             # MDX sources + figures
  tools/content-compiler/  # MDX → AST
  packs/               # Compiled content packs (generated)
  docs/                # Product & tech specs
```

## Architecture

```text
MDX sources ──► content-compiler ──► packs/bci-foundations/
                                         ├── manifest.json
                                         ├── lessons/*.json
                                         └── assets/
                                              │
Flutter app ──► ContentPackStore ─────────────┘
         ├── LessonPlayer (AST → widgets)
         ├── SimRegistry (simId → widget)
         └── ProgressRepository (SQLite)
```

### Layers

1. **Content pack** — immutable, versioned; bundled for offline MVP
2. **Player** — walks lesson AST, navigation, checks
3. **Sim runtime** — loads by `simId`, emits completion events
4. **Progress store** — offline source of truth
5. **Sync (later)** — optional account; progress merge only

## MDX pipeline

1. Author `content/courses/bci-foundations/**/*.mdx`
2. Run `npm run compile` in `tools/content-compiler`
3. Compiler parses front matter + MDX, validates against schema, writes `packs/...`
4. Flutter loads pack from assets (`assets/packs/...` copy or path config)
5. Unknown MDX components **fail the content build**

See [mdx-components.md](mdx-components.md) and [content-schema.json](content-schema.json).

## Data models

### Course graph

- `Course` `{ id, title, version, units[] }`
- `Unit` `{ id, title, section: spark|signal|pipeline|world, lessonIds[] }`
- `Lesson` `{ id, title, objective, estMinutes, blocks[] }`

### Lesson AST blocks

Typed union: `hook` | `markdown` | `figure` | `callout` | `sim` | `check`

### Progress

```text
ProgressRecord {
  lessonId, status, bestScore, simFlags{}, blockIndex, updatedAt
}
```

Conflict policy (future sync): `max(bestScore)`, union of completion/sim flags, latest `updatedAt` for cursor.

## Offline

- Ship the full content pack inside the app bundle for MVP (default)
- Packs are tiny today (~tens of KB of lesson JSON/text + small assets); text-heavy curriculum stays easy to download/embed
- Lessons play with zero network
- Later: optional differential OTA pack updates if courses grow large

## Suite handoff (later)

Lesson front matter may include `suiteHandoff` metadata. Client opens deep link / recipe document for NeuroFlow. Do not embed Learn inside the desktop Suite for v1.

## Non-clinical

Surface a clear disclaimer on first launch and in Profile. Content must not claim medical or clinical use.
