/** Typed client for the NeuroLearn API.
 *
 * The token lives in memory plus sessionStorage rather than localStorage: a
 * bearer token that survives until someone clears their browser is a longer
 * window than an authoring tool needs.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "/api";
const TOKEN_KEY = "neurolearn.token";

let token: string | null = sessionStorage.getItem(TOKEN_KEY);

export function setToken(next: string | null) {
  token = next;
  if (next) sessionStorage.setItem(TOKEN_KEY, next);
  else sessionStorage.removeItem(TOKEN_KEY);
}

export function getToken() {
  return token;
}

/** Validation failures arrive as {path, message}; keep both so the editor can
 *  point at the offending block instead of showing a wall of JSON. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly path?: string,
  ) {
    super(message);
  }
}

function describe(detail: unknown): { message: string; path?: string } {
  if (typeof detail === "string") return { message: detail };
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (typeof d.message === "string") {
      return { message: d.message, path: typeof d.path === "string" ? d.path : undefined };
    }
    // FastAPI's own 422 shape.
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as Record<string, unknown>;
      const loc = Array.isArray(first.loc) ? first.loc.join(".") : undefined;
      return { message: String(first.msg ?? "invalid request"), path: loc };
    }
  }
  return { message: "Request failed" };
}

async function request<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.json !== undefined) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
    body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
  });

  if (res.status === 204) return undefined as T;

  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    const { message, path: where } = describe(payload?.detail ?? payload);
    if (res.status === 401) setToken(null);
    throw new ApiError(res.status, message, where);
  }
  return payload as T;
}

// ------------------------------------------------------------------- types

export type Role = "learner" | "author" | "reviewer" | "admin";

export type User = {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  created_at: string;
};

export type LessonStatus = "draft" | "in_review" | "published" | "rejected" | "archived";

export type LessonVersion = {
  id: string;
  lesson_id: string;
  version: number;
  title: string;
  objective: string;
  est_minutes: number;
  status: LessonStatus;
  author_id: string;
  author_name: string | null;
  created_at: string;
  published_at: string | null;
};

export type LessonSummary = {
  id: string;
  slug: string;
  position: number;
  title: string | null;
  has_published: boolean;
};

export type Unit = {
  id: string;
  slug: string;
  title: string;
  section: string;
  position: number;
  lessons: LessonSummary[];
};

export type Course = {
  id: string;
  slug: string;
  title: string;
  description: string;
  units: Unit[];
};

export type Block = Record<string, unknown> & { type: string };

// -------------------------------------------------------------------- calls

export const api = {
  register: (email: string, display_name: string, password: string) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      json: { email, display_name, password },
    }),

  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      json: { email, password },
    }),

  me: () => request<User>("/auth/me"),

  courses: () => request<Course[]>("/courses"),

  createDraft: (
    unitId: string,
    body: {
      slug: string;
      title: string;
      objective: string;
      est_minutes: number;
      blocks: Block[];
    },
  ) =>
    request<LessonVersion>(`/authoring/units/${unitId}/lessons`, {
      method: "POST",
      json: body,
    }),

  updateDraft: (
    versionId: string,
    body: Partial<{ title: string; objective: string; est_minutes: number; blocks: Block[] }>,
  ) => request<LessonVersion>(`/authoring/versions/${versionId}`, { method: "PATCH", json: body }),

  submit: (versionId: string) =>
    request<LessonVersion>(`/authoring/versions/${versionId}/submit`, { method: "POST" }),

  withdraw: (versionId: string) =>
    request<LessonVersion>(`/authoring/versions/${versionId}/withdraw`, { method: "POST" }),

  mine: () => request<LessonVersion[]>("/authoring/mine"),

  queue: () => request<LessonVersion[]>("/authoring/queue"),

  review: (versionId: string, decision: "approve" | "reject", notes: string) =>
    request<LessonVersion>(`/authoring/versions/${versionId}/review`, {
      method: "POST",
      json: { decision, notes },
    }),
};
