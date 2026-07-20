/**
 * Shared React Flow pieces for the visual builder and the YAML editor
 * preview: the state node renderer, edge factory, and dagre auto-layout.
 */
import dagre from "@dagrejs/dagre";
import { Handle, Position, type Edge, type Node, type NodeProps } from "@xyflow/react";

export interface StateNodeData {
  label: string;
  isInitial: boolean;
  isTerminal: boolean;
  slaHours: number;
  requiresTask: boolean;
  defaultRole: string;
  serverId?: string; // set when hydrated from an existing workflow
}

export function StateNode({ data, selected }: NodeProps) {
  const d = data as StateNodeData;
  const borderColor = d.isInitial ? "#6366f1" : d.isTerminal ? "#3fb950" : "#30363d";
  const bg = selected ? "rgba(99,102,241,0.12)" : d.isInitial ? "rgba(99,102,241,0.08)" : d.isTerminal ? "rgba(63,185,80,0.06)" : "#1a1d27";

  return (
    <div style={{
      minWidth: 140,
      padding: "10px 14px",
      borderRadius: 10,
      border: `2px solid ${selected ? "#6366f1" : borderColor}`,
      background: bg,
      boxShadow: selected ? "0 0 0 3px rgba(99,102,241,0.25)" : undefined,
      cursor: "default",
      transition: "border-color 0.15s, background 0.15s",
    }}>
      <Handle type="target" position={Position.Left} style={{ background: "#6366f1", border: "2px solid #30363d", width: 10, height: 10 }} />

      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        {d.isInitial && <span style={{ fontSize: 8, fontWeight: 700, background: "rgba(99,102,241,0.3)", color: "#818cf8", padding: "2px 5px", borderRadius: 4, textTransform: "uppercase", letterSpacing: "0.06em" }}>Start</span>}
        {d.isTerminal && <span style={{ fontSize: 8, fontWeight: 700, background: "rgba(63,185,80,0.2)", color: "#3fb950", padding: "2px 5px", borderRadius: 4, textTransform: "uppercase", letterSpacing: "0.06em" }}>End</span>}
      </div>

      <div style={{ fontWeight: 600, fontSize: 13, color: "#e6edf3", lineHeight: 1.2 }}>
        {d.label || "Unnamed State"}
      </div>
      {d.slaHours > 0 && (
        <div style={{ fontSize: 10, color: "#8b949e", marginTop: 4 }}>SLA: {d.slaHours}h</div>
      )}

      <Handle type="source" position={Position.Right} style={{ background: "#6366f1", border: "2px solid #30363d", width: 10, height: 10 }} />
    </div>
  );
}

export const nodeTypes = { stateNode: StateNode };

export function makeEdge(
  id: string, source: string, target: string,
  name: string, requiresApproval: boolean, serverId?: string,
): Edge {
  return {
    id, source, target,
    label: name,
    labelStyle: { fontSize: 11, fill: "#8b949e", fontWeight: 500 },
    labelBgStyle: { fill: "#161b22" },
    labelBgPadding: [4, 4] as [number, number],
    style: requiresApproval
      ? { stroke: "#d29922", strokeWidth: 1.5, strokeDasharray: "6,3" }
      : { stroke: "#6366f1", strokeWidth: 1.5 },
    markerEnd: { type: "arrowclosed" as any, color: requiresApproval ? "#d29922" : "#6366f1" },
    data: { name, requiresApproval, serverId },
  };
}

export const NODE_W = 170;
export const NODE_H = 64;

/** Left-to-right rank layout via dagre. */
export function layoutGraph(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 90, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    return { ...n, position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 } };
  });
}

/** Build preview nodes/edges from a parsed DSL bundle (dry-run response). */
export function graphFromBundle(bundle: any): { nodes: Node[]; edges: Edge[] } {
  const states = bundle?.states ?? [];
  const transitions = bundle?.transitions ?? [];
  const nodes: Node[] = states.map((s: any) => ({
    id: s.name,
    type: "stateNode",
    position: { x: 0, y: 0 },
    data: {
      label: s.name,
      isInitial: Boolean(s.is_initial),
      isTerminal: Boolean(s.is_terminal),
      slaHours: Number(s.sla_config?.sla_hours ?? 0),
      requiresTask: Boolean(s.task_config?.requires_task ?? true),
      defaultRole: s.task_config?.default_role ?? "participant",
    } as StateNodeData,
  }));
  const edges: Edge[] = transitions.map((t: any, i: number) =>
    makeEdge(`t${i}`, t.from_state, t.to_state, t.name, Boolean(t.requires_approval))
  );
  return { nodes: layoutGraph(nodes, edges), edges };
}
