import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { WorkflowInstance } from "../../types/api";
import { formatDate } from "../../hooks/useWorkspace";
import { instanceTitle, ShellProps, stateColour, stateIcon } from "./types";

/**
 * List shell (VISION Layer 2) — the platform's default, now a first-class
 * registry entry rather than a redirect.
 *
 * Where TableShell is a spreadsheet of configurable columns, this is a
 * Linear/GitHub-Issues-style vertical list: one row per instance with an
 * optional title, a state chip (honouring state_display colour + icon), and
 * an SLA flag. It reads the same title_field as the other shells, and adds a
 * quick client-side text filter since it's the fallback for large workflows.
 */
export default function ListShell({ workflow, instances }: ShellProps) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const hasTitle = Boolean(workflow.ui_schema?.title_field);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return instances;
    return instances.filter((i) => {
      const title = instanceTitle(workflow, i) ?? "";
      return (
        i.reference_number.toLowerCase().includes(term) ||
        i.current_state_name.toLowerCase().includes(term) ||
        title.toLowerCase().includes(term)
      );
    });
  }, [instances, q, workflow]);

  if (!instances.length) {
    return (
      <div className="card" style={{ textAlign: "center", padding: 40, color: "var(--text-secondary)" }}>
        No instances yet.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <input
        placeholder="Filter by reference, title, or state…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        style={{ maxWidth: 340, padding: "7px 10px", fontSize: "0.85rem" }}
      />

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {filtered.map((inst, i) => {
          const colour = stateColour(workflow, inst.current_state_name);
          const icon = stateIcon(workflow, inst.current_state_name);
          const title = instanceTitle(workflow, inst);
          const sla = inst.sla?.status;
          return (
            <div
              key={inst.id}
              onClick={() => navigate(`/instances/${inst.id}`)}
              style={{
                display: "flex", alignItems: "center", gap: 12, padding: "11px 14px",
                cursor: "pointer",
                borderBottom: i < filtered.length - 1 ? "1px solid var(--border-light)" : "none",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              <span style={{ fontFamily: "monospace", fontSize: "0.8rem", color: "var(--accent-light)", flexShrink: 0, width: 130 }}>
                {inst.reference_number}
              </span>

              {hasTitle && (
                <span style={{ fontWeight: 600, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {title ?? "—"}
                </span>
              )}
              {!hasTitle && <span style={{ flex: 1 }} />}

              {sla && sla !== "ok" && !inst.completed_at && (
                <span className="text-xs" style={{ fontWeight: 700, flexShrink: 0, color: sla === "breached" ? "var(--danger)" : "var(--warning)" }}>
                  ⏱ {sla === "breached" ? "OVERDUE" : "DUE SOON"}
                </span>
              )}

              <span className="text-muted text-xs" style={{ flexShrink: 0, width: 90, textAlign: "right" }}>
                {formatDate(inst.created_at)}
              </span>

              <span
                className={`badge ${inst.completed_at ? "badge-terminal" : "badge-active"}`}
                style={{
                  flexShrink: 0, minWidth: 96, textAlign: "center",
                  ...(colour ? { background: `${colour}22`, color: colour, border: `1px solid ${colour}55` } : {}),
                }}
              >
                {icon && <span style={{ marginRight: 4 }}>{icon}</span>}
                {inst.current_state_name}
              </span>
            </div>
          );
        })}
        {filtered.length === 0 && (
          <div style={{ padding: 24, textAlign: "center", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
            No instances match “{q}”.
          </div>
        )}
      </div>
    </div>
  );
}
