import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { WorkflowInstance, Workflow } from "../types/api";

export default function InstancesPage() {
  const qc = useQueryClient();
  const [filterWorkflow, setFilterWorkflow] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [selectedWf, setSelectedWf] = useState("");
  const [createError, setCreateError] = useState("");

  const { data: instances = [], isLoading } = useQuery<WorkflowInstance[]>({
    queryKey: ["instances"],
    queryFn: async () => (await apiClient.get("/instances/")).data.results ?? [],
  });

  const { data: workflows = [] } = useQuery<Workflow[]>({
    queryKey: ["workflows"],
    queryFn: async () => (await apiClient.get("/workflows/")).data.results ?? [],
  });

  const createMutation = useMutation({
    mutationFn: async (wfId: string) =>
      (await apiClient.post("/instances/", { workflow_definition: wfId })).data,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["instances"] });
      setShowCreate(false);
      setSelectedWf("");
      setCreateError("");
    },
    onError: (err: any) => setCreateError(err?.response?.data?.detail ?? "Failed to create instance"),
  });

  const filtered = filterWorkflow
    ? instances.filter((i) => i.workflow_definition_name.toLowerCase().includes(filterWorkflow.toLowerCase()))
    : instances;

  const activeCount = instances.filter((i) => !(i as any).completed_at).length;
  const doneCount = instances.filter((i) => (i as any).completed_at).length;

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>Instances</h2>
          <p>{instances.length} total · {activeCount} active · {doneCount} completed</p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
          + New Instance
        </button>
      </div>

      {/* Create panel */}
      {showCreate && (
        <div className="card mb-4">
          <h3 style={{ marginBottom: 12, fontSize: "0.95rem" }}>Start a new instance</h3>
          <div className="form-group">
            <label>Workflow Definition</label>
            <select value={selectedWf} onChange={(e) => setSelectedWf(e.target.value)}>
              <option value="">Select a workflow…</option>
              {(workflows as Workflow[]).filter((w) => w.is_active).map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </div>
          {createError && <div className="alert alert-error">{createError}</div>}
          <div className="flex gap-2">
            <button
              className="btn-primary btn-sm"
              disabled={!selectedWf || createMutation.isPending}
              onClick={() => createMutation.mutate(selectedWf)}
            >
              {createMutation.isPending ? "Creating…" : "Create"}
            </button>
            <button className="btn-secondary btn-sm" onClick={() => { setShowCreate(false); setCreateError(""); }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="card">
        {/* Filter bar */}
        <div style={{ marginBottom: 14 }}>
          <input
            placeholder="Filter by workflow name…"
            value={filterWorkflow}
            onChange={(e) => setFilterWorkflow(e.target.value)}
            style={{ maxWidth: 300 }}
          />
        </div>

        {isLoading ? (
          <div>{[1,2,3,4].map(i => <div key={i} className="skeleton" style={{ height: 44, marginBottom: 8, borderRadius: 6 }} />)}</div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <p>{filterWorkflow ? "No instances match that filter." : "No instances yet."}</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Workflow</th>
                <th>Current State</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((inst) => {
                const completed = Boolean((inst as any).completed_at);
                return (
                  <tr key={inst.id}>
                    <td>
                      <Link to={`/instances/${inst.id}`} style={{ fontFamily: "monospace", fontSize: "0.875rem" }}>
                        {inst.reference_number}
                      </Link>
                    </td>
                    <td className="text-sm">{inst.workflow_definition_name}</td>
                    <td>
                      <span className={`badge ${completed ? "badge-terminal" : "badge-active"}`}>
                        {inst.current_state_name}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${completed ? "badge-inactive" : "badge-active"}`}>
                        {completed ? "Completed" : "In Progress"}
                      </span>
                    </td>
                    <td className="text-muted text-sm">
                      {new Date((inst as any).created_at).toLocaleDateString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
