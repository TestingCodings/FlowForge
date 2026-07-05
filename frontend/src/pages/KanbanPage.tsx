import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { Workflow, WorkflowInstance, State, Transition } from "../types/api";

/**
 * Layer 2 — Kanban shell. Columns are workflow states; cards are instances.
 * Dragging a card to another column fires the matching transition, so the
 * board is a live view of the engine, not a separate data model: rule blocks,
 * approval gating, and required forms all still apply.
 */
export default function KanbanPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [dragging, setDragging] = useState<WorkflowInstance | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: wf } = useQuery<Workflow>({
    queryKey: ["workflow", id],
    queryFn: async () => (await apiClient.get(`/workflows/${id}/`)).data,
    enabled: Boolean(id),
  });

  const { data: instances = [] } = useQuery<WorkflowInstance[]>({
    queryKey: ["instances", "by-workflow", id],
    queryFn: async () =>
      (await apiClient.get(`/instances/?workflow_definition=${id}`)).data.results ?? [],
    enabled: Boolean(id),
  });

  const states: State[] = useMemo(
    () => [...(wf?.states ?? [])].sort((a, b) => a.position_order - b.position_order),
    [wf],
  );
  const transitions: Transition[] = wf?.transitions ?? [];
  const cardFields: string[] = wf?.ui_schema?.card_fields ?? [];

  const byState = useMemo(() => {
    const map: Record<string, WorkflowInstance[]> = {};
    for (const s of states) map[s.id] = [];
    for (const i of instances) (map[i.current_state] ??= []).push(i);
    return map;
  }, [states, instances]);

  const transitionMutation = useMutation({
    mutationFn: async ({ instance, transition }: { instance: WorkflowInstance; transition: Transition }) =>
      (await apiClient.post(`/instances/${instance.id}/transition/`, { transition_id: transition.id })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instances", "by-workflow", id] });
      setError(null);
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Transition failed"),
  });

  const findTransition = (fromStateId: string, toStateId: string) =>
    transitions.find(t => t.from_state === fromStateId && t.to_state === toStateId);

  const onDrop = (toStateId: string) => {
    setDropTarget(null);
    if (!dragging) return;
    const inst = dragging;
    setDragging(null);
    if (inst.current_state === toStateId) return;
    const tr = findTransition(inst.current_state, toStateId);
    if (!tr) {
      const toState = states.find(s => s.id === toStateId);
      setError(`No transition from '${inst.current_state_name}' to '${toState?.display_name || toState?.name}'.`);
      return;
    }
    transitionMutation.mutate({ instance: inst, transition: tr });
  };

  if (!wf) return <div className="skeleton" style={{ height: 320, borderRadius: 10 }} />;

  return (
    <div>
      <div className="breadcrumb">
        <Link to="/workflows">Workflows</Link>
        <span>/</span>
        <Link to={`/workflows/${id}`}>{wf.name}</Link>
        <span>/</span>
        <span style={{ color: "var(--text-primary)" }}>Board</span>
      </div>

      <div className="page-header">
        <div className="page-header-left">
          <h2>{wf.name} — Board</h2>
          <p>Drag a card to a column to fire the transition. Rules and approvals still apply.</p>
        </div>
        <Link to={`/workflows/${id}`} className="btn-secondary btn-sm" style={{ textDecoration: "none" }}>
          Workflow settings
        </Link>
      </div>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: 14 }}>
          <span>⚠</span>
          <div style={{ flex: 1 }}>{error}</div>
          <button className="btn-ghost btn-sm" onClick={() => setError(null)}>✕</button>
        </div>
      )}

      <div style={{ display: "flex", gap: 12, alignItems: "flex-start", overflowX: "auto", paddingBottom: 12 }}>
        {states.map(state => {
          const cards = byState[state.id] ?? [];
          const isTarget = dropTarget === state.id;
          const canReceive = dragging && dragging.current_state !== state.id
            && Boolean(findTransition(dragging.current_state, state.id));
          return (
            <div
              key={state.id}
              data-col={state.name}
              onDragOver={e => { e.preventDefault(); setDropTarget(state.id); }}
              onDragLeave={() => setDropTarget(cur => (cur === state.id ? null : cur))}
              onDrop={() => onDrop(state.id)}
              style={{
                minWidth: 250, maxWidth: 290, flex: "1 0 250px",
                background: "var(--bg-surface)",
                border: `1px solid ${isTarget ? (canReceive ? "var(--success)" : "var(--danger)") : "var(--border)"}`,
                borderRadius: 10, padding: 10,
                transition: "border-color 120ms",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "2px 6px 10px" }}>
                <span className="text-sm" style={{ fontWeight: 700 }}>
                  {state.display_name || state.name}
                  {state.is_terminal && <span className="text-xs text-muted"> · end</span>}
                </span>
                <span className="badge badge-inactive">{cards.length}</span>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8, minHeight: 60 }}>
                {cards.map(inst => (
                  <div
                    key={inst.id}
                    data-card={inst.reference_number}
                    draggable={!inst.completed_at}
                    onDragStart={() => setDragging(inst)}
                    onDragEnd={() => { setDragging(null); setDropTarget(null); }}
                    style={{
                      background: "var(--bg-elevated)", border: "1px solid var(--border)",
                      borderRadius: 8, padding: "10px 12px",
                      cursor: inst.completed_at ? "default" : "grab",
                      opacity: dragging?.id === inst.id ? 0.4 : 1,
                    }}
                  >
                    <Link
                      to={`/instances/${inst.id}`}
                      style={{ fontFamily: "monospace", fontSize: "0.82rem", fontWeight: 600, color: "var(--accent-light)" }}
                    >
                      {inst.reference_number}
                    </Link>
                    {cardFields.length > 0 && (
                      <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 2 }}>
                        {cardFields.map(f => {
                          const v = (inst.metadata_json ?? {})[f];
                          if (v === undefined || v === null || v === "") return null;
                          return (
                            <div key={f} className="text-xs" style={{ display: "flex", gap: 6 }}>
                              <span className="text-muted" style={{ fontFamily: "monospace" }}>{f}:</span>
                              <span>{String(v)}</span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {inst.sla && inst.sla.status !== "ok" && !inst.completed_at && (
                      <div className="text-xs" style={{ marginTop: 6, color: inst.sla.status === "breached" ? "var(--danger)" : "var(--warning)", fontWeight: 700 }}>
                        ⏱ {inst.sla.status === "breached" ? "OVERDUE" : "DUE SOON"}
                      </div>
                    )}
                  </div>
                ))}
                {cards.length === 0 && (
                  <div className="text-xs text-muted" style={{ textAlign: "center", padding: "16px 0", border: "1px dashed var(--border)", borderRadius: 8 }}>
                    empty
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
