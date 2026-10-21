# NeuroLearn

Interactive BCI literacy. Accounts, community-authored lessons, and progress
tracking.

The Flutter client is the learner-facing app; this repository also holds the
API that backs it. Members can write lessons, submit them for review, and have
them published to everyone once a reviewer approves.

## Layout

| Path | Purpose |
|---|---|
| `server/` | FastAPI backend — accounts, authoring, review, progress |
| `studio/` | React web app where members write and review lessons |
| `app/` | Flutter client (mobile primary, web secondary) |
| `content/` | MDX lesson sources for the built-in pack |
| `tools/content-compiler/` | MDX → JSON compiler |
| `packs/` | Compiled offline content packs |

## Running the server

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# Configure NEUROLEARN_* environment variables as described below.
uvicorn neurolearn_api.main:app --reload
```

Interactive API docs at `http://localhost:8000/docs`.

```bash
pytest -q                        # 29 tests
```

## Running the studio

The authoring UI. Members write lessons here instead of posting JSON by hand.

```bash
cd studio
npm install
npm run dev          # http://localhost:5174, proxies /api to the server
```

Sign in, pick a unit, add blocks, save, submit. Reviewers get a queue tab.
Validation errors from the server highlight the offending block rather than
dumping JSON.

## Roles

Roles are cumulative — a reviewer can do everything an author can.

| Role | Can |
|---|---|
| `learner` | Take lessons, earn XP, keep a streak |
| `author` | Write lesson drafts and submit them for review |
| `reviewer` | Approve or reject submissions; create courses and units |
| `admin` | Everything |

**The first account created becomes the admin.** Register yours immediately
after deploying. Everyone after signs up as a learner; authoring and
moderation are granted deliberately.

## How community authoring works

```
draft ──submit──> in_review ──approve──> published
  ^                   │
  └────── reject ─────┘
```

Four decisions worth knowing about:

**Lessons are versioned; published versions are immutable.** Editing a live
lesson creates a new draft rather than mutating the one learners already worked
through. When version 3 goes live, version 2 is archived, not deleted — so a
learner's history still refers to something real.

**A draft locks when it is submitted.** A reviewer needs to be looking at the
same thing they are approving.

**Authors cannot review their own lessons.** Including admins.

**One open draft per lesson.** Two competing "latest" versions makes the review
queue meaningless.

## Content is untrusted until validated

Everything a member submits passes through `content/validate.py` before it
reaches the database.

- **Block types are an allowlist.** Unknown types are rejected, not ignored.
- **No raw HTML.** Prose is plain text with a small inline vocabulary
  (`**bold**`, `*italic*`, `` `code` ``, `[[glossary]]`) that the client
  renders. This removes script injection as a category rather than trying to
  sanitize it.
- **Simulations are referenced by id.** A lesson can say "run the band
  playground"; it cannot ship code. Adding a sim to `REGISTERED_SIMS` is a
  deliberate release decision.
- **Figures cannot traverse directories or point at external URLs**, and alt
  text is required.
- **Pedagogical minimums are enforced.** Every quiz question needs exactly one
  correct answer and an explanation. A lesson with no check cannot be published,
  because there would be no way to record that anyone learned anything.

Validation errors return the path to the offending block, so an author sees
`blocks[3].questions[1].choices: exactly one option must be correct (found 2)`
rather than "invalid content".

## Grading, XP, and streaks

Grading happens on the server. Correct answers are stripped from every lesson
payload the client receives — not only to stop cheating, but because once the
client reports its own score, streaks and XP mean nothing and the item-level
data becomes untrustworthy.

XP is flat and modest: 20 for passing, plus 10 the first time a lesson is
completed. The bonus is first-time-only so replaying one easy lesson is not the
fastest way to farm XP.

Streaks count calendar days, not sessions. Practising twice in a day does not
double-count; missing a day resets to 1 rather than 0, because showing someone
a zero right after they practised reads as a bug. Longest streak is kept as a
personal best. Reads recompute rather than trusting the stored column, so
someone who stopped a week ago does not still see their old streak.

## API

| Method | Path | Auth |
|---|---|---|
| `POST` | `/auth/register` | — |
| `POST` | `/auth/login` | — |
| `GET` | `/auth/me` | any |
| `GET` | `/courses` | — |
| `GET` | `/courses/{slug}` | — |
| `POST` | `/courses` | reviewer |
| `POST` | `/courses/{id}/units` | reviewer |
| `GET` | `/lessons/{id}` | — |
| `POST` | `/lessons/{id}/attempts` | any |
| `GET` | `/me/stats` | any |
| `POST` | `/courses/{id}/enroll` | any |
| `GET` | `/courses/{id}/progress` | any |
| `POST` | `/authoring/units/{id}/lessons` | author |
| `PATCH` | `/authoring/versions/{id}` | author (own draft) |
| `POST` | `/authoring/versions/{id}/submit` | author (own draft) |
| `POST` | `/authoring/versions/{id}/withdraw` | author (own draft) |
| `GET` | `/authoring/mine` | any |
| `GET` | `/authoring/queue` | reviewer |
| `POST` | `/authoring/versions/{id}/review` | reviewer |

## Before deploying

- [ ] Set `NEUROLEARN_JWT_SECRET`. Unset means a new key on every restart, which
      signs everyone out. The server logs a warning at startup.
- [ ] Point `NEUROLEARN_DATABASE_URL` at Postgres. SQLite is for local work.
- [ ] Set `NEUROLEARN_CORS` to your real origins, not `localhost`.
- [ ] Register the admin account immediately — the first one to arrive gets it.
- [ ] Serve over HTTPS. Tokens are bearer credentials.
- [ ] Add a migration tool (Alembic). `init_db()` uses `create_all`, which
      creates missing tables but will not alter existing ones.

## License

AGPL-3.0-or-later. See `LICENSE`.
