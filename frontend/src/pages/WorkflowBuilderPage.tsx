import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import {
  layoutGraph, lintGraph, makeEdge, nodeTypes, type StateNodeData,
} from "../components/flowGraph";

/* Builder-side form + rule models (ride along in node/edge data) */
export interface BuilderFormField {
  name: string;
  type: string;
  required: boolean;
}
export interface BuilderForm {
  name: string;
  required: boolean; // required_to_transition
  fields: BuilderFormField[];
}
export interface BuilderRule {
  condition: any;
  action: any;
  priority: number;
}

const RULE_OPERATORS = [
  "eq", "ne", "gt", "gte", "lt", "lte", "contains", "starts_with", "is_true", "is_false",
] as const;
const FIELD_TYPES = ["text", "textarea", "number", "checkbox", "dropdown", "date"] as const;

function isSimpleRule(r: BuilderRule): boolean {
  return Boolean(
    r.condition && typeof r.condition === "object" &&
    typeof r.condition.field === "string" &&
    RULE_OPERATORS.includes(r.condition.operator)
  );
}

function coerceRuleValue(raw: string): string | number | boolean {
  if (/^-?\d+(\.\d+)?$/.test(raw.trim())) return Number(raw);
  if (raw.trim() === "true") return true;
  if (raw.trim() === "false") return false;
  return raw;
}

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

  // Load the workflow being edited (+ its per-state forms)
  const { data: editWf, isLoading: editLoading } = useQuery({
    queryKey: ["workflow", editId],
    queryFn: async () => (await apiClient.get(`/workflows/${editId}/`)).data,
    enabled: isEdit,
  });
  const { data: editForms } = useQuery({
    queryKey: ["builderForms", editId],
    queryFn: async () => {
      const d = (await apiClient.get(`/forms/?workflow_definition=${editId}`)).data;
      return d.results ?? d;
    },
    enabled: isEdit,
  });

  // Live graph lint (mirrors backend dsl.lint_bundle)
  const lint = useMemo(() => lintGraph(nodes, edges), [nodes, edges]);

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

  const duplicateSelected = () => {
    if (!selectedNode) return;
    takeSnapshot();
    const d = selectedNode.data as StateNodeData;
    const id = String(nodeIdRef.current++);
    setNodes((ns) => [...ns, {
      ...selectedNode,
      id,
      position: { x: selectedNode.position.x + 30, y: selectedNode.position.y + 40 },
      selected: false,
      data: {
        ...d,
        label: `${d.label} (copy)`,
        isInitial: false, // only one start state allowed
        serverId: undefined, // a copy is a new state
      },
    }]);
    setSelectedNodeId(id);
  };

  const nudgeSelected = (dx: number, dy: number) => {
    if (!selectedNodeId) return;
    setNodes((ns) =>
      ns.map((n) =>
        n.id === selectedNodeId
          ? { ...n, position: { x: n.position.x + dx, y: n.position.y + dy } }
          : n
      )
    );
  };

  const autoLayout = () => {
    takeSnapshot();
    setNodes((ns) => layoutGraph(ns, edges));
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

  const updateEdgeRules = (rules: BuilderRule[]) => {
    if (!selectedEdgeId) return;
    setEdges((es) =>
      es.map((e) =>
        e.id === selectedEdgeId ? { ...e, data: { ...e.data, rules } } : e
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
      const d = n.data as StateNodeData & { form?: BuilderForm | null };
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
        // Only mention 'form' when known — absent means "leave alone" on compose
        ...(d.form !== undefined
          ? {
              form: d.form
                ? {
                    name: d.form.name.trim() || `${d.label.trim()} Form`,
                    schema: {
                      required_to_transition: d.form.required,
                      fields: d.form.fields.filter((f) => f.name.trim()),
                    },
                  }
                : null,
            }
          : {}),
      };
    });

    const transPayloads = edges.map((e) => {
      const fromNode = nodes.find((n) => n.id === e.source);
      const toNode   = nodes.find((n) => n.id === e.target);
      const serverId = (e.data as any)?.serverId;
      const rules: BuilderRule[] | undefined = (e.data as any)?.rules;
      return {
        ...(serverId ? { id: serverId } : {}),
        name: ((e.data as any)?.name || e.label || "Transition") as string,
        from_state: ((fromNode?.data as StateNodeData)?.label ?? "").trim(),
        to_state:   ((toNode?.data as StateNodeData)?.label ?? "").trim(),
        requires_approval: Boolean((e.data as any)?.requiresApproval),
        ...(rules !== undefined
          ? { rules: rules.map((r) => ({ condition: r.condition, action: r.action, priority: r.priority })) }
          : {}),
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
    if (!isEdit || !editWf || !editForms || hydratedRef.current) return;

    setWfName(editWf.name ?? "");
    setWfDesc(editWf.description ?? "");
    setWfPrefix(editWf.reference_prefix ?? "WFF");
    setWfActive(Boolean(editWf.is_active));

    const states = [...(editWf.states ?? [])].sort(
      (a: any, b: any) => a.position_order - b.position_order
    );
    const hasPositions = states.some(
      (s: any) => s.canvas_position && typeof s.canvas_position.x === "number"
    );
    // Latest form version per state (compose edits it in place / versions up)
    const formByState = new Map<string, any>();
    for (const f of editForms as any[]) {
      const cur = formByState.get(f.state);
      if (!cur || f.version > cur.version) formByState.set(f.state, f);
    }

    let hydratedNodes: Node[] = states.map((s: any, i: number) => {
      const f = formByState.get(s.id);
      const form: BuilderForm | null = f
        ? {
            name: f.name,
            required: Boolean(f.schema?.required_to_transition),
            fields: (f.schema?.fields ?? []).map((ff: any) => ({
              name: ff.name ?? "",
              type: ff.type ?? "text",
              required: Boolean(ff.required),
            })),
          }
        : null;
      return {
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
          form,
        } as StateNodeData & { form: BuilderForm | null },
      };
    });
    const rulesByTransition = new Map<string, BuilderRule[]>();
    for (const r of editWf.rules ?? []) {
      if (!r.transition) continue; // workflow-scoped rules aren't edge-editable
      const list = rulesByTransition.get(String(r.transition)) ?? [];
      list.push({ condition: r.condition, action: r.action, priority: r.priority });
      rulesByTransition.set(String(r.transition), list);
    }
    const hydratedEdges: Edge[] = (editWf.transitions ?? []).map((t: any) => {
      const e = makeEdge(
        String(t.id), String(t.from_state), String(t.to_state),
        t.name, Boolean(t.requires_approval), String(t.id),
      );
      (e.data as any).rules = rulesByTransition.get(String(t.id)) ?? [];
      return e;
    });
    // Workflows never opened in the builder have no stored positions —
    // rank-layout them instead of the naive grid.
    if (!hasPositions) {
      hydratedNodes = layoutGraph(hydratedNodes, hydratedEdges);
    }
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
  }, [isEdit, editWf, editForms, setNodes, setEdges]);

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
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") {
        e.preventDefault();
        duplicateSelected();
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        deleteSelected();
      } else if (e.key.startsWith("Arrow") && selectedNodeId) {
        e.preventDefault();
        const step = e.shiftKey ? 24 : 8;
        if (e.key === "ArrowLeft") nudgeSelected(-step, 0);
        else if (e.key === "ArrowRight") nudgeSelected(step, 0);
        else if (e.key === "ArrowUp") nudgeSelected(0, -step);
        else if (e.key === "ArrowDown") nudgeSelected(0, step);
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

        {!isEdit && (
          <Link
            to="/workflows/new/text"
            className="btn-secondary btn-sm hint"
            style={{ textDecoration: "none" }}
            data-hint="Write this workflow as YAML instead"
          >
            YAML editor
          </Link>
        )}
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
        <button
          className="btn-secondary btn-sm hint"
          onClick={autoLayout}
          data-hint="Arrange states left-to-right from the start state"
        >
          Auto-layout
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
            snapToGrid
            snapGrid={[12, 12]}
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
              onUpdateRules={updateEdgeRules}
            />
          ) : (
            <CanvasHelp nodesCount={nodes.length} edgesCount={edges.length} />
          )}

          {/* Live lint warnings */}
          {lint.length > 0 && (
            <div style={{
              borderTop: "1px solid var(--border)", paddingTop: 12,
              display: "flex", flexDirection: "column", gap: 6,
            }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "#d29922" }}>
                ⚠ {lint.length} warning{lint.length > 1 ? "s" : ""}
              </div>
              {lint.map((w, i) => (
                <div key={i} style={{ fontSize: "0.78rem", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                  {w}
                </div>
              ))}
            </div>
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
  const form = (node.data as any).form as BuilderForm | null | undefined;
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

      <div className="divider" />
      <FormSection form={form} onChange={(f) => onUpdate("form" as any, f)} stateLabel={d.label} />

      <div style={{ marginTop: 16, padding: "10px 12px", background: "var(--bg-elevated)", borderRadius: 8, fontSize: "0.78rem", color: "var(--text-secondary)" }}>
        Drag from the <strong style={{ color: "var(--accent-light)" }}>right handle →</strong> to another state's left handle to create a transition.
      </div>
    </div>
  );
}

/* ─── Per-state form editor ─── */
function FormSection({ form, onChange, stateLabel }: {
  form: BuilderForm | null | undefined;
  onChange: (f: BuilderForm | null) => void;
  stateLabel: string;
}) {
  const attach = () =>
    onChange({ name: `${stateLabel} Form`, required: true, fields: [{ name: "", type: "text", required: false }] });

  const patch = (p: Partial<BuilderForm>) => form && onChange({ ...form, ...p });
  const patchField = (i: number, p: Partial<BuilderFormField>) =>
    form && patch({ fields: form.fields.map((f, j) => (j === i ? { ...f, ...p } : f)) });

  return (
    <div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", color: "var(--text-primary)", fontSize: "0.85rem", marginBottom: 8 }}>
        <input
          type="checkbox"
          checked={Boolean(form)}
          onChange={(e) => (e.target.checked ? attach() : onChange(null))}
          style={{ width: "auto" }}
        />
        Form on this state
      </label>

      {form && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <input
            placeholder="Form name"
            value={form.name}
            onChange={(e) => patch({ name: e.target.value })}
            style={{ fontSize: "0.82rem", padding: "5px 8px" }}
          />
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", color: "var(--text-secondary)", fontSize: "0.8rem" }}>
            <input
              type="checkbox"
              checked={form.required}
              onChange={(e) => patch({ required: e.target.checked })}
              style={{ width: "auto" }}
            />
            Must be completed before transition
          </label>

          {form.fields.map((f, i) => (
            <div key={i} style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <input
                placeholder="field_name"
                value={f.name}
                onChange={(e) => patchField(i, { name: e.target.value })}
                style={{ flex: 1, minWidth: 0, fontSize: "0.78rem", padding: "4px 6px", fontFamily: "monospace" }}
              />
              <select
                value={f.type}
                onChange={(e) => patchField(i, { type: e.target.value })}
                style={{ width: 84, fontSize: "0.78rem", padding: "4px 4px" }}
              >
                {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <input
                type="checkbox"
                title="Required"
                checked={f.required}
                onChange={(e) => patchField(i, { required: e.target.checked })}
                style={{ width: "auto" }}
              />
              <button
                className="btn-secondary btn-sm"
                style={{ padding: "2px 7px", color: "var(--danger, #f85149)" }}
                onClick={() => patch({ fields: form.fields.filter((_, j) => j !== i) })}
              >✕</button>
            </div>
          ))}
          <button
            className="btn-secondary btn-sm"
            onClick={() => patch({ fields: [...form.fields, { name: "", type: "text", required: false }] })}
          >
            + Add field
          </button>
        </div>
      )}
    </div>
  );
}

/* ─── Edge properties panel ─── */
function EdgeEditor({ edge, onUpdateName, onToggleApproval, onUpdateRules }: {
  edge: Edge;
  onUpdateName: (n: string) => void;
  onToggleApproval: () => void;
  onUpdateRules: (rules: BuilderRule[]) => void;
}) {
  const requiresApproval = Boolean((edge.data as any)?.requiresApproval);
  const rules: BuilderRule[] = (edge.data as any)?.rules ?? [];

  const patchRule = (i: number, p: Partial<BuilderRule>) =>
    onUpdateRules(rules.map((r, j) => (j === i ? { ...r, ...p } : r)));
  const patchCondition = (i: number, p: Record<string, unknown>) =>
    patchRule(i, { condition: { ...rules[i].condition, ...p } });

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

      <div className="divider" />

      {/* Rules */}
      <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-secondary)", marginBottom: 8 }}>
        Rules ({rules.length})
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {rules.map((r, i) => (
          <div key={i} style={{ padding: "8px 10px", background: "var(--bg-elevated)", borderRadius: 8, display: "flex", flexDirection: "column", gap: 6 }}>
            {isSimpleRule(r) ? (
              <>
                <div style={{ display: "flex", gap: 4 }}>
                  <input
                    placeholder="field"
                    value={r.condition.field}
                    onChange={(e) => patchCondition(i, { field: e.target.value })}
                    style={{ flex: 1, minWidth: 0, fontSize: "0.78rem", padding: "4px 6px", fontFamily: "monospace" }}
                  />
                  <select
                    value={r.condition.operator}
                    onChange={(e) => patchCondition(i, { operator: e.target.value })}
                    style={{ width: 96, fontSize: "0.78rem", padding: "4px 4px" }}
                  >
                    {RULE_OPERATORS.map((op) => <option key={op} value={op}>{op}</option>)}
                  </select>
                </div>
                {!["is_true", "is_false"].includes(r.condition.operator) && (
                  <input
                    placeholder="value"
                    value={String(r.condition.value ?? "")}
                    onChange={(e) => patchCondition(i, { value: coerceRuleValue(e.target.value) })}
                    style={{ fontSize: "0.78rem", padding: "4px 6px", fontFamily: "monospace" }}
                  />
                )}
                <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", color: "var(--text-secondary)", fontSize: "0.78rem" }}>
                  <input
                    type="checkbox"
                    checked={Boolean(r.action?.block_transition)}
                    onChange={(e) => patchRule(i, { action: { ...r.action, block_transition: e.target.checked } })}
                    style={{ width: "auto" }}
                  />
                  Block this transition when matched
                </label>
              </>
            ) : (
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontFamily: "monospace", wordBreak: "break-all" }}>
                (advanced rule — edit via YAML) {JSON.stringify(r.condition).slice(0, 80)}
              </div>
            )}
            <button
              className="btn-secondary btn-sm"
              style={{ alignSelf: "flex-end", padding: "2px 8px", color: "var(--danger, #f85149)" }}
              onClick={() => onUpdateRules(rules.filter((_, j) => j !== i))}
            >
              Remove
            </button>
          </div>
        ))}
        <button
          className="btn-secondary btn-sm"
          onClick={() =>
            onUpdateRules([...rules, {
              condition: { field: "", operator: "eq", value: "" },
              action: { block_transition: true },
              priority: 100,
            }])
          }
        >
          + Add rule
        </button>
      </div>

      <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--bg-elevated)", borderRadius: 8, fontSize: "0.78rem", color: "var(--text-secondary)" }}>
        Rules run when this transition fires; a matched blocking rule stops it.
        Press <strong style={{ color: "var(--text-primary)" }}>Delete</strong> on the canvas to remove this transition.
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
