import { useCallback, useEffect, useState, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type Connection,
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";

/* ─── Types ─── */
interface StateNodeData {
  label: string;
  isInitial: boolean;
  isTerminal: boolean;
  slaHours: number;
  requiresTask: boolean;
  defaultRole: string;
  serverId?: string; // set when hydrated from an existing workflow
}

/* ─── Custom node ─── */
function StateNode({ data, selected }: NodeProps) {
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

const nodeTypes = { stateNode: StateNode };

/* ─── Draft persistence + undo history ─── */
const DRAFT_KEY = "flowforge:builder-draft";
const HISTORY_LIMIT = 50;

interface Snapshot {
  nodes: Node[];
  edges: Edge[];
}

interface BuilderDraft extends Snapshot {
  wfName: string;
  wfDesc: string;
  wfPrefix: string;
  wfActive: boolean;
  savedAt: string;
}

function loadDraft(): BuilderDraft | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const draft = JSON.parse(raw) as BuilderDraft;
    if (!Array.isArray(draft.nodes) || !Array.isArray(draft.edges)) return null;
    return draft;
  } catch {
    return null;
  }
}

/* ─── Default empty state for new node ─── */
function makeNode(id: string, position: { x: number; y: number }, isInitial = false): Node {
  return {
    id,
    type: "stateNode",
    position,
    data: {
      label: isInitial ? "Initial State" : "New State",
      isInitial,
      isTerminal: false,
      slaHours: isInitial ? 48 : 24,
      requiresTask: true,
      defaultRole: isInitial ? "participant" : "approver",
    } as StateNodeData,
  };
}

