import { useCallback, useEffect, useState } from "react";

import { api, ApiError, setToken, getToken } from "./api";
import type { Block, Course, LessonVersion, User } from "./api";
import { BlockEditor, emptyBlock } from "./BlockEditor";
import "./studio.css";

type Tab = "write" | "mine" | "queue";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      setBooting(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setBooting(false));
  }, []);

  if (booting) return <div className="boot">Loading…</div>;
  if (!user) return <SignIn onSignedIn={setUser} />;
  return <Studio user={user} onSignOut={() => { setToken(null); setUser(null); }} />;
}

// ------------------------------------------------------------------ sign in

function SignIn({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function go() {
    setBusy(true);
    setError(null);
    try {
      const { access_token } =
        mode === "login"
          ? await api.login(email, password)
          : await api.register(email, name, password);
      setToken(access_token);
      onSignedIn(await api.me());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="signin">
      <div className="signin__card">
        <h1>NeuroLearn Studio</h1>
        <p className="muted">Write lessons for the community.</p>

        {mode === "register" && (
          <input
            value={name}
            placeholder="Display name"
            autoComplete="name"
            onChange={(e) => setName(e.target.value)}
          />
        )}
        <input
          value={email}
          type="email"
          placeholder="Email"
          autoComplete="email"
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          value={password}
          type="password"
          placeholder="Password — at least 10 characters"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && go()}
        />

        {error && <p className="error">{error}</p>}

        <button className="primary" onClick={go} disabled={busy || !email || !password}>
          {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
        <button
          className="link"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError(null);
          }}
        >
          {mode === "login" ? "Create an account" : "I already have an account"}
        </button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------- studio

function Studio({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const canReview = user.role === "reviewer" || user.role === "admin";
  const canAuthor = user.role !== "learner";
  const [tab, setTab] = useState<Tab>(canAuthor ? "write" : "mine");

  return (
    <div className="studio">
      <header className="top">
        <b>NeuroLearn Studio</b>
        <nav>
          {canAuthor && (
            <button className={tab === "write" ? "on" : ""} onClick={() => setTab("write")}>
              Write
            </button>
          )}
          <button className={tab === "mine" ? "on" : ""} onClick={() => setTab("mine")}>
            My lessons
          </button>
          {canReview && (
            <button className={tab === "queue" ? "on" : ""} onClick={() => setTab("queue")}>
              Review queue
            </button>
          )}
        </nav>
        <div className="spacer" />
        <span className="who">
          {user.display_name} <em>{user.role}</em>
        </span>
        <button className="link" onClick={onSignOut}>
          Sign out
        </button>
      </header>

      <main>
        {!canAuthor && tab === "write" && (
          <p className="notice">
Your account is a learner. Ask a moderator for the author role to start
            writing lessons.
          </p>
        )}
        {tab === "write" && canAuthor && <Writer />}
        {tab === "mine" && <MyLessons />}
        {tab === "queue" && canReview && <Queue reviewerId={user.id} />}
      </main>
    </div>
  );
}

// ------------------------------------------------------------------- writer

function Writer() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [unitId, setUnitId] = useState("");
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [objective, setObjective] = useState("");
  const [minutes, setMinutes] = useState(8);
  const [blocks, setBlocks] = useState<Block[]>([emptyBlock("hook"), emptyBlock("check")]);

  const [saved, setSaved] = useState<LessonVersion | null>(null);
  const [error, setError] = useState<{ message: string; path?: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.courses().then(setCourses).catch(() => setCourses([]));
  }, []);

  // Slug follows the title until the author edits it themselves.
  const [slugTouched, setSlugTouched] = useState(false);
  useEffect(() => {
    if (slugTouched) return;
    setSlug(
      title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 80),
    );
  }, [title, slugTouched]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const version = await api.createDraft(unitId, {
        slug,
        title,
        objective,
        est_minutes: minutes,
        blocks,
      });
      setSaved(version);
    } catch (e) {
      if (e instanceof ApiError) setError({ message: e.message, path: e.path });
      else setError({ message: "Could not save" });
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!saved) return;
    setBusy(true);
    setError(null);
    try {
      setSaved(await api.submit(saved.id));
    } catch (e) {
      if (e instanceof ApiError) setError({ message: e.message, path: e.path });
    } finally {
      setBusy(false);
    }
  }

  const ready = unitId && slug && title.length >= 2 && blocks.length > 0;
  const hasCheck = blocks.some((b) => b.type === "check");

  return (
    <div className="writer">
      <div className="writer__meta">
        <label>
          Unit
          <select value={unitId} onChange={(e) => setUnitId(e.target.value)}>
            <option value="">Choose a unit…</option>
            {courses.map((c) =>
              c.units.map((u) => (
                <option key={u.id} value={u.id}>
                  {c.title} → {u.title}
                </option>
              )),
            )}
          </select>
        </label>

        <label>
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="The brain's electrical currents" />
        </label>

        <label>
          Slug
          <input
            value={slug}
            onChange={(e) => {
              setSlugTouched(true);
              setSlug(e.target.value);
            }}
            placeholder="brain-electricity"
          />
        </label>

        <label>
          Minutes
          <input
            type="number"
            min={1}
            max={60}
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
          />
        </label>

        <label className="wide">
          Objective
          <input
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="Explain why EEG needs many neurons firing together."
          />
        </label>
      </div>

      {!hasCheck && (
        <p className="notice notice--warn">
          Add a Check block before submitting — a lesson with no questions cannot record
          that anyone learned anything, so the server will reject it.
        </p>
      )}

      <BlockEditor blocks={blocks} onChange={setBlocks} errorPath={error?.path} />

      {error && (
        <p className="error">
          {error.path && <code>{error.path}</code>} {error.message}
        </p>
      )}

      <div className="writer__actions">
        {saved && <span className="status">Saved as v{saved.version} · {saved.status}</span>}
        <div className="spacer" />
        <button onClick={save} disabled={!ready || busy}>
          {saved ? "Save again" : "Save draft"}
        </button>
        <button
          className="primary"
          onClick={submit}
          disabled={!saved || busy || saved.status !== "draft"}
        >
          Submit for review
        </button>
      </div>
    </div>
  );
}

