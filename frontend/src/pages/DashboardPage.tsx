import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { apiClient } from "../api/client";
import { TaskItem, WorkflowInstance } from "../types/api";

/* ─── Recharts dark theme tokens ─── */
const C_GRID   = "#21262d";
const C_TEXT   = "#8b949e";
const C_ACCENT = "#6366f1";
const C_GREEN  = "#3fb950";
const C_WARN   = "#d29922";

/* ─── Data helpers ─── */
function last14Days(): string[] {
  const days: string[] = [];
  for (let i = 13; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    days.push(d.toISOString().slice(0, 10));
  }
  return days;
}

function shortDate(iso: string) {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

function useChartData(instances: WorkflowInstance[]) {
  return useMemo(() => {
    const days = last14Days();

    // Activity over time
    const createdByDay = Object.fromEntries(days.map(d => [d, 0]));
    const completedByDay = Object.fromEntries(days.map(d => [d, 0]));
    for (const inst of instances) {
      const c = inst.created_at?.slice(0, 10);
      if (c && createdByDay[c] !== undefined) createdByDay[c]++;
      const done = inst.completed_at?.slice(0, 10);
      if (done && completedByDay[done] !== undefined) completedByDay[done]++;
    }
    const activity = days.map(d => ({
      date: shortDate(d),
      Created: createdByDay[d],
      Completed: completedByDay[d],
    }));

    // Instances by current state (top 8)
    const stateCounts: Record<string, number> = {};
    for (const inst of instances) {
      const s = inst.current_state_name || "Unknown";
      stateCounts[s] = (stateCounts[s] ?? 0) + 1;
    }
    const byState = Object.entries(stateCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([state, count]) => ({ state, count }));

    // Instances by workflow
    const wfCounts: Record<string, { active: number; completed: number }> = {};
    for (const inst of instances) {
      const name = inst.workflow_definition_name ?? "Unknown";
      if (!wfCounts[name]) wfCounts[name] = { active: 0, completed: 0 };
      if (inst.completed_at) wfCounts[name].completed++;
      else wfCounts[name].active++;
    }
    const byWorkflow = Object.entries(wfCounts).map(([name, v]) => ({
      name: name.length > 20 ? name.slice(0, 18) + "…" : name,
      ...v,
      total: v.active + v.completed,
    }));

    return { activity, byState, byWorkflow };
  }, [instances]);
}

/* ─── Custom tooltip ─── */
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#161b22", border: "1px solid #30363d", borderRadius: 8,
      padding: "8px 12px", fontSize: "0.78rem",
    }}>
      <div style={{ color: C_TEXT, marginBottom: 4 }}>{label}</div>
      {payload.map((p: any) => (
        <div key={p.name} style={{ color: p.color, fontWeight: 600 }}>
          {p.name}: {p.value}
        </div>
      ))}
    </div>
  );
}

/* ─── State bar colours ─── */
const STATE_COLOURS = [C_ACCENT, "#818cf8", "#a5b4fc", C_GREEN, "#6fda8a", C_WARN, "#fbbf24", "#f87171"];

