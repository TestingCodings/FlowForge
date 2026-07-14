import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { formatDate } from "../hooks/useWorkspace";
import { Workflow, WorkflowInstance } from "../types/api";
import Hint from "./Hint";

interface Props {
  instance: WorkflowInstance;
  workflow: Workflow | undefined;
  canEdit: boolean;
}

/**
 * Sub-instances of a container instance (docs/UX.md section 3).
 * Shown when the workflow's ui_schema.children allows nesting, or when
 * children already exist (e.g. config was later removed).
 */
export default function ChildrenPanel({ instance, workflow, canEdit }: Props) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [childWfName, setChildWfName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const config = workflow?.ui_schema?.children;
  const allowedNames = config?.workflows ?? [];

  const { data: children = [] } = useQuery<WorkflowInstance[]>({
    queryKey: ["children", instance.id],
    queryFn: async () => (await apiClient.get(`/instances/${instance.id}/children/`)).data,
  });

  const { data: allWorkflows = [] } = useQuery<Workflow[]>({
    queryKey: ["workflows"],
    queryFn: async () => (await apiClient.get("/workflows/")).data.results ?? [],
    enabled: allowedNames.length > 0,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["children", instance.id] });
    qc.invalidateQueries({ queryKey: ["instance", instance.id] });
  };

  const addChild = useMutation({
    mutationFn: async () => {
      const wf = allWorkflows.find(w => w.name === childWfName);
      if (!wf) throw new Error("Pick a workflow.");
      return (await apiClient.post("/instances/", {
        workflow_definition: wf.id,
        parent: instance.id,
      })).data;
    },
    onSuccess: () => {
      invalidate();
      setErr(null);
      setAdding(false);
      setChildWfName("");
    },
    onError: (e: any) =>
      setErr(
        e?.response?.data?.non_field_errors?.[0] ??
        e?.response?.data?.detail ??
        e?.message ??
        "Failed to create sub-instance",
      ),
  });

  const detach = useMutation({
    mutationFn: async (childId: string) =>
      apiClient.patch(`/instances/${childId}/move/`, { parent: null }),
    onSuccess: invalidate,
  });

  if (allowedNames.length === 0 && children.length === 0) return null;

  const total = children.length;
  const done = children.filter(c => c.completed_at).length;
  const pct = total ? Math.round((done / total) * 100) : 0;
  const rollUp = config?.roll_up ?? true;
  const extraCols = (config?.columns ?? []).filter(c => c.startsWith("metadata."));

  return (
    <div className="card mt-4">
      <div className="card-header">
        <h3>Sub-instances <Hint tip="Smaller pieces of work that live inside this one — like test runs inside a release. Rules can stop the parent from finishing until every sub-instance is complete." /></h3>
        <div className="flex gap-2 items-center">
          <span className="badge badge-inactive">{done}/{total} complete</span>
          {canEdit && allowedNames.length > 0 && !instance.completed_at && (
            <button
              className={adding ? "btn-secondary btn-sm" : "btn-primary btn-sm"}
              onClick={() => setAdding(!adding)}
            >
              {adding ? "Cancel" : "+ Add sub-instance"}
            </button>
          )}
        </div>
      </div>

      {rollUp && total > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ height: 8, borderRadius: 99, background: "var(--bg-elevated)", overflow: "hidden" }}>
            <div style={{
              height: "100%", width: `${pct}%`, borderRadius: 99,
              background: pct === 100 ? "var(--success)" : "var(--accent)",
              transition: "width 300ms",
            }} />
          </div>
          <div className="text-xs text-muted" style={{ marginTop: 4 }}>{pct}% complete</div>
        </div>
      )}

      {adding && (
        <div style={{
          display: "flex", gap: 10, alignItems: "flex-end", marginBottom: 14,
          background: "var(--bg-elevated)", border: "1px solid var(--border)",
          borderRadius: 10, padding: 12,
        }}>
          <div className="form-group" style={{ marginBottom: 0, flex: 1 }}>
            <label>Workflow</label>
            <select value={childWfName} onChange={e => setChildWfName(e.target.value)}>
              <option value="">Choose…</option>
              {allowedNames.map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <button
            className="btn-primary btn-sm"
            onClick={() => addChild.mutate()}
            disabled={addChild.isPending || !childWfName}
          >
            {addChild.isPending ? "Creating…" : "Create"}
          </button>
        </div>
      )}

      {err && <div className="alert alert-error mb-2">{err}</div>}

      {children.length === 0 ? (
        <p className="text-muted text-sm">
          No sub-instances yet.
          {allowedNames.length > 0 && ` This ${workflow?.name ?? "instance"} can contain: ${allowedNames.join(", ")}.`}
        </p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Reference</th>
              <th>Workflow</th>
              <th>State</th>
              {extraCols.map(c => <th key={c}>{c.slice(9)}</th>)}
              <th>Created</th>
              {canEdit && <th style={{ width: 44 }}></th>}
            </tr>
          </thead>
          <tbody>
            {children.map(child => (
              <tr key={child.id}>
                <td>
                  <Link to={`/instances/${child.id}`} style={{ fontFamily: "monospace", fontSize: "0.82rem", color: "var(--accent-light)" }}>
                    {child.reference_number}
                  </Link>
                </td>
                <td className="text-sm text-muted">{child.workflow_definition_name}</td>
                <td>
                  <span className={`badge ${child.completed_at ? "badge-terminal" : "badge-active"}`}>
                    {child.current_state_name}
                  </span>
                  {child.sla && child.sla.status !== "ok" && !child.completed_at && (
                    <span className="text-xs" style={{ marginLeft: 6, color: child.sla.status === "breached" ? "var(--danger)" : "var(--warning)", fontWeight: 700 }}>
                      ⏱
                    </span>
                  )}
                </td>
                {extraCols.map(c => (
                  <td key={c} className="text-sm">
                    {String((child.metadata_json ?? {})[c.slice(9)] ?? "")}
                  </td>
                ))}
                <td className="text-sm text-muted">{formatDate(child.created_at)}</td>
                {canEdit && (
                  <td>
                    <button
                      className="btn-ghost btn-sm"
                      title="Detach from this parent"
                      style={{ color: "var(--danger)", padding: "4px 8px" }}
                      onClick={() => detach.mutate(child.id)}
                    >
                      ✕
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
