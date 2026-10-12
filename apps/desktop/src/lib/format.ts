export function shortId(id: string | null | undefined, n = 10): string {
  if (!id) return "—";
  return id.length > n ? `${id.slice(0, n)}…` : id;
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function issueText(i: string | { message?: string; code?: string }): string {
  return typeof i === "string" ? i : i.message || i.code || JSON.stringify(i);
}

/** Readable name for a saved experiment metric key, e.g. test_f1_macro → "test F1 (macro)". */
export function metricLabel(key: string): string {
  return key
    .replace(/f1_macro/g, "F1 (macro)")
    .replace(/accuracy/g, "accuracy")
    .replace(/^n_/, "n ")
    .replace(/_/g, " ");
}

export function fmtMetric(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (v == null) return "—";
  return typeof v === "string" ? v : JSON.stringify(v);
}
