import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { WorkflowInstance, Workflow, Transition, SlaInfo } from "../types/api";
import { formatDate } from "../hooks/useWorkspace";

interface BulkResult {
  transition: string;
  requested: number;
  succeeded: number;
  failed: number;
  results: { id: string; reference_number?: string; status: string; detail: string }[];
}

function SlaBadge({ sla }: { sla: SlaInfo | null | undefined }) {
  if (!sla || sla.status === "ok") return null;
  const isBreached = sla.status === "breached";
  return (
    <span
      title={`SLA ${isBreached ? "breached" : "warning"}: ${sla.elapsed_hours}h / ${sla.sla_hours}h`}
      style={{
        display: "inline-flex", alignItems: "center", gap: 3,
        fontSize: "0.7rem", fontWeight: 700, padding: "1px 6px",
        borderRadius: 99, marginLeft: 6,
        background: isBreached ? "rgba(239,68,68,0.15)" : "rgba(245,158,11,0.15)",
        color: isBreached ? "#f87171" : "#fbbf24",
        border: `1px solid ${isBreached ? "rgba(239,68,68,0.3)" : "rgba(245,158,11,0.3)"}`,
      }}
    >
      ⏱ {isBreached ? "OVERDUE" : "DUE SOON"}
    </span>
  );
}

