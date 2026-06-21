import { useMemo } from "react";
import { State, Transition } from "../types/api";

interface Props {
  states: State[];
  transitions: Transition[];
  currentStateId: string;
  visitedStateNames?: string[];
  isTerminal?: boolean;
}

const NODE_W  = 140;
const NODE_H  = 46;
const COL_GAP = 80;   // horizontal gap between levels
const ROW_GAP = 18;   // vertical gap between nodes in the same level
const PAD     = 24;

/** BFS-based topological level assignment. Returns level (0-based) for each state id. */
function assignLevels(states: State[], transitions: Transition[]): Map<string, number> {
  const out = new Map<string, number>();

  // Build adjacency (from → [to])
  const adj = new Map<string, string[]>();
  for (const s of states) adj.set(s.id, []);
  for (const t of transitions) {
    const list = adj.get(t.from_state);
    if (list) list.push(t.to_state);
  }

  // Start from initial states (or state with lowest position_order)
  const initials = states.filter(s => s.is_initial);
  const roots = initials.length > 0 ? initials : [states.sort((a, b) => a.position_order - b.position_order)[0]];

  // Longest-path BFS: for each state, record the furthest distance from any root
  const queue: Array<{ id: string; level: number }> = roots.map(s => ({ id: s.id, level: 0 }));
  const visited = new Set<string>();

  while (queue.length) {
    const { id, level } = queue.shift()!;
    const existing = out.get(id) ?? -1;
    if (level <= existing) continue; // already assigned a further-out level
    out.set(id, level);
    if (visited.has(id)) continue;
    visited.add(id);
    for (const next of (adj.get(id) ?? [])) {
      queue.push({ id: next, level: level + 1 });
    }
  }

  // Any states not reached (disconnected): add after max level
  const maxLevel = Math.max(0, ...out.values());
  let extra = maxLevel + 1;
  for (const s of states) {
    if (!out.has(s.id)) out.set(s.id, extra++);
  }

  return out;
}

