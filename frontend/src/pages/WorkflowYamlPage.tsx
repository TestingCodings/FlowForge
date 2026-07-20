/**
 * Text-first workflow authoring (docs/BUILDER.md Part 3): YAML on the
 * left, live React Flow preview on the right, driven by the backend
 * dry-run endpoint so the parser is the single source of truth.
 */
import { useEffect, useRef, useState } from "react";
import { ReactFlow, Background, Controls, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { apiClient } from "../api/client";
import { graphFromBundle, nodeTypes } from "../components/flowGraph";

const STARTER = `workflow: My Workflow
prefix: MWF
description: Describe what this process is for

states:
  - name: Submitted        # first state is the start state
    sla_hours: 24
  - name: In Review
    role: approver
  - name: Approved
    terminal: true
  - name: Rejected
    terminal: true

transitions:
  - Submitted -> In Review: Submit
  - In Review -> Approved:
      name: Approve
      requires_approval: true
  - In Review -> Rejected: Reject
`;

interface DryRun {
  valid: boolean;
  bundle?: any;
  lint?: string[];
  name_taken?: boolean;
  errors?: string[];
}

export default function WorkflowYamlPage() {
  const navigate = useNavigate();
  const [text, setText] = useState(STARTER);
  const [dryRun, setDryRun] = useState<DryRun | null>(null);
  const [checking, setChecking] = useState(false);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [createError, setCreateError] = useState<string[]>([]);
  const latestRef = useRef(text);

  /* Debounced dry-run validation + preview */
  useEffect(() => {
    latestRef.current = text;
    setChecking(true);
    const t = setTimeout(async () => {
      const sent = text;
      try {
        const resp = await apiClient.post("/workflows/compose-yaml/?dry_run=true", { text: sent });
        if (latestRef.current !== sent) return; // stale response
        setDryRun({ valid: true, ...resp.data });
        const { nodes: n, edges: e } = graphFromBundle(resp.data.bundle);
        setNodes(n);
        // One frame later: xyflow drops edges committed alongside all-new nodes
        setTimeout(() => setEdges(e), 50);
      } catch (err: any) {
        if (latestRef.current !== sent) return;
        const detail = err?.response?.data?.detail;
        setDryRun({ valid: false, errors: Array.isArray(detail) ? detail : [String(detail ?? err)] });
      } finally {
        if (latestRef.current === sent) setChecking(false);
      }
    }, 500);
    return () => clearTimeout(t);
  }, [text]);

  const createMutation = useMutation({
    mutationFn: async () =>
      (await apiClient.post("/workflows/compose-yaml/", { text })).data,
    onSuccess: (data) => navigate(`/workflows/${data.id}`),
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      setCreateError(Array.isArray(detail) ? detail : [String(detail ?? err)]);
    },
  });

  const canCreate = Boolean(dryRun?.valid) && !dryRun?.name_taken && !checking;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 56px)" }}>
      {/* Top bar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, padding: "10px 16px",
        background: "var(--bg-surface)", borderBottom: "1px solid var(--border)", flexShrink: 0,
      }}>
        <div style={{ fontWeight: 700, fontSize: "0.9rem", color: "var(--accent-light)" }}>
          YAML Workflow Editor
        </div>
        <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
          {checking ? "Validating…" : dryRun?.valid ? "✓ Valid" : dryRun ? "Has errors" : ""}
        </span>
        <div style={{ flex: 1 }} />
        <Link to="/workflows/new" className="btn-secondary btn-sm" style={{ textDecoration: "none" }}>
          Visual builder
        </Link>
        <button
          className="btn-primary btn-sm"
          onClick={() => { setCreateError([]); createMutation.mutate(); }}
          disabled={!canCreate || createMutation.isPending}
          style={{ minWidth: 130 }}
        >
          {createMutation.isPending ? "Creating…" : "Create Workflow"}
        </button>
      </div>

      {/* Editor + preview */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* Left: text editor + messages */}
        <div style={{
          width: "44%", minWidth: 380, display: "flex", flexDirection: "column",
          borderRight: "1px solid var(--border)",
        }}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            spellCheck={false}
            style={{
              flex: 1, resize: "none", border: "none", outline: "none",
              background: "var(--bg-base)", color: "var(--text-primary)",
              fontFamily: "ui-monospace, 'Cascadia Code', Consolas, monospace",
              fontSize: "0.85rem", lineHeight: 1.6, padding: 16,
              tabSize: 2 as any,
            }}
          />
          {/* Messages */}
          <div style={{
            maxHeight: "38%", overflowY: "auto", flexShrink: 0,
            borderTop: "1px solid var(--border)", background: "var(--bg-surface)",
            padding: "8px 12px", display: "flex", flexDirection: "column", gap: 4,
          }}>
            {dryRun && !dryRun.valid && (dryRun.errors ?? []).map((e, i) => (
              <div key={`e${i}`} style={{ fontSize: "0.8rem", color: "var(--danger, #f85149)" }}>✕ {e}</div>
            ))}
            {createError.map((e, i) => (
              <div key={`c${i}`} style={{ fontSize: "0.8rem", color: "var(--danger, #f85149)" }}>✕ {e}</div>
            ))}
            {dryRun?.valid && dryRun.name_taken && (
              <div style={{ fontSize: "0.8rem", color: "#d29922" }}>
                ⚠ A workflow with this name already exists — pick another name.
              </div>
            )}
            {dryRun?.valid && (dryRun.lint ?? []).map((w, i) => (
              <div key={`w${i}`} style={{ fontSize: "0.8rem", color: "#d29922" }}>⚠ {w}</div>
            ))}
            {dryRun?.valid && !dryRun.name_taken && (dryRun.lint ?? []).length === 0 && (
              <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                No problems found.
              </div>
            )}
          </div>
        </div>

        {/* Right: live preview */}
        <div style={{ flex: 1, background: "var(--bg-base)", position: "relative" }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            style={{ background: "var(--bg-base)" }}
          >
            <Background color="#21262d" gap={24} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
          {dryRun && !dryRun.valid && (
            <div style={{
              position: "absolute", inset: 0, display: "flex", alignItems: "center",
              justifyContent: "center", background: "rgba(0,0,0,0.35)", pointerEvents: "none",
            }}>
              <span style={{ fontSize: "0.9rem", color: "var(--text-secondary)" }}>
                Preview paused — fix the errors on the left
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
