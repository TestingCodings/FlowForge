import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { State, Transition, WorkflowInstance } from "../../types/api";
import { groupLabel, groupValue, instanceTitle, ShellProps, stateColour, stateIcon } from "./types";

const NO_LANE = "__no_lane__";

export default function KanbanShell({ workflow, instances, fireTransition }: ShellProps) {
  const [dragging, setDragging] = useState<WorkflowInstance | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  const states: State[] = useMemo(
    () => [...(workflow.states ?? [])].sort((a, b) => a.position_order - b.position_order),
    [workflow],
  );
  const transitions: Transition[] = workflow.transitions ?? [];
  const cardFields: string[] = workflow.ui_schema?.card_fields ?? [];
  const swimlaneField = workflow.ui_schema?.swimlanes;

  /** Instances split into swimlanes; a single unnamed lane when unconfigured. */
  const lanes = useMemo(() => {
    if (!swimlaneField) return [{ key: NO_LANE, items: instances }];
    const map = new Map<string, WorkflowInstance[]>();
    for (const inst of instances) {
      const key = groupValue(inst, swimlaneField) || NO_LANE;
      const list = map.get(key) ?? [];
      list.push(inst);
      map.set(key, list);
    }
    return [...map.entries()]
      .sort(([a], [b]) => (a === NO_LANE ? 1 : b === NO_LANE ? -1 : a.localeCompare(b)))
      .map(([key, items]) => ({ key, items }));
  }, [instances, swimlaneField]);

  const findTransition = (fromStateId: string, toStateId: string) =>
    transitions.find(t => t.from_state === fromStateId && t.to_state === toStateId);

  // Drop targets are scoped per lane so the same state in two lanes doesn't
  // both highlight while dragging.
  const onDrop = (toStateId: string) => {
    setDropTarget(null);
    if (!dragging) return;
    const inst = dragging;
    setDragging(null);
    if (inst.current_state === toStateId) return;
    const tr = findTransition(inst.current_state, toStateId);
    if (tr) fireTransition(inst, tr);
  };

  const renderBoard = (laneKey: string, laneItems: WorkflowInstance[]) => {
    const byState: Record<string, WorkflowInstance[]> = {};
    for (const s of states) byState[s.id] = [];
    for (const i of laneItems) (byState[i.current_state] ??= []).push(i);

    return (
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start", overflowX: "auto", paddingBottom: 12 }}>
        {states.map(state => {
          const cards = byState[state.id] ?? [];
          const targetKey = `${laneKey}:${state.id}`;
          const isTarget = dropTarget === targetKey;
          const canReceive = dragging && dragging.current_state !== state.id
            && Boolean(findTransition(dragging.current_state, state.id));
          const colour = stateColour(workflow, state.name);
          const icon = stateIcon(workflow, state.name);
          return (
            <div
              key={state.id}
              data-col={state.name}
              onDragOver={e => { e.preventDefault(); setDropTarget(targetKey); }}
              onDragLeave={() => setDropTarget(cur => (cur === targetKey ? null : cur))}
              onDrop={() => onDrop(state.id)}
              style={{
                minWidth: 250, maxWidth: 290, flex: "1 0 250px",
                background: "var(--bg-surface)",
                border: `1px solid ${isTarget ? (canReceive ? "var(--success)" : "var(--danger)") : "var(--border)"}`,
                borderTop: colour ? `3px solid ${colour}` : undefined,
                borderRadius: 10, padding: 10,
                transition: "border-color 120ms",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "2px 6px 10px" }}>
                <span className="text-sm" style={{ fontWeight: 700, color: colour }}>
                  {icon && <span style={{ marginRight: 5 }}>{icon}</span>}
                  {state.display_name || state.name}
                  {state.is_terminal && <span className="text-xs text-muted"> · end</span>}
                </span>
                <span className="badge badge-inactive">{cards.length}</span>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8, minHeight: 60 }}>
                {cards.map(inst => {
                  const title = instanceTitle(workflow, inst);
                  return (
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
                      {title && (
                        <div className="text-sm" style={{ fontWeight: 600, marginBottom: 2 }}>{title}</div>
                      )}
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
                  );
                })}
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
    );
  };

  // Unconfigured: the board renders exactly as before, no lane chrome.
  if (!swimlaneField) return renderBoard(NO_LANE, instances);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {lanes.map(({ key, items }) => (
        <div key={key}>
          <div style={{
            display: "flex", alignItems: "center", gap: 8, marginBottom: 8,
            paddingBottom: 6, borderBottom: "1px solid var(--border)",
          }}>
            <span style={{
              fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase",
              letterSpacing: "0.06em", color: "var(--text-secondary)",
            }}>
              {groupLabel(swimlaneField)}
            </span>
            <span style={{ fontSize: "0.9rem", fontWeight: 600 }}>
              {key === NO_LANE ? "—" : key}
            </span>
            <span className="badge badge-inactive">{items.length}</span>
          </div>
          {renderBoard(key, items)}
        </div>
      ))}
    </div>
  );
}