export default function StateGraph({
  states, transitions, currentStateId, visitedStateNames = [],
}: Props) {
  const { nodes, edges, svgW, svgH } = useMemo(() => {
    if (!states.length) return { nodes: [], edges: [], svgW: 0, svgH: 0 };

    const levelMap = assignLevels(states, transitions);

    // Group states by level, sort each group by position_order for determinism
    const byLevel = new Map<number, State[]>();
    for (const s of states) {
      const l = levelMap.get(s.id) ?? 0;
      const list = byLevel.get(l) ?? [];
      list.push(s);
      byLevel.set(l, list);
    }
    for (const [l, list] of byLevel) {
      byLevel.set(l, list.sort((a, b) => a.position_order - b.position_order));
    }

    // Compute x/y for every state
    const nodePos = new Map<string, { x: number; y: number }>();
    for (const [level, list] of byLevel) {
      const x = PAD + level * (NODE_W + COL_GAP);
      const totalH = list.length * NODE_H + (list.length - 1) * ROW_GAP;
      list.forEach((s, i) => {
        const y = PAD + i * (NODE_H + ROW_GAP);
        nodePos.set(s.id, { x, y });
        // Stagger groups vertically so they center — we'll do a second pass
        void totalH;
      });
    }

    // Center groups vertically relative to the tallest level
    const maxGroupH = Math.max(...[...byLevel.values()].map(list => list.length * NODE_H + (list.length - 1) * ROW_GAP));
    for (const [, list] of byLevel) {
      const groupH = list.length * NODE_H + (list.length - 1) * ROW_GAP;
      const offset = Math.floor((maxGroupH - groupH) / 2);
      list.forEach((s) => {
        const pos = nodePos.get(s.id)!;
        nodePos.set(s.id, { x: pos.x, y: PAD + offset + (list.indexOf(s)) * (NODE_H + ROW_GAP) });
      });
    }

    const nodeList = states.map(s => ({ state: s, ...nodePos.get(s.id)! }));

    const edgeList = transitions.map(t => ({
      id: t.id, name: t.name,
      from: nodePos.get(t.from_state),
      to:   nodePos.get(t.to_state),
      fromState: states.find(s => s.id === t.from_state),
      toState:   states.find(s => s.id === t.to_state),
    })).filter(e => e.from && e.to) as Array<{
      id: string; name: string;
      from: { x: number; y: number }; to: { x: number; y: number };
      fromState: State; toState: State;
    }>;

    const maxX = Math.max(...nodeList.map(n => n.x)) + NODE_W + PAD;
    const maxY = Math.max(...nodeList.map(n => n.y)) + NODE_H + PAD;

    return { nodes: nodeList, edges: edgeList, svgW: maxX, svgH: maxY };
  }, [states, transitions]);

  const currentState = states.find(s => s.id === currentStateId);

  function stateStatus(state: State) {
    if (state.id === currentStateId) return "active";
    // Only mark as completed if the audit trail explicitly recorded this state as visited.
    // Never use position_order as a proxy — branching flows have states at lower orders
    // that were never actually reached (e.g. "Approved" when the claim was "Rejected").
    if (visitedStateNames.includes(state.name) || visitedStateNames.includes(state.display_name)) return "completed";
    return "pending";
  }

  if (!states.length) return null;

  return (
    <div className="state-graph-wrap">
      <svg
        width={svgW}
        height={svgH}
        viewBox={`0 0 ${svgW} ${svgH}`}
        style={{ display: "block", minWidth: svgW }}
      >
        <defs>
          <marker id="arr-active"  markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0,8 3,0 6" fill="#6366f1" /></marker>
          <marker id="arr-done"    markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0,8 3,0 6" fill="#3fb950" /></marker>
          <marker id="arr-pending" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0,8 3,0 6" fill="#30363d" /></marker>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* ── Edges ── */}
        {edges.map(e => {
          const status = stateStatus(e.fromState);
          const stroke = status === "completed" ? "#3fb950" : status === "active" ? "#6366f1" : "#30363d";
          const markerId = status === "completed" ? "arr-done" : status === "active" ? "arr-active" : "arr-pending";
          const opacity = status === "pending" ? 0.35 : 1;

          // Start from right-center of source, end at left-center of target
          const x1 = e.from.x + NODE_W;
          const y1 = e.from.y + NODE_H / 2;
          const x2 = e.to.x;
          const y2 = e.to.y + NODE_H / 2;

          // Back-edge (right-to-left) or skip-level: use an arc that routes around
          const isBackEdge = e.to.x <= e.from.x;
          const dy = Math.abs(y2 - y1);
          const dx = Math.abs(x2 - x1);

          let d: string;
          if (isBackEdge) {
            // Loop back: arc below the nodes
            const midX = (x1 + x2) / 2;
            const arcY = Math.max(e.from.y, e.to.y) + NODE_H + 28;
            d = `M ${x1} ${y1} C ${x1 + 20} ${arcY}, ${x2 - 20} ${arcY}, ${x2} ${y2}`;
          } else if (dy > 4) {
            // Same or skipped level but different row: S-curve
            const cpX = x1 + dx * 0.4;
            d = `M ${x1} ${y1} C ${cpX} ${y1}, ${cpX} ${y2}, ${x2} ${y2}`;
          } else {
            // Straight horizontal
            d = `M ${x1} ${y1} L ${x2 - 8} ${y2}`;
          }

          // Label position: midpoint of the bezier approximation
          const lx = (x1 + x2) / 2;
          const ly = isBackEdge
            ? Math.max(e.from.y, e.to.y) + NODE_H + 42
            : (y1 + y2) / 2 - 6;

          return (
            <g key={e.id}>
              <path d={d} fill="none" stroke={stroke} strokeWidth={1.5}
                markerEnd={`url(#${markerId})`} opacity={opacity} />
              <text x={lx} y={ly} textAnchor="middle" fontSize="9"
                fill={stroke} opacity={opacity * 0.85}>
                {e.name}
              </text>
            </g>
          );
        })}

        {/* ── Nodes ── */}
        {nodes.map(({ x, y, state }) => {
          const status  = stateStatus(state);
          const isActive = status === "active";
          const isDone   = status === "completed";

          const fill   = isActive ? "rgba(99,102,241,0.18)" : isDone ? "rgba(63,185,80,0.12)" : "rgba(33,38,45,0.8)";
          const stroke = isActive ? "#6366f1" : isDone ? "#3fb950" : "#30363d";
          const textC  = isActive ? "#818cf8" : isDone ? "#6fda8a" : "#8b949e";
          const iconX  = x + 14;
          const textX  = isActive || isDone ? x + 28 : x + NODE_W / 2;
          const anchor = isActive || isDone ? "start" : "middle";

          return (
            <g key={state.id} filter={isActive ? "url(#glow)" : undefined}>
              <rect x={x} y={y} width={NODE_W} height={NODE_H} rx={8} ry={8}
                fill={fill} stroke={stroke} strokeWidth={isActive ? 1.5 : 1} />

              {isDone && (
                <text x={iconX} y={y + NODE_H / 2 + 4} fontSize="12" fill="#3fb950">✓</text>
              )}
              {isActive && (
                <circle cx={iconX} cy={y + NODE_H / 2} r={4} fill="#6366f1">
                  <animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite" />
                </circle>
              )}

              {/* State name — clip long names with ellipsis via SVG foreignObject is complex, truncate in JS */}
              <text x={textX} y={y + NODE_H / 2 - 4} textAnchor={anchor}
                fontSize="11" fontWeight={isActive ? "700" : "500"} fill={textC}>
                {truncate(state.display_name || state.name, 14)}
              </text>
              <text x={textX} y={y + NODE_H / 2 + 10} textAnchor={anchor}
                fontSize="8" fill={textC} opacity="0.55">
                {state.is_initial ? "start" : state.is_terminal ? "end" : ""}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function truncate(s: string, max: number) {
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}
