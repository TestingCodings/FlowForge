import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import {
  ReactFlow, Background, Controls, MiniMap, Handle, Position,
  getNodesBounds, getViewportForBounds,
  type Node, type Edge, type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { toPng } from "html-to-image";

import { apiClient } from "../api/client";
import { TopologyResponse, TopologyNode } from "../types/api";
import { layoutGraph, NODE_W } from "../components/flowGraph";

/* A stable colour per workflow name, so each system type reads distinctly. */
const PALETTE = ["#6366f1", "#3fb950", "#d29922", "#58a6ff", "#db61a2", "#a371f7", "#f0883e"];
function workflowColour(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

interface AssetData extends Record<string, unknown> {
  node: TopologyNode;
  onOpen: (id: string) => void;
}

function AssetNode({ data }: NodeProps) {
  const { node, onOpen } = data as AssetData;
  const colour = workflowColour(node.workflow);
  return (
    <div
      onClick={() => onOpen(node.id)}
      title={`${node.reference} · ${node.workflow}`}
      style={{
        width: NODE_W, padding: "9px 12px", borderRadius: 10,
        border: `2px solid ${colour}`,
        background: node.completed ? "rgba(255,255,255,0.03)" : `${colour}14`,
        cursor: "pointer", opacity: node.completed ? 0.7 : 1,
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
        <span style={{
          fontSize: 8, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em",
          background: `${colour}30`, color: colour, padding: "2px 5px", borderRadius: 4,
        }}>
          {node.workflow}
        </span>
      </div>
      <div style={{ fontFamily: "monospace", fontSize: 11, fontWeight: 600, color: "#e6edf3" }}>
        {node.reference}
      </div>
      {node.title && (
        <div style={{ fontSize: 10, color: "#8b949e", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {node.title}
        </div>
      )}
      {node.state && (
        <div style={{ fontSize: 9, color: colour, marginTop: 3 }}>{node.state}</div>
      )}
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { asset: AssetNode };

export default function TopologyPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const root = params.get("root") ?? "";
  const depth = params.get("depth") ?? "2";
  const relFilter = params.get("rel_types") ?? "";

  const query = useMemo(() => {
    const qs = new URLSearchParams();
    if (root) { qs.set("root", root); qs.set("depth", depth); }
    if (relFilter) qs.set("rel_types", relFilter);
    return qs.toString();
  }, [root, depth, relFilter]);

  const { data, isLoading } = useQuery<TopologyResponse>({
    queryKey: ["topology", query],
    queryFn: async () => (await apiClient.get(`/topology/?${query}`)).data,
  });

  const { nodes, edges, relTypes } = useMemo(() => {
    if (!data) return { nodes: [] as Node[], edges: [] as Edge[], relTypes: [] as string[] };
    const rawNodes: Node[] = data.nodes.map((n) => ({
      id: n.id,
      type: "asset",
      position: { x: 0, y: 0 },
      data: { node: n, onOpen: (id: string) => navigate(`/instances/${id}`) } as AssetData,
    }));
    const rawEdges: Edge[] = data.edges.map((e) => ({
      id: e.id, source: e.source, target: e.target,
      label: e.type,
      labelStyle: { fontSize: 10, fill: "#8b949e" },
      labelBgStyle: { fill: "#161b22" },
      style: {
        stroke: e.kind === "containment" ? "#8b949e" : "#6366f1",
        strokeWidth: 1.5,
        strokeDasharray: e.kind === "containment" ? "5,4" : undefined,
      },
      markerEnd: { type: "arrowclosed" as any, color: e.kind === "containment" ? "#8b949e" : "#6366f1" },
    }));
    const laidOut = layoutGraph(rawNodes, rawEdges);
    const relTypes = [...new Set(data.edges.filter((e) => e.kind === "relationship").map((e) => e.type))];
    return { nodes: laidOut, edges: rawEdges, relTypes };
  }, [data, navigate]);

  const exportPng = async () => {
    const vp = document.querySelector(".react-flow__viewport") as HTMLElement | null;
    if (!vp || nodes.length === 0) return;
    const bounds = getNodesBounds(nodes);
    const w = Math.max(640, Math.round(bounds.width) + 120);
    const h = Math.max(400, Math.round(bounds.height) + 120);
    const t = getViewportForBounds(bounds, w, h, 0.4, 2, 0.1);
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg-base").trim() || "#0d1117";
    const url = await toPng(vp, {
      backgroundColor: bg, width: w, height: h, pixelRatio: 2,
      style: { width: `${w}px`, height: `${h}px`, transform: `translate(${t.x}px,${t.y}px) scale(${t.zoom})`, transformOrigin: "top left" },
    });
    const a = document.createElement("a");
    a.href = url; a.download = "topology.png"; a.click();
  };

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>Topology</h2>
          <p>A live map of instances and how they connect — across every workflow.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary btn-sm" onClick={exportPng}>⤓ PNG</button>
        </div>
      </div>

      {/* Filters */}
      <div className="card" style={{ padding: "10px 14px", marginBottom: 12, display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
        {root ? (
          <>
            <span className="text-xs text-muted">Rooted at one instance ·</span>
            <label className="text-xs" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              Depth
              <select value={depth} onChange={(e) => setParams((p) => { p.set("depth", e.target.value); return p; })}
                style={{ padding: "3px 8px", fontSize: "0.8rem" }}>
                {["1", "2", "3", "4"].map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
            <button className="btn-ghost btn-sm" onClick={() => setParams({})}>Show whole estate</button>
          </>
        ) : (
          <span className="text-xs text-muted">Whole estate — open an instance's "View topology" to focus on one.</span>
        )}
        {relTypes.length > 0 && (
          <label className="text-xs" style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
            Relationship
            <select
              value={relFilter}
              onChange={(e) => setParams((p) => { e.target.value ? p.set("rel_types", e.target.value) : p.delete("rel_types"); return p; })}
              style={{ padding: "3px 8px", fontSize: "0.8rem" }}
            >
              <option value="">All types</option>
              {relTypes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
        )}
      </div>

      {data?.truncated && (
        <div className="alert" style={{ marginBottom: 12, background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", fontSize: "0.82rem" }}>
          Showing the first {nodes.length} instances — narrow with a root or a relationship filter to see more detail.
        </div>
      )}

      <div style={{ height: "calc(100vh - 230px)", minHeight: 420, background: "var(--bg-base)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
        {isLoading ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--text-secondary)" }}>Loading topology…</div>
        ) : nodes.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--text-secondary)" }}>
            No linked instances to map yet. Link instances (or add sub-instances) and they appear here.
          </div>
        ) : (
          <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.2 }} minZoom={0.1}>
            <Background color="#21262d" gap={24} size={1} />
            <Controls />
            <MiniMap style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
              nodeColor={(n) => workflowColour((n.data as AssetData).node.workflow)} />
          </ReactFlow>
        )}
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 16, marginTop: 10, fontSize: "0.78rem", color: "var(--text-secondary)", flexWrap: "wrap" }}>
        <span><span style={{ display: "inline-block", width: 18, height: 0, borderTop: "2px solid #6366f1", verticalAlign: "middle", marginRight: 5 }} />relationship</span>
        <span><span style={{ display: "inline-block", width: 18, height: 0, borderTop: "2px dashed #8b949e", verticalAlign: "middle", marginRight: 5 }} />containment</span>
        <span style={{ marginLeft: "auto" }}>Node colour = workflow · click a node to open the instance</span>
      </div>
    </div>
  );
}
