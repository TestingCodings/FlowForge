import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { WorkflowInstance, Transition, AuditEntry } from "../types/api";
import StateGraph from "../components/StateGraph";

export default function InstanceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [blockReason, setBlockReason] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Fetch the instance
  const { data: instance, isLoading } = useQuery<WorkflowInstance>({
    queryKey: ["instance", id],
    queryFn: async () => (await apiClient.get(`/instances/${id}/`)).data,
    enabled: Boolean(id),
  });

  // Fetch the full workflow definition (for graph + available transitions)
  const { data: workflow } = useQuery({
    queryKey: ["workflow", instance?.workflow_definition],
    queryFn: async () => (await apiClient.get(`/workflows/${instance!.workflow_definition}/`)).data,
    enabled: Boolean(instance?.workflow_definition),
  });

  // Fetch audit trail
  const { data: auditData } = useQuery<{ results: AuditEntry[] }>({
    queryKey: ["audit-trail", id],
    queryFn: async () => (await apiClient.get(`/audit/${id}/`)).data,
    enabled: Boolean(id),
  });

  // Transitions available from current state
  const availableTransitions: Transition[] = (workflow?.transitions ?? []).filter(
    (t: Transition) => t.from_state === instance?.current_state
  );

  // Visited state names from audit trail
  const visitedStateNames: string[] = [
    ...(auditData?.results ?? [])
      .filter((e) => e.to_state)
      .map((e) => e.to_state as string),
  ];

  const transitionMutation = useMutation({
    mutationFn: async (transition_id: string) => {
      const res = await apiClient.post(`/instances/${id}/transition/`, { transition_id });
      return res.data;
    },
    onSuccess: (data) => {
      setBlockReason(null);
      setSuccessMsg(`Moved to "${data.current_state_name}"`);
      qc.invalidateQueries({ queryKey: ["instance", id] });
      qc.invalidateQueries({ queryKey: ["audit-trail", id] });
      qc.invalidateQueries({ queryKey: ["instances"] });
      setTimeout(() => setSuccessMsg(null), 3000);
    },
    onError: (err: any) => {
      setSuccessMsg(null);
      setBlockReason(err?.response?.data?.detail ?? "Transition failed");
    },
  });

  if (isLoading) {
    return (
      <div>
        <div className="breadcrumb"><Link to="/instances">Instances</Link><span>/</span>Loading…</div>
        <div className="skeleton" style={{ height: 300, borderRadius: 14 }} />
      </div>
    );
  }

  if (!instance) {
    return (
      <div>
        <div className="breadcrumb"><Link to="/instances">Instances</Link><span>/</span>Not found</div>
        <div className="card empty-state"><p>Instance not found.</p></div>
      </div>
    );
  }

  const isCompleted = Boolean(instance.completed_at);

  return (
    <div>
      {/* Breadcrumb */}
      <div className="breadcrumb">
        <Link to="/instances">Instances</Link>
        <span>/</span>
        <span style={{ color: "var(--text-primary)" }}>{instance.reference_number}</span>
      </div>

      {/* Page header */}
      <div className="page-header">
        <div className="page-header-left">
          <h2>{instance.reference_number}</h2>
          <p>{instance.workflow_definition_name}</p>
        </div>
        <span className={`badge ${isCompleted ? "badge-terminal" : "badge-active"}`}>
          {isCompleted ? "Completed" : "In Progress"}
        </span>
      </div>

      {/* State graph */}
      {workflow && (
        <div className="mb-4">
          <StateGraph
            states={workflow.states ?? []}
            transitions={workflow.transitions ?? []}
            currentStateId={instance.current_state}
            visitedStateNames={visitedStateNames}
            isTerminal={isCompleted}
          />
        </div>
      )}

      {/* Alert banners */}
      {blockReason && (
        <div className="alert alert-error">
          <span>⚠</span>
          <div>
            <strong>Transition blocked</strong>
            <div style={{ marginTop: 2 }}>{blockReason}</div>
          </div>
        </div>
      )}
      {successMsg && (
        <div className="alert alert-success">
          <span>✓</span> {successMsg}
        </div>
      )}

      <div className="grid grid-2">
        {/* Transitions panel */}
        <div className="card">
          <div className="card-header">
            <h3>Available Transitions</h3>
          </div>
          {isCompleted ? (
            <div className="empty-state" style={{ padding: "24px 0" }}>
              <p>This instance is complete — no further transitions.</p>
            </div>
          ) : availableTransitions.length === 0 ? (
            <div className="empty-state" style={{ padding: "24px 0" }}>
              <p>No transitions available from current state.</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {availableTransitions.map((t) => {
                const toState = (workflow?.states ?? []).find((s: any) => s.id === t.to_state);
                return (
                  <button
                    key={t.id}
                    className="transition-btn"
                    onClick={() => transitionMutation.mutate(t.id)}
                    disabled={transitionMutation.isPending}
                  >
                    <span className="t-name">{t.display_name || t.name}</span>
                    <span className="t-arrow">
                      {instance.current_state_name} → {toState?.display_name || toState?.name || "…"}
                      {t.requires_approval && " · requires approval"}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          <div className="divider" />

          {/* Current state details */}
          <div>
            <div className="text-xs text-muted mb-2" style={{ textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 }}>Current State</div>
            <span className="badge badge-active">{instance.current_state_name}</span>
          </div>
        </div>

        {/* Metadata */}
        <div className="card">
          <div className="card-header"><h3>Metadata</h3></div>
          {Object.keys(instance.metadata_json ?? {}).length === 0 ? (
            <p className="text-muted text-sm">No metadata recorded.</p>
          ) : (
            <table className="table">
              <tbody>
                {Object.entries(instance.metadata_json ?? {}).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ color: "var(--text-secondary)", width: "40%", fontFamily: "monospace", fontSize: "0.8rem" }}>{k}</td>
                    <td style={{ fontWeight: 500 }}>{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {instance.completed_at && (
            <>
              <div className="divider" />
              <div className="text-sm text-muted">
                Completed {new Date(instance.completed_at).toLocaleString()}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Audit trail */}
      <div className="card mt-4">
        <div className="card-header"><h3>Audit Trail</h3></div>
        {(auditData?.results ?? []).length === 0 ? (
          <p className="text-muted text-sm">No audit entries yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Event</th>
                <th>From</th>
                <th>To</th>
                <th>Actor</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {(auditData?.results ?? []).map((entry: AuditEntry) => (
                <tr key={entry.id}>
                  <td>
                    <span className={`badge ${auditBadgeClass(entry.action_type)}`}>
                      {entry.action_type.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="text-muted text-sm">{entry.from_state ?? "—"}</td>
                  <td className="text-sm">{entry.to_state ?? "—"}</td>
                  <td className="text-sm">{entry.actor_email ?? "—"}</td>
                  <td className="text-muted text-sm">{new Date(entry.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function auditBadgeClass(action: string) {
  if (action.includes("transition")) return "badge-active";
  if (action.includes("created"))    return "badge-initial";
  if (action.includes("rule"))       return "badge-warning";
  return "badge-inactive";
}
