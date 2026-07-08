import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import { AuditEntry } from "../types/api";
import { formatDateTime } from "../hooks/useWorkspace";

export default function AuditPage() {
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery<{ results: AuditEntry[] }>({
    queryKey: ["audit"],
    queryFn: async () => (await apiClient.get("/audit/")).data,
  });

  const entries: AuditEntry[] = data?.results ?? [];
  const filtered = search
    ? entries.filter(
        (e) =>
          e.action_type.includes(search.toLowerCase()) ||
          e.actor_email?.toLowerCase().includes(search.toLowerCase()) ||
          e.from_state?.toLowerCase().includes(search.toLowerCase()) ||
          e.to_state?.toLowerCase().includes(search.toLowerCase())
      )
    : entries;

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>Audit Log</h2>
          <p>Immutable record of all state transitions and system events</p>
        </div>
        <span className="badge badge-inactive">{entries.length} entries</span>
      </div>

      <div className="card">
        <div style={{ marginBottom: 14 }}>
          <input
            placeholder="Search by event, actor or state…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ maxWidth: 320 }}
          />
        </div>

        {isLoading ? (
          <div>{[1,2,3,4,5].map(i => <div key={i} className="skeleton" style={{ height: 40, marginBottom: 8, borderRadius: 6 }} />)}</div>
        ) : filtered.length === 0 ? (
          <div className="empty-state"><p>{search ? "No entries match your search." : "No audit entries yet."}</p></div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Event</th>
                <th>Instance</th>
                <th>From</th>
                <th>To</th>
                <th>Actor</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry: any) => (
                <tr key={entry.id}>
                  <td>
                    <span className={`badge ${auditBadge(entry.action_type)}`}>
                      {entry.action_type.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td>
                    {entry.workflow_instance ? (
                      <Link
                        to={`/instances/${entry.workflow_instance}`}
                        className="font-mono"
                        style={{ fontSize: "0.8rem", color: "var(--accent-light)" }}
                      >
                        {entry.workflow_instance_reference ?? entry.workflow_instance.slice(0, 8)}
                      </Link>
                    ) : "—"}
                  </td>
                  <td className="text-muted text-sm">{entry.from_state ?? "—"}</td>
                  <td className="text-sm">{entry.to_state ?? "—"}</td>
                  <td className="text-sm">{entry.actor_email ?? entry.actor ?? "—"}</td>
                  <td className="text-muted text-sm">
                    {formatDateTime(entry.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function auditBadge(action: string) {
  if (action.includes("transition")) return "badge-active";
  if (action.includes("created"))    return "badge-initial";
  if (action.includes("rule"))       return "badge-warning";
  if (action.includes("blocked"))    return "badge-danger";
  return "badge-inactive";
}
