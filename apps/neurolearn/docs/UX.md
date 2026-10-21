# NeuroLearn UX

## Principles

- Mobile-first; one composition per screen—no dashboard clutter
- Educational value over gamification (no hearts, energy, streaks)
- Always clear how to continue and how to go back to the map
- Offline is the default experience, not a degraded mode

## Navigation

Bottom navigation (MVP):

| Tab | Purpose |
|---|---|
| **Learn** | Continue CTA + course map |
| **Practice** | Weak items / free sims (stub OK in early builds) |
| **Profile** | Progress, glossary, disclaimers, offline status |

No educator, classroom, or multi-course library chrome in MVP.

## Course map (Learn)

Reference UI: clean learner path (progress + course card + numbered zigzag).

- Title **Learn**
- PROGRESS row + linear bar (`complete/total Lessons`)
- Course card with circular percent
- Numbered circular nodes on a dotted zigzag path
- Labels under nodes; **Continue** bubble on current
- Complete = green + check badge; current = blue; later = grey

| State | Meaning |
|---|---|
| Locked (soft) | Shown grey; still tappable in MVP |
| Available / In progress | Blue current node |
| Complete | Green + check |
| Needs review | Optional Practice flag later |

## Lesson overview

Tapping a node opens overview:

- Round back button
- Hero figure (or placeholder)
- Title + objective
- **Take Practice** (primary) / **Learn Theory** (outline)
- Study summary rows (theory %, best score, time)

## Theory flow

Full article on one scrollable page (not stepped sections):

- Close + “Theory” title + mascot
- Title, objective, then all lesson blocks in order
- Bottom CTA: Start practice

## Content delivery

Bundle the full course pack in the app. Current pack is tens of KB (mostly JSON/MDX text + small SVGs). Even with figures and a few sims, shipping everything offline is the default.

## Quiz / practice flow

Full-screen practice (not a sheet):

- Round back + lesson title + progress bar
- Prompt + bordered answer cards with radio affordance
- Immediate feedback + explain
- Pass ≥70%; unlimited retries; best score stored
- No public leaderboards

## Progress

- Lesson: status, best score, sim completion flags, updatedAt
- Unit: percent complete, mastery flag
- Profile: section completion rings (celebration without streaks)

## Empty / edge states

- First launch: short disclaimer (non-clinical) → Continue into lesson 1
- Offline: silent success (content bundled); show sync status only when account exists later
- Skip ahead: confirm dialog explaining prerequisites may help
