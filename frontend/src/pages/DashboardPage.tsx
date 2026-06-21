import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import { TaskItem, WorkflowInstance } from "../types/api";

export default function DashboardPage() {
  const { data: tasks = [], isLoading: tasksLoading } = useQuery<TaskItem[]>({
    queryKey: ["tasks"],
    queryFn: async () => {
      const res = await apiClient.get("/tasks/");
      return res.data.results ?? [];
    },
  });

  const { data: instances = [] } = useQuery<WorkflowInstance[]>({
    queryKey: ["instances"],
    queryFn: async () => {
      const res = await apiClient.get("/instances/");
      return res.data.results ?? [];
    },
  });

  const { data: workflows = [] } = useQuery({
    queryKey: ["workflows"],
    queryFn: async () => {
      const res = await apiClient.get("/workflows/");
      return res.data.results ?? [];
    },
  });

  const openTasks = tasks.filter((t) => t.status !== "completed").length;
  const activeInstances = instances.filter((i) => !(i as any).completed_at).length;
  const completedInstances = instances.filter((i) => (i as any).completed_at).length;
  const activeWorkflows = workflows.filter((w: any) => w.is_active).length;

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>Dashboard</h2>
          <p>Welcome back — here's what needs your attention</p>
        </div>
      </div>

      {/* Stats row */}
      <div className="stats-grid">
        <div className="stat-card accent">
          <div className="label">Open Tasks</div>
          <div className="value">{openTasks}</div>
          <div className="sub">Awaiting action</div>
        </div>
        <div className="stat-card warning">
          <div className="label">Active Instances</div>
          <div className="value">{activeInstances}</div>
          <div className="sub">In progress</div>
        </div>
        <div className="stat-card success">
          <div className="label">Completed</div>
          <div className="value">{completedInstances}</div>
          <div className="sub">Instances closed</div>
        </div>
        <div className="stat-card info">
          <div className="label">Workflows</div>
          <div className="value">{activeWorkflows}</div>
          <div className="sub">Active definitions</div>
        </div>
      </div>

      <div className="grid grid-2">
        {/* Task inbox */}
        <div className="card">
          <div className="card-header">
            <h3>Task Inbox</h3>
            {openTasks > 0 && (
              <span className="badge badge-pending">{openTasks} open</span>
            )}
          </div>

          {tasksLoading ? (
            <div>{[1,2,3].map(i => <div key={i} className="skeleton" style={{ height: 36, marginBottom: 8, borderRadius: 6 }} />)}</div>
          ) : tasks.length === 0 ? (
            <div className="empty-state" style={{ padding: "20px 0" }}>
              <p>No tasks assigned to you.</p>
            </div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Reference</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {tasks.slice(0, 10).map((task) => (
                  <tr key={task.id}>
                    <td style={{ fontWeight: 500 }}>{task.title}</td>
                    <td>
                      <span className="font-mono text-sm text-muted">{task.workflow_reference}</span>
                    </td>
                    <td>
                      <span className={`badge ${task.status === "completed" ? "badge-terminal" : "badge-pending"}`}>
                        {task.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Recent instances */}
        <div className="card">
          <div className="card-header">
            <h3>Recent Instances</h3>
            <Link to="/instances" style={{ fontSize: "0.8rem", color: "var(--accent-light)" }}>View all →</Link>
          </div>

          {instances.length === 0 ? (
            <div className="empty-state" style={{ padding: "20px 0" }}>
              <p>No instances yet. <Link to="/instances" style={{ color: "var(--accent-light)" }}>Create one →</Link></p>
            </div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>State</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {instances.slice(0, 8).map((inst) => (
                  <tr key={inst.id}>
                    <td>
                      <Link to={`/instances/${inst.id}`} className="font-mono" style={{ fontSize: "0.85rem" }}>
                        {inst.reference_number}
                      </Link>
                    </td>
                    <td className="text-sm text-muted">{inst.current_state_name}</td>
                    <td>
                      <span className={`badge ${(inst as any).completed_at ? "badge-terminal" : "badge-active"}`}>
                        {(inst as any).completed_at ? "Done" : "Active"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Workflows summary */}
      {workflows.length > 0 && (
        <div className="card mt-4">
          <div className="card-header">
            <h3>Workflow Definitions</h3>
            <Link to="/workflows" style={{ fontSize: "0.8rem", color: "var(--accent-light)" }}>Manage →</Link>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {workflows.map((wf: any) => (
              <Link
                key={wf.id}
                to={`/workflows/${wf.id}`}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                  padding: "14px 18px",
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border)",
                  borderRadius: 10,
                  minWidth: 180,
                  transition: "border-color 0.15s",
                }}
                onMouseOver={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
                onMouseOut={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
              >
                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{wf.name}</div>
                <div style={{ display: "flex", gap: 6 }}>
                  <span className="badge badge-role-workflow_designer" style={{ fontSize: "0.7rem" }}>{wf.reference_prefix}</span>
                  <span className={`badge ${wf.is_active ? "badge-active" : "badge-inactive"}`} style={{ fontSize: "0.7rem" }}>
                    {wf.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
