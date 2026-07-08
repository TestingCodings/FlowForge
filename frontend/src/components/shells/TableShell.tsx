import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { WorkflowInstance } from "../../types/api";
import { formatDate } from "../../hooks/useWorkspace";
import { instanceTitle, ShellProps, stateColour } from "./types";

const DEFAULT_COLUMNS = ["reference", "state", "sla", "created"];

const BUILTIN_LABELS: Record<string, string> = {
  reference: "Reference",
  state: "State",
  sla: "SLA",
  status: "Status",
  created: "Created",
  title: "Title",
};

function cellValue(col: string, inst: WorkflowInstance): string | number {
  if (col.startsWith("metadata.")) {
    const v = (inst.metadata_json ?? {})[col.slice(9)];
    return v === undefined || v === null ? "" : (typeof v === "number" ? v : String(v));
  }
  switch (col) {
    case "reference": return inst.reference_number;
    case "state":     return inst.current_state_name;
    case "status":    return inst.completed_at ? "Completed" : "In Progress";
    case "created":   return inst.created_at;
    case "sla":       return inst.sla?.status ?? "";
    default:          return "";
  }
}

export default function TableShell({ workflow, instances }: ShellProps) {
  const navigate = useNavigate();
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  const columns: string[] = workflow.ui_schema?.list_columns?.length
    ? workflow.ui_schema.list_columns
    : DEFAULT_COLUMNS;

  const hasTitle = Boolean(workflow.ui_schema?.title_field);

  const sorted = useMemo(() => {
    if (!sortCol) return instances;
    return [...instances].sort((a, b) => {
      const va = cellValue(sortCol, a);
      const vb = cellValue(sortCol, b);
      const cmp = typeof va === "number" && typeof vb === "number"
        ? va - vb
        : String(va).localeCompare(String(vb));
      return sortAsc ? cmp : -cmp;
    });
  }, [instances, sortCol, sortAsc]);

  const header = (col: string) =>
    BUILTIN_LABELS[col] ?? (col.startsWith("metadata.") ? col.slice(9) : col);

  const toggleSort = (col: string) => {
    if (sortCol === col) setSortAsc(a => !a);
    else { setSortCol(col); setSortAsc(true); }
  };

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table className="table" style={{ margin: 0 }}>
        <thead>
          <tr>
            {hasTitle && <th>Title</th>}
            {columns.map(col => (
              <th key={col} onClick={() => toggleSort(col)} style={{ cursor: "pointer", userSelect: "none" }}>
                {header(col)}
                {sortCol === col && <span style={{ marginLeft: 4 }}>{sortAsc ? "↑" : "↓"}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(inst => (
            <tr
              key={inst.id}
              onClick={() => navigate(`/instances/${inst.id}`)}
              style={{ cursor: "pointer" }}
            >
              {hasTitle && (
                <td style={{ fontWeight: 600 }}>{instanceTitle(workflow, inst) ?? "—"}</td>
              )}
              {columns.map(col => {
                if (col === "reference") {
                  return (
                    <td key={col} style={{ fontFamily: "monospace", fontSize: "0.82rem", color: "var(--accent-light)" }}>
                      {inst.reference_number}
                    </td>
                  );
                }
                if (col === "state") {
                  const colour = stateColour(workflow, inst.current_state_name);
                  return (
                    <td key={col}>
                      <span
                        className={`badge ${inst.completed_at ? "badge-terminal" : "badge-active"}`}
                        style={colour ? { background: `${colour}22`, color: colour, border: `1px solid ${colour}55` } : undefined}
                      >
                        {inst.current_state_name}
                      </span>
                    </td>
                  );
                }
                if (col === "sla") {
                  const s = inst.sla?.status;
                  return (
                    <td key={col}>
                      {!s || s === "ok" || inst.completed_at ? (
                        <span className="text-muted text-xs">—</span>
                      ) : (
                        <span className="text-xs" style={{ fontWeight: 700, color: s === "breached" ? "var(--danger)" : "var(--warning)" }}>
                          ⏱ {s === "breached" ? "OVERDUE" : "DUE SOON"}
                        </span>
                      )}
                    </td>
                  );
                }
                if (col === "created") {
                  return <td key={col} className="text-muted text-sm">{formatDate(inst.created_at)}</td>;
                }
                if (col === "status") {
                  return (
                    <td key={col}>
                      <span className={`badge ${inst.completed_at ? "badge-inactive" : "badge-active"}`}>
                        {inst.completed_at ? "Completed" : "In Progress"}
                      </span>
                    </td>
                  );
                }
                return <td key={col} className="text-sm">{String(cellValue(col, inst))}</td>;
              })}
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr><td colSpan={columns.length + (hasTitle ? 1 : 0)} className="text-muted text-sm" style={{ textAlign: "center", padding: 24 }}>No instances yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
