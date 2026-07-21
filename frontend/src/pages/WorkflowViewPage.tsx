import { useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { Transition, Workflow, WorkflowInstance } from "../types/api";
import { SHELL_REGISTRY } from "../components/shells";
import { useWorkspace } from "../hooks/useWorkspace";

/**
 * Renders a workflow through its configured shell (ui_schema.shell).
 * The page owns data fetching and the transition mutation; shells are pure
 * presentation and call back through the ShellProps contract.
 */
export default function WorkflowViewPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data: workspace } = useWorkspace();

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

  const transitionMutation = useMutation({
    mutationFn: async ({ instance, transition }: { instance: WorkflowInstance; transition: Transition }) =>
      (await apiClient.post(`/instances/${instance.id}/transition/`, { transition_id: transition.id })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instances", "by-workflow", id] });
      setError(null);
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Transition failed"),
  });

  if (!wf) return <div className="skeleton" style={{ height: 320, borderRadius: 10 }} />;

  // Per-workflow shell wins; the workspace default_view (VISION Layer 1) is
  // the fallback for workflows that never chose one.
  const shellName = wf.ui_schema?.shell ?? workspace?.ui_config?.default_view ?? "list";
  const Shell = SHELL_REGISTRY[shellName];

  // "list" (or anything unregistered) is the platform default instances view
  if (!Shell) return <Navigate to="/instances" replace />;

  const shellLabel = shellName.charAt(0).toUpperCase() + shellName.slice(1);

  return (
    <div>
      <div className="breadcrumb">
        <Link to="/workflows">Workflows</Link>
        <span>/</span>
        <Link to={`/workflows/${id}`}>{wf.name}</Link>
        <span>/</span>
        <span style={{ color: "var(--text-primary)" }}>{shellLabel}</span>
      </div>

      <div className="page-header">
        <div className="page-header-left">
          <h2>{wf.name}</h2>
          <p>
            {shellName === "kanban"
              ? "Drag a card to a column to fire the transition. Rules and approvals still apply."
              : `${instances.length} instances · ${shellLabel.toLowerCase()} view`}
          </p>
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

      <Shell
        workflow={wf}
        instances={instances}
        fireTransition={(instance, transition) => transitionMutation.mutate({ instance, transition })}
        transitionPending={transitionMutation.isPending}
      />
    </div>
  );
}