export default function InstancesPage() {
  const qc = useQueryClient();
  const [filterWorkflow, setFilterWorkflow] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [selectedWf, setSelectedWf] = useState("");
  const [createError, setCreateError] = useState("");

  // Bulk selection
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkTransitionId, setBulkTransitionId] = useState("");
  const [bulkResult, setBulkResult] = useState<BulkResult | null>(null);

  const [topLevelOnly, setTopLevelOnly] = useState(false);

  const { data: instances = [], isLoading } = useQuery<WorkflowInstance[]>({
    queryKey: ["instances", { topLevelOnly }],
    queryFn: async () =>
      (await apiClient.get(topLevelOnly ? "/instances/?parent__isnull=true" : "/instances/")).data.results ?? [],
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

  /* ── Bulk selection helpers ── */
  const toggleRow = (id: string) =>
    setSelected(cur => {
      const next = new Set(cur);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const allFilteredSelected = filtered.length > 0 && filtered.every(i => selected.has(i.id));
  const toggleAll = () =>
    setSelected(allFilteredSelected ? new Set() : new Set(filtered.map(i => i.id)));

  // Bulk transition is offered when every selected instance shares one workflow
  const selectedInstances = useMemo(
    () => instances.filter(i => selected.has(i.id)),
    [instances, selected],
  );
  const commonWorkflowId = useMemo(() => {
    const ids = new Set(selectedInstances.map(i => i.workflow_definition));
    return ids.size === 1 ? [...ids][0] : null;
  }, [selectedInstances]);

  const { data: commonWorkflow } = useQuery<Workflow>({
    queryKey: ["workflow", commonWorkflowId],
    queryFn: async () => (await apiClient.get(`/workflows/${commonWorkflowId}/`)).data,
    enabled: Boolean(commonWorkflowId),
  });

  // Only transitions leaving a state that at least one selected instance is in
  const bulkTransitions: Transition[] = useMemo(() => {
    if (!commonWorkflow) return [];
    const statesInUse = new Set(selectedInstances.map(i => i.current_state));
    return (commonWorkflow.transitions ?? []).filter(t => statesInUse.has(t.from_state));
  }, [commonWorkflow, selectedInstances]);

  const bulkMutation = useMutation({
    mutationFn: async () =>
      (await apiClient.post("/instances/bulk-transition/", {
        instance_ids: [...selected],
        transition_id: bulkTransitionId,
      })).data as BulkResult,
    onSuccess: (data) => {
      setBulkResult(data);
      setSelected(new Set());
      setBulkTransitionId("");
      qc.invalidateQueries({ queryKey: ["instances"] });
    },
  });

  const exportCsv = async () => {
    const resp = await apiClient.get(
      `/instances/export/?ids=${[...selected].join(",")}`,
      { responseType: "blob" },
    );
    const url = URL.createObjectURL(resp.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = "instances.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

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

      {/* Bulk result summary */}
      {bulkResult && (
        <div className={`alert ${bulkResult.failed === 0 ? "alert-success" : "alert-error"}`} style={{ marginBottom: 14 }}>
          <div style={{ flex: 1 }}>
            <strong>
              Bulk "{bulkResult.transition}": {bulkResult.succeeded} succeeded
              {bulkResult.failed > 0 && `, ${bulkResult.failed} failed`}
            </strong>
            {bulkResult.failed > 0 && (
              <ul style={{ margin: "6px 0 0 16px", fontSize: "0.82rem" }}>
                {bulkResult.results.filter(r => r.status !== "ok").map(r => (
                  <li key={r.id}>
                    <span style={{ fontFamily: "monospace" }}>{r.reference_number ?? r.id}</span>: {r.detail}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button className="btn-ghost btn-sm" onClick={() => setBulkResult(null)}>✕</button>
        </div>
      )}

      <div className="card">
        {/* Filter bar + bulk actions */}
        <div style={{ marginBottom: 14, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <input
            placeholder="Filter by workflow name…"
            value={filterWorkflow}
            onChange={(e) => setFilterWorkflow(e.target.value)}
            style={{ maxWidth: 300 }}
          />

          <label className="text-sm" style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={topLevelOnly}
              onChange={() => setTopLevelOnly(!topLevelOnly)}
            />
            Top-level only
          </label>

          {selected.size > 0 && (
            <div style={{
              display: "flex", gap: 8, alignItems: "center", marginLeft: "auto",
              padding: "6px 12px", borderRadius: 8,
              background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.3)",
            }}>
              <span className="text-sm" style={{ fontWeight: 600 }}>{selected.size} selected</span>

              {commonWorkflowId ? (
                <>
                  <select
                    value={bulkTransitionId}
                    onChange={e => setBulkTransitionId(e.target.value)}
                    style={{ fontSize: "0.82rem", padding: "4px 8px" }}
                  >
                    <option value="">Transition…</option>
                    {bulkTransitions.map(t => (
                      <option key={t.id} value={t.id}>
                        {t.display_name || t.name}{t.requires_approval ? " (approval)" : ""}
                      </option>
                    ))}
                  </select>
                  <button
                    className="btn-primary btn-sm"
                    disabled={!bulkTransitionId || bulkMutation.isPending}
                    onClick={() => bulkMutation.mutate()}
                  >
                    {bulkMutation.isPending ? "Applying…" : "Apply"}
                  </button>
                </>
              ) : (
                <span className="text-xs text-muted">select one workflow to transition</span>
              )}

              <button className="btn-secondary btn-sm" onClick={exportCsv}>Export CSV</button>
              <button className="btn-ghost btn-sm" onClick={() => setSelected(new Set())}>Clear</button>
            </div>
          )}
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
                <th style={{ width: 32 }}>
                  <input type="checkbox" checked={allFilteredSelected} onChange={toggleAll} />
                </th>
                <th>Reference</th>
                <th>Workflow</th>
                <th>Current State</th>
                <th>SLA</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((inst) => {
                const completed = Boolean(inst.completed_at);
                const sla = inst.sla;
                const rowStyle = sla?.status === "breached"
                  ? { background: "rgba(239,68,68,0.04)" }
                  : sla?.status === "warning"
                  ? { background: "rgba(245,158,11,0.04)" }
                  : undefined;
                return (
                  <tr key={inst.id} style={rowStyle}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.has(inst.id)}
                        onChange={() => toggleRow(inst.id)}
                      />
                    </td>
                    <td>
                      <Link to={`/instances/${inst.id}`} style={{ fontFamily: "monospace", fontSize: "0.875rem" }}>
                        {inst.reference_number}
                      </Link>
                      {inst.parent_reference && (
                        <div className="text-xs text-muted" style={{ fontFamily: "monospace" }}>
                          ↳ in {inst.parent_reference}
                        </div>
                      )}
                    </td>
                    <td className="text-sm">{inst.workflow_definition_name}</td>
                    <td>
                      <span className={`badge ${completed ? "badge-terminal" : "badge-active"}`}>
                        {inst.current_state_name}
                      </span>
                    </td>
                    <td>
                      {!completed && sla ? (
                        <SlaBadge sla={sla} />
                      ) : (
                        <span className="text-muted text-xs">—</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${completed ? "badge-inactive" : "badge-active"}`}>
                        {completed ? "Completed" : "In Progress"}
                      </span>
                    </td>
                    <td className="text-muted text-sm">
                      {formatDate(inst.created_at)}
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
