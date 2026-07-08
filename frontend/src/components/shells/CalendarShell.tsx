import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { WorkflowInstance } from "../../types/api";
import { instanceTitle, ShellProps, stateColour } from "./types";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function instanceDate(inst: WorkflowInstance, dateField: string): Date | null {
  const raw = dateField === "created_at"
    ? inst.created_at
    : (inst.metadata_json ?? {})[dateField];
  if (!raw) return null;
  const d = new Date(String(raw));
  return isNaN(d.getTime()) ? null : d;
}

function dayKey(d: Date) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

export default function CalendarShell({ workflow, instances }: ShellProps) {
  const [cursor, setCursor] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  const dateField = workflow.ui_schema?.date_field || "created_at";

  const byDay = useMemo(() => {
    const map: Record<string, WorkflowInstance[]> = {};
    for (const inst of instances) {
      const d = instanceDate(inst, dateField);
      if (d) (map[dayKey(d)] ??= []).push(inst);
    }
    return map;
  }, [instances, dateField]);

  // Build the month grid: weeks starting Monday
  const weeks = useMemo(() => {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const start = new Date(first);
    start.setDate(first.getDate() - ((first.getDay() + 6) % 7)); // back to Monday
    const cells: Date[] = [];
    const d = new Date(start);
    while (cells.length < 42) {
      cells.push(new Date(d));
      d.setDate(d.getDate() + 1);
    }
    const out: Date[][] = [];
    for (let i = 0; i < 42; i += 7) out.push(cells.slice(i, i + 7));
    // Drop trailing weeks fully outside the month
    return out.filter(week => week.some(day => day.getMonth() === cursor.getMonth()));
  }, [cursor]);

  const monthLabel = cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const today = dayKey(new Date());

  return (
    <div className="card" style={{ padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <button className="btn-secondary btn-sm" onClick={() => setCursor(c => new Date(c.getFullYear(), c.getMonth() - 1, 1))}>←</button>
        <div style={{ fontWeight: 700 }}>{monthLabel}
          <span className="text-xs text-muted" style={{ marginLeft: 8, fontWeight: 400 }}>
            by <span style={{ fontFamily: "monospace" }}>{dateField}</span>
          </span>
        </div>
        <button className="btn-secondary btn-sm" onClick={() => setCursor(c => new Date(c.getFullYear(), c.getMonth() + 1, 1))}>→</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
        {DAY_LABELS.map(l => (
          <div key={l} className="text-xs text-muted" style={{ textAlign: "center", fontWeight: 700, padding: "4px 0", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            {l}
          </div>
        ))}
        {weeks.flat().map((day, i) => {
          const inMonth = day.getMonth() === cursor.getMonth();
          const key = dayKey(day);
          const items = byDay[key] ?? [];
          return (
            <div
              key={i}
              style={{
                minHeight: 92, borderRadius: 8, padding: 6,
                background: inMonth ? "var(--bg-elevated)" : "transparent",
                border: `1px solid ${key === today ? "var(--accent)" : "var(--border-light)"}`,
                opacity: inMonth ? 1 : 0.35,
              }}
            >
              <div className="text-xs text-muted" style={{ marginBottom: 4, fontWeight: key === today ? 700 : 400 }}>
                {day.getDate()}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                {items.slice(0, 3).map(inst => {
                  const colour = stateColour(workflow, inst.current_state_name) ?? "var(--accent)";
                  const title = instanceTitle(workflow, inst);
                  return (
                    <Link
                      key={inst.id}
                      to={`/instances/${inst.id}`}
                      title={`${inst.reference_number} · ${inst.current_state_name}`}
                      style={{
                        display: "block", padding: "2px 6px", borderRadius: 5,
                        background: `${colour}1e`, borderLeft: `3px solid ${colour}`,
                        fontSize: "0.7rem", fontWeight: 600, color: "var(--text-primary)",
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                        textDecoration: "none",
                      }}
                    >
                      {title ?? inst.reference_number}
                    </Link>
                  );
                })}
                {items.length > 3 && (
                  <div className="text-xs text-muted">+{items.length - 3} more</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