/* ─── Page ─── */
export default function DashboardPage() {
  const { data: tasks = [], isLoading: tasksLoading } = useQuery<TaskItem[]>({
    queryKey: ["tasks"],
    queryFn: async () => (await apiClient.get("/tasks/")).data.results ?? [],
  });

  const { data: instances = [] } = useQuery<WorkflowInstance[]>({
    queryKey: ["instances"],
    queryFn: async () => (await apiClient.get("/instances/?page_size=200")).data.results ?? [],
  });

  const { data: workflows = [] } = useQuery({
    queryKey: ["workflows"],
    queryFn: async () => (await apiClient.get("/workflows/")).data.results ?? [],
  });

  const openTasks          = tasks.filter(t => t.status !== "completed").length;
  const activeInstances    = instances.filter(i => !i.completed_at).length;
  const completedInstances = instances.filter(i =>  i.completed_at).length;
  const total              = instances.length;
  const completionRate     = total > 0 ? Math.round((completedInstances / total) * 100) : 0;
  const activeWorkflows    = workflows.filter((w: any) => w.is_active).length;

  const { activity, byState, byWorkflow } = useChartData(instances);

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>Dashboard</h2>
          <p>Platform overview — instances, tasks, and workflow performance</p>
        </div>
      </div>

      {/* ── Stat cards ── */}
      <div className="stats-grid" style={{ marginBottom: 20 }}>
        <StatCard colour="accent" label="Open Tasks"       value={openTasks}          sub="Awaiting action" />
        <StatCard colour="warning" label="Active Instances" value={activeInstances}    sub="In progress" />
        <StatCard colour="success" label="Completed"        value={completedInstances} sub={`${completionRate}% completion rate`} />
        <StatCard colour="info"    label="Workflows"        value={activeWorkflows}    sub="Active definitions" />
      </div>

      {/* ── Charts row ── */}
      <div className="grid grid-2 mb-4">
        {/* Activity over time */}
        <div className="card">
          <div className="card-header">
            <h3>Activity — last 14 days</h3>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={activity} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="gradCreated" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={C_ACCENT} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={C_ACCENT} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradCompleted" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={C_GREEN} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={C_GREEN} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={C_GRID} strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fill: C_TEXT, fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: C_TEXT, fontSize: 10 }} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="Created"   stroke={C_ACCENT} fill="url(#gradCreated)"   strokeWidth={2} dot={false} />
              <Area type="monotone" dataKey="Completed" stroke={C_GREEN}  fill="url(#gradCompleted)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-2" style={{ paddingLeft: 4 }}>
            <Legend colour={C_ACCENT} label="Created" />
            <Legend colour={C_GREEN}  label="Completed" />
          </div>
        </div>

        {/* Instances by state */}
        <div className="card">
          <div className="card-header">
            <h3>Instances by current state</h3>
            <span className="badge badge-inactive">{total} total</span>
          </div>
          {byState.length === 0 ? (
            <p className="text-muted text-sm" style={{ paddingTop: 16 }}>No instances yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={byState} layout="vertical" margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C_GRID} strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tick={{ fill: C_TEXT, fontSize: 10 }} tickLine={false} axisLine={false} allowDecimals={false} />
                <YAxis type="category" dataKey="state" tick={{ fill: C_TEXT, fontSize: 10 }} tickLine={false} axisLine={false} width={100} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={22}>
                  {byState.map((_, i) => (
                    <Cell key={i} fill={STATE_COLOURS[i % STATE_COLOURS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* ── Workflow breakdown ── */}
      {byWorkflow.length > 0 && (
        <div className="card mb-4">
          <div className="card-header">
            <h3>Active vs Completed by workflow</h3>
          </div>
          <ResponsiveContainer width="100%" height={byWorkflow.length * 44 + 20}>
            <BarChart data={byWorkflow} layout="vertical" margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={C_GRID} strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tick={{ fill: C_TEXT, fontSize: 10 }} tickLine={false} axisLine={false} allowDecimals={false} />
              <YAxis type="category" dataKey="name" tick={{ fill: C_TEXT, fontSize: 10 }} tickLine={false} axisLine={false} width={140} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="active"    name="Active"    fill={C_ACCENT} radius={[0, 0, 0, 0]} stackId="a" maxBarSize={24} />
              <Bar dataKey="completed" name="Completed" fill={C_GREEN}  radius={[0, 4, 4, 0]} stackId="a" maxBarSize={24} />
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-2" style={{ paddingLeft: 4 }}>
            <Legend colour={C_ACCENT} label="Active" />
            <Legend colour={C_GREEN}  label="Completed" />
          </div>
        </div>
      )}

      <div className="grid grid-2">
        {/* Task inbox */}
        <div className="card">
          <div className="card-header">
            <h3>Task Inbox</h3>
            {openTasks > 0 && <span className="badge badge-pending">{openTasks} open</span>}
          </div>
          {tasksLoading ? (
            <div>{[1,2,3].map(i => <div key={i} className="skeleton" style={{ height: 36, marginBottom: 8, borderRadius: 6 }} />)}</div>
          ) : tasks.length === 0 ? (
            <div className="empty-state" style={{ padding: "20px 0" }}><p>No tasks assigned.</p></div>
          ) : (
            <table className="table">
              <thead><tr><th>Task</th><th>Reference</th><th>Status</th></tr></thead>
              <tbody>
                {tasks.slice(0, 10).map(task => (
                  <tr key={task.id}>
                    <td style={{ fontWeight: 500 }}>{task.title}</td>
                    <td><span style={{ fontFamily: "monospace", fontSize: "0.82rem", color: "var(--text-secondary)" }}>{task.workflow_reference}</span></td>
                    <td><span className={`badge ${task.status === "completed" ? "badge-terminal" : "badge-pending"}`}>{task.status}</span></td>
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
              <thead><tr><th>Reference</th><th>Workflow</th><th>State</th><th>Status</th></tr></thead>
              <tbody>
                {instances.slice(0, 8).map(inst => (
                  <tr key={inst.id}>
                    <td>
                      <Link to={`/instances/${inst.id}`} style={{ fontFamily: "monospace", fontSize: "0.82rem", color: "var(--accent-light)" }}>
                        {inst.reference_number}
                      </Link>
                    </td>
                    <td className="text-xs text-muted">{inst.workflow_definition_name}</td>
                    <td className="text-sm">{inst.current_state_name}</td>
                    <td>
                      <span className={`badge ${inst.completed_at ? "badge-terminal" : "badge-active"}`}>
                        {inst.completed_at ? "Done" : "Active"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Small components ─── */
function StatCard({ colour, label, value, sub }: { colour: string; label: string; value: number; sub: string }) {
  return (
    <div className={`stat-card ${colour}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      <div className="sub">{sub}</div>
    </div>
  );
}

function Legend({ colour, label }: { colour: string; label: string }) {
  return (
    <div className="flex items-center gap-2" style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
      <div style={{ width: 10, height: 10, borderRadius: 2, background: colour, flexShrink: 0 }} />
      {label}
    </div>
  );
}
