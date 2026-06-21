import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import { Workflow } from "../types/api";

export default function WorkflowsPage() {
  const { data = [], isLoading } = useQuery<Workflow[]>({
    queryKey: ["workflows"],
    queryFn: async () => (await apiClient.get("/workflows/")).data.results ?? [],
  });

  const active = data.filter((w) => w.is_active).length;

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>Workflows</h2>
          <p>{data.length} definitions · {active} active</p>
        </div>
        <Link to="/workflows/new">
          <button className="btn-primary">+ Create Workflow</button>
        </Link>
      </div>

      {isLoading ? (
        <div className="grid grid-2">
          {[1,2,3].map(i => <div key={i} className="skeleton" style={{ height: 120, borderRadius: 14 }} />)}
        </div>
      ) : data.length === 0 ? (
        <div className="card empty-state">
          <p>No workflows yet.</p>
          <Link to="/workflows/new" style={{ color: "var(--accent-light)", marginTop: 8 }}>
            Create your first workflow →
          </Link>
        </div>
      ) : (
        <div className="grid grid-2">
          {data.map((wf) => (
            <Link key={wf.id} to={`/workflows/${wf.id}`} style={{ textDecoration: "none" }}>
              <div
                className="card"
                style={{ cursor: "pointer", transition: "border-color 0.15s" }}
                onMouseOver={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--accent)")}
                onMouseOut={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--border)")}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="badge badge-role-workflow_designer" style={{ fontFamily: "monospace" }}>
                    {wf.reference_prefix}
                  </span>
                  <span className={`badge ${wf.is_active ? "badge-active" : "badge-inactive"}`}>
                    {wf.is_active ? "Active" : "Inactive"}
                  </span>
                  <span className="badge badge-inactive">v{wf.version}</span>
                </div>
                <div style={{ fontWeight: 600, fontSize: "1rem", marginBottom: 4 }}>{wf.name}</div>
                <div className="text-sm text-muted">{wf.description || "No description"}</div>
                <div className="divider" />
                <div className="flex gap-3 text-xs text-muted">
                  <span>{wf.states?.length ?? 0} states</span>
                  <span>{wf.transitions?.length ?? 0} transitions</span>
                  <span>{wf.rules?.length ?? 0} rules</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
