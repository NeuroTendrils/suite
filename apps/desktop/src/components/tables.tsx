import type { EpochSetSummary, Split } from "../types";
import { fmtDate, fmtMetric } from "../lib/format";
import { Badge } from "./ui";

export function ValidationBadge({ ok, errors, warnings }: { ok: boolean | null; errors: number; warnings: number }) {
  if (ok == null) return <Badge>not validated</Badge>;
  if (!ok) return <Badge tone="danger">{errors} error{errors === 1 ? "" : "s"}</Badge>;
  if (warnings) return <Badge tone="warn">{warnings} warning{warnings === 1 ? "" : "s"}</Badge>;
  return <Badge tone="ok">valid</Badge>;
}

export function EpochTable({ rows }: { rows: EpochSetSummary[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th className="r">Trials</th>
            <th>Events</th>
            <th className="r">Window (s)</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id}>
              <td>{e.name}</td>
              <td className="r num">{e.n_trials}</td>
              <td>{e.event_names.join(", ") || "—"}</td>
              <td className="r num">
                {e.tmin} – {e.tmax}
              </td>
              <td className="muted">{fmtDate(e.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SplitTable({ rows, selected, onSelect }: { rows: Split[]; selected: string; onSelect: (id: string) => void }) {
  return (
    <div className="table-wrap">
      <table className="table table-click">
        <thead>
          <tr>
            <th />
            <th>Method</th>
            <th className="r">Train</th>
            <th className="r">Val</th>
            <th className="r">Test</th>
            <th className="r">Seed</th>
            <th>Leakage check</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id} className={s.id === selected ? "selected" : ""} onClick={() => onSelect(s.id)}>
              <td>
                <input type="radio" readOnly checked={s.id === selected} aria-label="Select split" />
              </td>
              <td>{s.method}</td>
              <td className="r num">{s.train_indices.length}</td>
              <td className="r num">{s.val_indices.length}</td>
              <td className="r num">{s.test_indices.length}</td>
              <td className="r num">{fmtMetric(s.parameters?.seed)}</td>
              <td>
                {s.leakage_check?.ok === false ? (
                  <span title={(s.leakage_check.warnings || []).join("\n")}>
                    <Badge tone="warn">{s.leakage_check.warnings?.length ?? 0} warning(s)</Badge>
                  </span>
                ) : s.leakage_check?.ok ? (
                  <Badge tone="ok">ok</Badge>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td className="muted">{fmtDate(s.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
