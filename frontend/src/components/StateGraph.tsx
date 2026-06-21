import { useMemo } from "react";
import { State, Transition } from "../types/api";

interface Props {
  states: State[];
  transitions: Transition[];
  currentStateId: string;
  visitedStateNames?: string[];
  isTerminal?: boolean;
}

const NODE_W = 130;
const NODE_H = 44;
const COL_GAP = 70;
const ROW_GAP = 60;
const PAD = 20;

export default function StateGraph({ states, transitions, currentStateId, visitedStateNames = [], isTerminal = false }: Props) {
  const { nodes, edges, svgW, svgH } = useMemo(() => {
    if (!states.length) return { nodes: [], edges: [], svgW: 0, svgH: 0 };

    // Separate non-terminal (main path) from terminal (branch) states
    const main = [...states].filter(s => !s.is_terminal).sort((a, b) => a.position_order - b.position_order);
    const terminals = [...states].filter(s => s.is_terminal).sort((a, b) => a.position_order - b.position_order);

    // Build node map: all states get (col, row) positions
    const nodeMap: Record<string, { x: number; y: number; state: State }> = {};

    // Lay out main-path states in a single row
    main.forEach((s, i) => {
      nodeMap[s.id] = {
        x: PAD + i * (NODE_W + COL_GAP),
        y: PAD,
        state: s,
      };
    });

    // Lay out terminals: try to place them below their source state (the state that transitions to them)
    const usedXSlots = new Set<number>();
    terminals.forEach((s) => {
      // Find who transitions to this terminal
      const inTransitions = transitions.filter(t => t.to_state === s.id);
      let preferredX = PAD + (main.length - 0.5) * (NODE_W + COL_GAP);

      if (inTransitions.length > 0) {
        const sourceNode = nodeMap[inTransitions[0].from_state];
        if (sourceNode) preferredX = sourceNode.x;
      }

      // Spread terminals if they share the same x
      while (usedXSlots.has(preferredX)) preferredX += NODE_W + 20;
      usedXSlots.add(preferredX);

      nodeMap[s.id] = {
        x: preferredX,
        y: PAD + NODE_H + ROW_GAP,
        state: s,
      };
    });

    const nodes = Object.values(nodeMap);

    // Build edges from transitions
    const edges = transitions.map(t => ({
      id: t.id,
      name: t.name,
      from: nodeMap[t.from_state],
      to: nodeMap[t.to_state],
    })).filter(e => e.from && e.to);

    const maxX = Math.max(...nodes.map(n => n.x)) + NODE_W + PAD;
    const maxY = Math.max(...nodes.map(n => n.y)) + NODE_H + PAD;

    return { nodes, edges, svgW: maxX, svgH: maxY };
  }, [states, transitions]);

  const currentState = states.find(s => s.id === currentStateId);

  function stateStatus(state: State) {
    if (state.id === currentStateId) return "active";
    if (visitedStateNames.includes(state.name)) return "completed";
    if (!currentState) return "pending";
    // Heuristic: lower position_order than current = completed (linear flows)
    if (state.position_order < (currentState?.position_order ?? 999)) return "completed";
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
          {/* Arrow marker — active */}
          <marker id="arrow-active" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#6366f1" />
          </marker>
          {/* Arrow marker — done */}
          <marker id="arrow-done" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#3fb950" />
          </marker>
          {/* Arrow marker — pending */}
          <marker id="arrow-pending" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#30363d" />
          </marker>
          {/* Glow filter for active node */}
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Edges */}
        {edges.map(e => {
          const fx = e.from.x + NODE_W;
          const fy = e.from.y + NODE_H / 2;
          const tx = e.to.x;
          const ty = e.to.y + NODE_H / 2;

          // Curved path for edges going down (branch edges)
          const isBranch = e.to.y !== e.from.y;
          const pathD = isBranch
            ? `M ${fx} ${fy} C ${fx + 30} ${fy}, ${tx - 30} ${ty}, ${tx} ${ty}`
            : `M ${fx} ${fy} L ${tx - 8} ${ty}`;

          const fromStatus = stateStatus(e.from.state);
          const stroke = fromStatus === "completed" ? "#3fb950" : fromStatus === "active" ? "#6366f1" : "#30363d";
          const markerId = fromStatus === "completed" ? "arrow-done" : fromStatus === "active" ? "arrow-active" : "arrow-pending";

          return (
            <g key={e.id}>
              <path
                d={pathD}
                fill="none"
                stroke={stroke}
                strokeWidth={1.5}
                markerEnd={`url(#${markerId})`}
                opacity={fromStatus === "pending" ? 0.4 : 1}
              />
              {/* Edge label */}
              <text
                x={(fx + tx) / 2}
                y={isBranch ? fy + (ty - fy) / 2 - 6 : fy - 8}
                textAnchor="middle"
                fontSize="9"
                fill={stroke}
                opacity={fromStatus === "pending" ? 0.4 : 0.8}
              >
                {e.name}
              </text>
            </g>
          );
        })}

        {/* Nodes */}
        {nodes.map(({ x, y, state }) => {
          const status = stateStatus(state);
          const isActive = status === "active";
          const isDone   = status === "completed";

          const fill   = isActive ? "rgba(99,102,241,0.18)" : isDone ? "rgba(63,185,80,0.12)" : "rgba(33,38,45,0.8)";
          const stroke = isActive ? "#6366f1" : isDone ? "#3fb950" : "#30363d";
          const textC  = isActive ? "#818cf8" : isDone ? "#6fda8a" : "#8b949e";

          return (
            <g key={state.id} filter={isActive ? "url(#glow)" : undefined}>
              <rect
                x={x} y={y}
                width={NODE_W} height={NODE_H}
                rx={8} ry={8}
                fill={fill}
                stroke={stroke}
                strokeWidth={isActive ? 1.5 : 1}
              />
              {/* Status icon */}
              {isDone && (
                <text x={x + 14} y={y + NODE_H / 2 + 4} fontSize="12" fill="#3fb950">✓</text>
              )}
              {isActive && (
                <circle cx={x + 14} cy={y + NODE_H / 2} r={4} fill="#6366f1">
                  <animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite" />
                </circle>
              )}
              {/* State name */}
              <text
                x={isDone || isActive ? x + 26 : x + NODE_W / 2}
                y={y + NODE_H / 2 - 4}
                textAnchor={isDone || isActive ? "start" : "middle"}
                fontSize="11"
                fontWeight={isActive ? "700" : "500"}
                fill={textC}
              >
                {state.display_name || state.name}
              </text>
              {/* Pill label: Initial / Terminal */}
              <text
                x={isDone || isActive ? x + 26 : x + NODE_W / 2}
                y={y + NODE_H / 2 + 10}
                textAnchor={isDone || isActive ? "start" : "middle"}
                fontSize="8"
                fill={textC}
                opacity="0.6"
              >
                {state.is_initial ? "start" : state.is_terminal ? "end" : ""}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
