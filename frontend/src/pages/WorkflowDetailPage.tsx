import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { Workflow } from "../types/api";
import StateGraph from "../components/StateGraph";

export default function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [createMsg, setCreateMsg] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  const { data: wf, isLoading } = useQuery<Workflow>({
    queryKey: ["workflow", id],
    queryFn: async () => (await apiClient.get(`/workflows/${id}/`)).data,
    enabled: Boolean(id),
  });

  const createInstance = useMutation({
    mutationFn: async () =>
      (await apiClient.post("/instances/", { workflow_definition: id })).data,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["instances"] });
      setCreateMsg(`Created ${data.reference_number}`);
      setCreateError(null);
      setTimeout(() => setCreateMsg(null), 4000);
    },
    onError: (err: any) => setCreateError(err?.response?.data?.detail ?? "Failed to create"),
  });

  if (isLoading) {
    return (
      <div>
        <div className="breadcrumb"><Link to="/workflows">Workflows</Link><span>/</span>Loading…</div>
        <div className="skeleton" style={{ height: 300, borderRadius: 14, marginTop: 16 }} />
      </div>
    );
  }

  if (!wf) {
    return <div className="card empty-state"><p>Workflow not found.</p></div>;
  }

  return (
    <div>
      <div className="breadcrumb">
        <Link to="/workflows">Workflows</Link>
        <span>/</span>
        <span style={{ color: "var(--text-primary)" }}>{wf.name}</span>
      </div>

      <div className="page-header" style={{ marginTop: 8 }}>
        <div className="page-header-left">
          <h2>{wf.name}</h2>
          <p>{wf.description || "No description"}</p>
        </div>
        <div className="flex gap-2 items-center">
          <span className="badge badge-role-workflow_designer" style={{ fontFamily: "monospace" }}>{wf.reference_prefix}</span>
          <span className={`badge ${wf.is_active ? "badge-active" : "badge-inactive"}`}>
            {wf.is_active ? "Active" : "Inactive"}
          </span>
          <span className="badge badge-inactive">v{wf.version}</span>
        </div>
      </div>

      {/* State graph */}
      <div className="mb-4">
        <StateGraph
          states={wf.states ?? []}
          transitions={wf.transitions ?? []}
          currentStateId={(wf.states ?? []).find((s) => s.is_initial)?.id ?? ""}
        />
      </div>

      {/* Create instance banner */}
      {wf.is_active && (
        <div className="card mb-4" style={{ background: "rgba(99,102,241,0.07)", borderColor: "rgba(99,102,241,0.3)" }}>
          <div className="flex items-center gap-3">
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, marginBottom: 3 }}>Start a new instance</div>
              <div className="text-sm text-muted">Creates a new {wf.reference_prefix} case at the "{(wf.states ?? []).find(s => s.is_initial)?.display_name}" state</div>
            </div>
            <button
              className="btn-primary"
              onClick={() => createInstance.mutate()}
              disabled={createInstance.isPending}
            >
              {createInstance.isPending ? "Creating…" : `+ New ${wf.reference_prefix}`}
            </button>
          </div>
          {createMsg && <div className="alert alert-success mt-2">{createMsg}</div>}
          {createError && <div className="alert alert-error mt-2">{createError}</div>}
        </div>
      )}

      <div className="grid grid-2">
        {/* States */}
        <div className="card">
          <div className="card-header">
            <h3>States</h3>
            <span className="badge badge-inactive">{wf.states?.length ?? 0}</span>
          </div>
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Type</th><th>SLA (hrs)</th></tr>
            </thead>
            <tbody>
              {(wf.states ?? []).sort((a, b) => a.position_order - b.position_order).map((s) => (
                <tr key={s.id}>
                  <td style={{ fontWeight: 500 }}>{s.display_name || s.name}</td>
                  <td>
                    {s.is_initial && <span className="badge badge-initial">Start</span>}
                    {s.is_terminal && <span className="badge badge-terminal">End</span>}
                    {!s.is_initial && !s.is_terminal && <span className="badge badge-inactive">Step</span>}
                  </td>
                  <td className="text-muted text-sm">
                    {(s.sla_config as any)?.sla_hours ? `${(s.sla_config as any).sla_hours}h` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Transitions */}
        <div className="card">
          <div className="card-header">
            <h3>Transitions</h3>
            <span className="badge badge-inactive">{wf.transitions?.length ?? 0}</span>
          </div>
          <table className="table">
            <thead>
              <tr><th>Name</th><th>From → To</th><th>Approval</th></tr>
            </thead>
            <tbody>
              {(wf.transitions ?? []).map((t) => {
                const from = (wf.states ?? []).find(s => s.id === t.from_state);
                const to   = (wf.states ?? []).find(s => s.id === t.to_state);
                return (
                  <tr key={t.id}>
                    <td style={{ fontWeight: 500 }}>{t.name}</td>
                    <td className="text-sm text-muted">
                      {from?.name ?? "?"} → {to?.name ?? "?"}
                    </td>
                    <td>
                      {t.requires_approval
                        ? <span className="badge badge-pending">Required</span>
                        : <span className="badge badge-inactive">None</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Rules */}
        {(wf.rules ?? []).length > 0 && (
          <div className="card" style={{ gridColumn: "1 / -1" }}>
            <div className="card-header">
              <h3>Rules</h3>
              <span className="badge badge-warning">{wf.rules.length} rules</span>
            </div>
            <table className="table">
              <thead>
                <tr><th>Transition</th><th>Condition</th><th>Action</th><th>Priority</th></tr>
              </thead>
              <tbody>
                {(wf.rules ?? []).map((r) => {
                  const tr = (wf.transitions ?? []).find(t => t.id === r.transition);
                  const cond = r.condition as any;
                  const act  = r.action as any;
                  return (
                    <tr key={r.id}>
                      <td className="text-sm">{tr?.name ?? r.transition}</td>
                      <td className="text-sm text-muted font-mono">
                        {cond.field} {cond.operator} {String(cond.value)}
                      </td>
                      <td>
                        <span className={`badge ${act.type === "block_transition" ? "badge-danger" : "badge-warning"}`}>
                          {act.type.replace(/_/g, " ")}
                        </span>
                        {act.reason && <span className="text-xs text-muted" style={{ marginLeft: 6 }}>{act.reason}</span>}
                      </td>
                      <td className="text-muted text-sm">{r.priority}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