// -------------------------------------------------------------- my lessons

function MyLessons() {
  const [rows, setRows] = useState<LessonVersion[] | null>(null);

  const load = useCallback(() => {
    api.mine().then(setRows).catch(() => setRows([]));
  }, []);
  useEffect(load, [load]);

  if (rows === null) return <p className="muted">Loading…</p>;
  if (rows.length === 0) return <p className="muted">Nothing written yet.</p>;

  return (
    <table className="rows">
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
            <td>
              <b>{r.title}</b>
              <span className="muted"> v{r.version}</span>
            </td>
            <td>
              <span className={`badge badge--${r.status}`}>{r.status.replace("_", " ")}</span>
            </td>
            <td className="right">
              {(r.status === "in_review" || r.status === "rejected") && (
                <button
                  className="mini"
                  onClick={() => api.withdraw(r.id).then(load)}
                >
                  {r.status === "rejected" ? "Reopen" : "Withdraw"}
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// -------------------------------------------------------------------- queue

function Queue({ reviewerId }: { reviewerId: string }) {
  const [rows, setRows] = useState<LessonVersion[] | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    api.queue().then(setRows).catch(() => setRows([]));
  }, []);
  useEffect(load, [load]);

  async function decide(id: string, decision: "approve" | "reject") {
    await api.review(id, decision, notes[id] ?? "");
    load();
  }

  if (rows === null) return <p className="muted">Loading…</p>;
  if (rows.length === 0) return <p className="muted">The queue is empty.</p>;

  return (
    <div className="queue">
      {rows.map((r) => {
        // The server enforces this too; disabling the buttons just avoids
        // offering an action that is going to be refused.
        const isOwn = r.author_id === reviewerId;
        return (
          <div key={r.id} className="queue__item">
            <div className="queue__head">
              <b>{r.title}</b>
              <span className="muted">
                v{r.version} · {r.author_name ?? "unknown"}
              </span>
            </div>
            {r.objective && <p className="muted">{r.objective}</p>}
            <textarea className="resize-none"
              rows={2}
              placeholder="Notes for the author"
              value={notes[r.id] ?? ""}
              onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })}
            />
            <div className="queue__actions">
              {isOwn && <span className="muted">You wrote this — someone else must review it.</span>}
              <div className="spacer" />
              <button className="mini" onClick={() => decide(r.id, "reject")} disabled={isOwn}>
                Reject
              </button>
              <button className="primary mini" onClick={() => decide(r.id, "approve")} disabled={isOwn}>
                Approve
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