/* ─── Edge factory (shared by connect dialog + hydration) ─── */
function makeEdge(
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

/* ─── Main page ─── */
export default function WorkflowBuilderPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { id: editId } = useParams<{ id: string }>();
  const isEdit = Boolean(editId);
  const nodeIdRef = useRef(2);
  const hydratedRef = useRef(false);

  // Workflow metadata
  const [wfName, setWfName] = useState("");
  const [wfDesc, setWfDesc] = useState("");
  const [wfPrefix, setWfPrefix] = useState("WFF");
  const [wfActive, setWfActive] = useState(true);

  // Canvas state
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([
    makeNode("1", { x: 60, y: 120 }, true),
  ]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Selection
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  // Pending connection (for naming the transition)
  const [pendingConn, setPendingConn] = useState<Connection | null>(null);
  const [pendingTransName, setPendingTransName] = useState("Transition");

  // Errors
  const [errors, setErrors] = useState<string[]>([]);
  const [saveSuccess, setSaveSuccess] = useState("");

  // Draft found in localStorage at mount (offer resume until acted on).
  // Edit mode skips drafts entirely — the server graph is the source of truth.
  const [pendingDraft, setPendingDraft] = useState<BuilderDraft | null>(() =>
    isEdit ? null : loadDraft()
  );

  // 409 from compose: workflow has instances, offer publish-new-version flow
  const [conflict, setConflict] = useState<string | null>(null);

  // Load the workflow being edited
  const { data: editWf, isLoading: editLoading } = useQuery({
    queryKey: ["workflow", editId],
    queryFn: async () => (await apiClient.get(`/workflows/${editId}/`)).data,
    enabled: isEdit,
  });

  // Undo/redo history (structural changes + node moves)
  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);
  const [, setHistoryVersion] = useState(0); // re-render for button disabled state

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);
  const selectedEdge = edges.find((e) => e.id === selectedEdgeId);

  const takeSnapshot = useCallback(() => {
    past.current = [...past.current.slice(-(HISTORY_LIMIT - 1)), { nodes, edges }];
    future.current = [];
    setHistoryVersion((v) => v + 1);
  }, [nodes, edges]);

  const undo = useCallback(() => {
    const prev = past.current.pop();
    if (!prev) return;
    future.current.push({ nodes, edges });
    setNodes(prev.nodes);
    setEdges(prev.edges);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setHistoryVersion((v) => v + 1);
  }, [nodes, edges, setNodes, setEdges]);

  const redo = useCallback(() => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push({ nodes, edges });
    setNodes(next.nodes);
    setEdges(next.edges);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setHistoryVersion((v) => v + 1);
  }, [nodes, edges, setNodes, setEdges]);

  /* ─── Callbacks ─── */
  const onConnect = useCallback((conn: Connection) => {
    setPendingConn(conn);
    const fromNode = nodes.find((n) => n.id === conn.source);
    const toNode   = nodes.find((n) => n.id === conn.target);
    const fromLabel = (fromNode?.data as StateNodeData)?.label ?? "State";
    const toLabel   = (toNode?.data as StateNodeData)?.label ?? "State";
    setPendingTransName(`${fromLabel} → ${toLabel}`);
  }, [nodes]);

  const confirmConnection = () => {
    if (!pendingConn) return;
    takeSnapshot();
    const id = `e${pendingConn.source}-${pendingConn.target}`;
    setEdges((eds) => addEdge(
      makeEdge(id, pendingConn.source!, pendingConn.target!, pendingTransName, false),
      eds,
    ));
    setPendingConn(null);
  };

  const addState = () => {
    takeSnapshot();
    const id = String(nodeIdRef.current++);
    const x = 80 + (nodes.length % 4) * 200;
    const y = 80 + Math.floor(nodes.length / 4) * 130;
    setNodes((ns) => [...ns, makeNode(id, { x, y })]);
    setSelectedNodeId(id);
    setSelectedEdgeId(null);
  };

  const deleteSelected = () => {
    if (!selectedNodeId && !selectedEdgeId) return;
    takeSnapshot();
    if (selectedNodeId) {
      setNodes((ns) => ns.filter((n) => n.id !== selectedNodeId));
      setEdges((es) => es.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId));
      setSelectedNodeId(null);
    }
    if (selectedEdgeId) {
      setEdges((es) => es.filter((e) => e.id !== selectedEdgeId));
      setSelectedEdgeId(null);
    }
  };

  const updateNodeData = (field: keyof StateNodeData, value: unknown) => {
    if (!selectedNodeId) return;
    setNodes((ns) =>
      ns.map((n) =>
        n.id === selectedNodeId
          ? { ...n, data: { ...n.data, [field]: value } }
          : n
      )
    );
    // If marking as initial, clear all other initials
    if (field === "isInitial" && value === true) {
      setNodes((ns) =>
        ns.map((n) =>
          n.id === selectedNodeId
            ? n
            : { ...n, data: { ...n.data, isInitial: false } }
        )
      );
    }
  };

  const updateEdgeLabel = (newName: string) => {
    if (!selectedEdgeId) return;
    setEdges((es) =>
      es.map((e) =>
        e.id === selectedEdgeId
          ? { ...e, label: newName, data: { ...e.data, name: newName } }
          : e
      )
    );
  };

  const toggleEdgeApproval = () => {
    if (!selectedEdgeId) return;
    setEdges((es) =>
      es.map((e) =>
        e.id === selectedEdgeId
          ? {
              ...e,
              data: { ...e.data, requiresApproval: !(e.data as any)?.requiresApproval },
              style: {
                ...e.style,
                stroke: (e.data as any)?.requiresApproval ? "#6366f1" : "#d29922",
                strokeDasharray: (e.data as any)?.requiresApproval ? undefined : "6,3",
              },
            }
          : e
      )
    );
  };

  /* ─── Validate + build payload ─── */
  const validate = (): string[] => {
    const errs: string[] = [];
    if (!wfName.trim()) errs.push("Workflow name is required");
    if (!wfPrefix.trim()) errs.push("Reference prefix is required");
    if (nodes.length === 0) errs.push("Add at least one state");
    const initials = nodes.filter((n) => (n.data as StateNodeData).isInitial);
    if (initials.length !== 1) errs.push("Exactly one state must be marked as the start state");
    const names = nodes.map((n) => ((n.data as StateNodeData).label || "").trim());
    if (names.some((n) => !n)) errs.push("All states must have a name");
    if (new Set(names).size !== names.length) errs.push("State names must be unique");
    return errs;
  };

  const buildPayload = () => {
    const statePayloads = nodes.map((n, i) => {
      const d = n.data as StateNodeData;
      return {
        ...(d.serverId ? { id: d.serverId } : {}),
        name: d.label.trim(),
        display_name: d.label.trim(),
        is_initial: d.isInitial,
        is_terminal: d.isTerminal,
        position_order: i + 1,
        sla_config: d.slaHours > 0 ? { sla_hours: d.slaHours } : {},
        task_config: {
          requires_task: d.requiresTask && !d.isTerminal,
          default_role: d.defaultRole || "participant",
        },
        canvas_position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
      };
    });

    const transPayloads = edges.map((e) => {
      const fromNode = nodes.find((n) => n.id === e.source);
      const toNode   = nodes.find((n) => n.id === e.target);
      const serverId = (e.data as any)?.serverId;
      return {
        ...(serverId ? { id: serverId } : {}),
        name: ((e.data as any)?.name || e.label || "Transition") as string,
        from_state: ((fromNode?.data as StateNodeData)?.label ?? "").trim(),
        to_state:   ((toNode?.data as StateNodeData)?.label ?? "").trim(),
        requires_approval: Boolean((e.data as any)?.requiresApproval),
      };
    });

    return {
      name: wfName.trim(),
      description: wfDesc.trim(),
      reference_prefix: wfPrefix.trim().toUpperCase().slice(0, 10),
      ...(isEdit ? {} : { version: 1 }),
      is_active: wfActive,
      states: statePayloads,
      transitions: transPayloads,
    };
  };

  /* ─── Hydrate canvas from an existing workflow (edit mode) ─── */
  useEffect(() => {
    if (!isEdit || !editWf || hydratedRef.current) return;

    setWfName(editWf.name ?? "");
    setWfDesc(editWf.description ?? "");
    setWfPrefix(editWf.reference_prefix ?? "WFF");
    setWfActive(Boolean(editWf.is_active));

    const states = [...(editWf.states ?? [])].sort(
      (a: any, b: any) => a.position_order - b.position_order
    );
    const hydratedNodes: Node[] = states.map((s: any, i: number) => ({
      id: String(s.id),
      type: "stateNode",
      position:
        s.canvas_position && typeof s.canvas_position.x === "number"
          ? { x: s.canvas_position.x, y: s.canvas_position.y }
          : { x: 80 + (i % 4) * 220, y: 80 + Math.floor(i / 4) * 140 },
      data: {
        label: s.name,
        isInitial: Boolean(s.is_initial),
        isTerminal: Boolean(s.is_terminal),
        slaHours: Number(s.sla_config?.sla_hours ?? 0),
        requiresTask: Boolean(s.task_config?.requires_task ?? true),
        defaultRole: s.task_config?.default_role ?? "participant",
        serverId: String(s.id),
      } as StateNodeData,
    }));
    const hydratedEdges: Edge[] = (editWf.transitions ?? []).map((t: any) =>
      makeEdge(
        String(t.id), String(t.from_state), String(t.to_state),
        t.name, Boolean(t.requires_approval), String(t.id),
      )
    );
    // Edges land one frame after nodes: xyflow drops edges applied in the
    // same commit that replaces all nodes (skipped before measurement).
    // hydratedRef flips inside the timer so a StrictMode double-invoke
    // (which clears the first timer via cleanup) still hydrates once.
    setNodes(hydratedNodes);
    const t = setTimeout(() => {
      hydratedRef.current = true;
      setEdges(hydratedEdges);
    }, 50);
    return () => clearTimeout(t);
  }, [isEdit, editWf, setNodes, setEdges]);

  /* ─── Draft persistence (debounced autosave to localStorage; create mode only) ─── */
  useEffect(() => {
    if (isEdit) return;
    // Don't clobber a not-yet-resumed draft with the pristine initial canvas
    if (pendingDraft) return;
    const dirty = nodes.length > 1 || edges.length > 0 || wfName.trim() !== "" || wfDesc.trim() !== "";
    const t = setTimeout(() => {
      if (!dirty) {
        localStorage.removeItem(DRAFT_KEY);
        return;
      }
      const draft: BuilderDraft = {
        nodes, edges, wfName, wfDesc, wfPrefix, wfActive,
        savedAt: new Date().toISOString(),
      };
      try { localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)); } catch { /* quota */ }
    }, 1000);
    return () => clearTimeout(t);
  }, [nodes, edges, wfName, wfDesc, wfPrefix, wfActive, pendingDraft]);

  const resumeDraft = () => {
    if (!pendingDraft) return;
    setNodes(pendingDraft.nodes);
    setEdges(pendingDraft.edges);
    setWfName(pendingDraft.wfName ?? "");
    setWfDesc(pendingDraft.wfDesc ?? "");
    setWfPrefix(pendingDraft.wfPrefix ?? "WFF");
    setWfActive(pendingDraft.wfActive ?? true);
    const maxId = Math.max(0, ...pendingDraft.nodes.map((n) => Number(n.id)).filter(Number.isFinite));
    nodeIdRef.current = maxId + 1;
    setPendingDraft(null);
  };

  const discardDraft = () => {
    localStorage.removeItem(DRAFT_KEY);
    setPendingDraft(null);
  };

  /* ─── Keyboard: undo/redo/delete (skip while typing in a field) ─── */
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo(); else undo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        redo();
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        deleteSelected();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const errs = validate();
      if (errs.length) { setErrors(errs); throw new Error("validation"); }
      setErrors([]);
      setConflict(null);
      if (isEdit) {
        return (await apiClient.put(`/workflows/${editId}/compose/`, buildPayload())).data;
      }
      return (await apiClient.post("/workflows/", buildPayload())).data;
    },
    onSuccess: (data) => {
      if (!isEdit) localStorage.removeItem(DRAFT_KEY);
      qc.invalidateQueries({ queryKey: ["workflows"] });
      qc.invalidateQueries({ queryKey: ["workflow", editId] });
      setSaveSuccess(`Saved! Redirecting to ${data.name}…`);
      setTimeout(() => navigate(`/workflows/${data.id}`), 1200);
    },
    onError: (err: any) => {
      if (err.message === "validation") return;
      if (err?.response?.status === 409) {
        setConflict(err.response.data?.detail ?? "This workflow has instances.");
        return;
      }
      const detail = err?.response?.data;
      const list = Array.isArray(detail?.detail) ? detail.detail
        : [typeof detail === "string" ? detail : JSON.stringify(detail)];
      setErrors(list);
    },
  });

  /* 409 recovery: publish a draft clone, remap ids by name, apply edits to it */
  const publishMutation = useMutation({
    mutationFn: async () => {
      const pub = (await apiClient.post(`/workflows/${editId}/publish-new-version/`)).data;
      const payload = buildPayload();
      const stateIdByName = new Map<string, string>(
        (pub.states ?? []).map((s: any) => [s.name, String(s.id)])
      );
      const stateNameById = new Map<string, string>(
        (pub.states ?? []).map((s: any) => [String(s.id), s.name])
      );
      const transIdByKey = new Map<string, string>(
        (pub.transitions ?? []).map((t: any) => [
          `${stateNameById.get(String(t.from_state))}→${stateNameById.get(String(t.to_state))}→${t.name}`,
          String(t.id),
        ])
      );
      // Stale ids belong to the old version — remap to the clone's ids where
      // names still match (preserves cloned forms/rules on unrenamed entities)
      payload.states = payload.states.map((s: any) => {
        const { id: _old, ...rest } = s;
        const cloneId = stateIdByName.get(rest.name);
        return cloneId ? { id: cloneId, ...rest } : rest;
      });
      payload.transitions = payload.transitions.map((t: any) => {
        const { id: _old, ...rest } = t;
        const cloneId = transIdByKey.get(`${rest.from_state}→${rest.to_state}→${rest.name}`);
        return cloneId ? { id: cloneId, ...rest } : rest;
      });
      payload.name = pub.name; // clone's draft name avoids the unique-name clash
      return (await apiClient.put(`/workflows/${pub.id}/compose/`, payload)).data;
    },
    onSuccess: (data) => {
      setConflict(null);
      qc.invalidateQueries({ queryKey: ["workflows"] });
      setSaveSuccess(`Published ${data.name} with your changes. Redirecting…`);
      setTimeout(() => navigate(`/workflows/${data.id}`), 1200);
    },
    onError: (err: any) => {
      const detail = err?.response?.data;
      setErrors([typeof detail === "string" ? detail : JSON.stringify(detail)]);
    },
  });

  /* ─── Render ─── */
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 56px)", gap: 0 }}>
      {/* Top bar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, padding: "10px 16px",
        background: "var(--bg-surface)", borderBottom: "1px solid var(--border)",
        flexShrink: 0,
      }}>
        <div style={{ fontWeight: 700, fontSize: "0.9rem", color: "var(--accent-light)", marginRight: 4 }}>
          {isEdit ? "Edit Workflow" : "Workflow Builder"}
        </div>
        {isEdit && editLoading && (
          <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>Loading…</span>
        )}

        <input
          placeholder="Workflow name *"
          value={wfName}
          onChange={(e) => setWfName(e.target.value)}
          style={{ width: 220, padding: "6px 10px", fontSize: "0.85rem" }}
        />
        <input
          placeholder="Description"
          value={wfDesc}
          onChange={(e) => setWfDesc(e.target.value)}
          style={{ width: 200, padding: "6px 10px", fontSize: "0.85rem" }}
        />
        <input
          placeholder="PREFIX"
          value={wfPrefix}
          onChange={(e) => setWfPrefix(e.target.value.toUpperCase().slice(0, 10))}
          style={{ width: 90, padding: "6px 10px", fontSize: "0.85rem", fontFamily: "monospace" }}
        />

        <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: "0.82rem", color: "var(--text-secondary)", cursor: "pointer", marginLeft: 2 }}>
          <input type="checkbox" checked={wfActive} onChange={(e) => setWfActive(e.target.checked)} style={{ width: "auto" }} />
          Active
        </label>

        <div style={{ flex: 1 }} />

        <button
          className="btn-secondary btn-sm hint"
          onClick={undo}
          disabled={past.current.length === 0}
          data-hint="Undo (Ctrl+Z)"
          style={{ padding: "4px 10px" }}
        >
          ↩
        </button>
        <button
          className="btn-secondary btn-sm hint"
          onClick={redo}
          disabled={future.current.length === 0}
          data-hint="Redo (Ctrl+Shift+Z)"
          style={{ padding: "4px 10px" }}
        >
          ↪
        </button>
        <button className="btn-secondary btn-sm" onClick={addState}>
          + Add State
        </button>
        {(selectedNodeId || selectedEdgeId) && (
          <button className="btn-danger btn-sm" onClick={deleteSelected}>
            Delete
          </button>
        )}
        <button
          className="btn-primary btn-sm"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          style={{ minWidth: 120 }}
        >
          {saveMutation.isPending ? "Saving…" : isEdit ? "Save Changes" : "Save Workflow"}
        </button>
      </div>

      {/* Resume draft banner */}
      {pendingDraft && (
        <div className="alert" style={{
          margin: "8px 16px", flexShrink: 0, display: "flex", alignItems: "center", gap: 12,
          background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 14px",
        }}>
          <span style={{ fontSize: "0.85rem", color: "var(--text-primary)", flex: 1 }}>
            You have an unsaved draft{pendingDraft.wfName ? ` — "${pendingDraft.wfName}"` : ""} from{" "}
            {new Date(pendingDraft.savedAt).toLocaleString()}. Resume it?
          </span>
          <button className="btn-primary btn-sm" onClick={resumeDraft}>Resume draft</button>
          <button className="btn-secondary btn-sm" onClick={discardDraft}>Discard</button>
        </div>
      )}

      {/* Compose conflict: workflow has instances */}
      {conflict && (
        <div className="alert alert-error" style={{
          margin: "8px 16px", flexShrink: 0, display: "flex", alignItems: "center", gap: 12,
        }}>
          <span style={{ flex: 1 }}>{conflict}</span>
          <button
            className="btn-primary btn-sm"
            onClick={() => publishMutation.mutate()}
            disabled={publishMutation.isPending}
            style={{ flexShrink: 0 }}
          >
            {publishMutation.isPending ? "Publishing…" : "Publish new version with these changes"}
          </button>
          <button className="btn-secondary btn-sm" onClick={() => setConflict(null)}>Cancel</button>
        </div>
      )}

      {/* Errors */}
      {errors.length > 0 && (
        <div className="alert alert-error" style={{ margin: "8px 16px", flexShrink: 0 }}>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}
      {saveSuccess && (
        <div className="alert alert-success" style={{ margin: "8px 16px", flexShrink: 0 }}>
          {saveSuccess}
        </div>
      )}

      {/* Canvas + properties panel */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* React Flow canvas */}
        <div style={{ flex: 1, background: "var(--bg-base)" }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeDragStart={() => takeSnapshot()}
            onNodeClick={(_, node) => { setSelectedNodeId(node.id); setSelectedEdgeId(null); }}
            onEdgeClick={(_, edge) => { setSelectedEdgeId(edge.id); setSelectedNodeId(null); }}
            onPaneClick={() => { setSelectedNodeId(null); setSelectedEdgeId(null); }}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            deleteKeyCode={null}
            style={{ background: "var(--bg-base)" }}
          >
            <Background color="#21262d" gap={24} size={1} />
            <Controls style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }} />
            <MiniMap
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
              nodeColor={(n) => {
                const d = n.data as StateNodeData;
                return d.isInitial ? "#6366f1" : d.isTerminal ? "#3fb950" : "#30363d";
              }}
            />
          </ReactFlow>
        </div>

        {/* Properties panel */}
        <div style={{
          width: 280, flexShrink: 0,
          background: "var(--bg-surface)", borderLeft: "1px solid var(--border)",
          padding: 16, overflowY: "auto", display: "flex", flexDirection: "column", gap: 16,
        }}>
          {/* Node editor */}
          {selectedNode ? (
            <NodeEditor
              node={selectedNode}
              onUpdate={updateNodeData}
            />
          ) : selectedEdge ? (
            <EdgeEditor
              edge={selectedEdge}
              onUpdateName={updateEdgeLabel}
              onToggleApproval={toggleEdgeApproval}
            />
          ) : (
            <CanvasHelp nodesCount={nodes.length} edgesCount={edges.length} />
          )}
        </div>
      </div>

      {/* Transition naming modal */}
      {pendingConn && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999,
        }}>
          <div style={{
            background: "var(--bg-surface)", border: "1px solid var(--border)",
            borderRadius: 14, padding: 24, width: 360,
            boxShadow: "var(--shadow-lg)",
          }}>
            <h3 style={{ marginBottom: 14, fontSize: "1rem" }}>Name this transition</h3>
            <div className="form-group">
              <label>Transition name</label>
              <input
                value={pendingTransName}
                onChange={(e) => setPendingTransName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && confirmConnection()}
                autoFocus
              />
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button className="btn-primary" onClick={confirmConnection} style={{ flex: 1 }}>
                Add Transition
              </button>
              <button className="btn-secondary" onClick={() => setPendingConn(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Node properties panel ─── */
function NodeEditor({ node, onUpdate }: { node: Node; onUpdate: (f: keyof StateNodeData, v: unknown) => void }) {
  const d = node.data as StateNodeData;
  return (
    <div>
      <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-secondary)", marginBottom: 12 }}>
        State Properties
      </div>

      <div className="form-group">
        <label>State name</label>
        <input value={d.label} onChange={(e) => onUpdate("label", e.target.value)} autoFocus />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", color: "var(--text-primary)" }}>
          <input type="checkbox" checked={d.isInitial} onChange={(e) => onUpdate("isInitial", e.target.checked)} style={{ width: "auto" }} />
          <span style={{ fontSize: "0.85rem" }}>Start state</span>
          <span className="badge badge-initial" style={{ fontSize: "0.65rem" }}>START</span>
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", color: "var(--text-primary)" }}>
          <input type="checkbox" checked={d.isTerminal} onChange={(e) => onUpdate("isTerminal", e.target.checked)} style={{ width: "auto" }} />
          <span style={{ fontSize: "0.85rem" }}>Terminal (end) state</span>
          <span className="badge badge-terminal" style={{ fontSize: "0.65rem" }}>END</span>
        </label>
      </div>

      <div className="divider" />

      <div className="form-group">
        <label>SLA hours</label>
        <input
          type="number" min={0}
          value={d.slaHours}
          onChange={(e) => onUpdate("slaHours", Number(e.target.value))}
        />
      </div>

      {!d.isTerminal && (
        <>
          <div className="form-group">
            <label>Default assigned role</label>
            <select value={d.defaultRole} onChange={(e) => onUpdate("defaultRole", e.target.value)}>
              <option value="participant">Participant</option>
              <option value="approver">Approver</option>
              <option value="workflow_designer">Workflow Designer</option>
              <option value="platform_admin">Platform Admin</option>
            </select>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", color: "var(--text-primary)", fontSize: "0.85rem" }}>
            <input type="checkbox" checked={d.requiresTask} onChange={(e) => onUpdate("requiresTask", e.target.checked)} style={{ width: "auto" }} />
            Creates a task when entered
          </label>
        </>
      )}

      <div style={{ marginTop: 16, padding: "10px 12px", background: "var(--bg-elevated)", borderRadius: 8, fontSize: "0.78rem", color: "var(--text-secondary)" }}>
        Drag from the <strong style={{ color: "var(--accent-light)" }}>right handle →</strong> to another state's left handle to create a transition.
      </div>
    </div>
  );
}

/* ─── Edge properties panel ─── */
function EdgeEditor({ edge, onUpdateName, onToggleApproval }: {
  edge: Edge;
  onUpdateName: (n: string) => void;
  onToggleApproval: () => void;
}) {
  const requiresApproval = Boolean((edge.data as any)?.requiresApproval);
  return (
    <div>
      <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-secondary)", marginBottom: 12 }}>
        Transition Properties
      </div>
      <div className="form-group">
        <label>Transition name</label>
        <input
          value={String(edge.label ?? (edge.data as any)?.name ?? "")}
          onChange={(e) => onUpdateName(e.target.value)}
          autoFocus
        />
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", color: "var(--text-primary)", fontSize: "0.85rem" }}>
        <input type="checkbox" checked={requiresApproval} onChange={onToggleApproval} style={{ width: "auto" }} />
        Requires approval
        {requiresApproval && <span className="badge badge-pending" style={{ fontSize: "0.65rem" }}>APPROVAL</span>}
      </label>
      <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--bg-elevated)", borderRadius: 8, fontSize: "0.78rem", color: "var(--text-secondary)" }}>
        Click away or press <strong style={{ color: "var(--text-primary)" }}>Backspace/Delete</strong> on the canvas to remove this transition.
      </div>
    </div>
  );
}

/* ─── Empty canvas help ─── */
function CanvasHelp({ nodesCount, edgesCount }: { nodesCount: number; edgesCount: number }) {
  return (
    <div>
      <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-secondary)", marginBottom: 12 }}>
        How to build
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {[
          { num: "1", text: "Click + Add State to create a new state node on the canvas" },
          { num: "2", text: "Click a state to select it and edit its name, SLA, and role in this panel" },
          { num: "3", text: "Mark exactly one state as Start and one or more as End (terminal)" },
          { num: "4", text: "Drag from the → handle on a state's right edge to another state's left edge to create a transition" },
          { num: "5", text: "Name the transition in the dialog, then click an edge to set approval requirements" },
          { num: "6", text: "Enter a workflow name and prefix above, then click Save Workflow" },
        ].map((step) => (
          <div key={step.num} style={{ display: "flex", gap: 10 }}>
            <div style={{ width: 20, height: 20, borderRadius: "50%", background: "rgba(99,102,241,0.2)", color: "var(--accent-light)", fontSize: "0.72rem", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}>
              {step.num}
            </div>
            <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.5, margin: 0 }}>{step.text}</p>
          </div>
        ))}
      </div>
      <div className="divider" />
      <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
        <strong style={{ color: "var(--text-primary)" }}>{nodesCount}</strong> states ·{" "}
        <strong style={{ color: "var(--text-primary)" }}>{edgesCount}</strong> transitions
      </div>
    </div>
  );
}
