import { useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import {
  WorkflowInstance, Transition, AuditEntry, UserProfile,
  InstanceRelationship, InstanceSearchResult, CurrentForm, FormField,
} from "../types/api";
import StateGraph from "../components/StateGraph";
import Hint from "../components/Hint";
import ChildrenPanel from "../components/ChildrenPanel";
import { formatDateTime } from "../hooks/useWorkspace";

/* ─── Role capability helpers ─── */
const CAN_DO_ANYTHING = new Set(["platform_admin", "workflow_designer"]);
const CAN_APPROVE     = new Set(["platform_admin", "workflow_designer", "approver"]);
const CAN_TRANSITION  = new Set(["platform_admin", "workflow_designer", "approver", "participant"]);
const CAN_COMMENT     = new Set(["platform_admin", "workflow_designer", "approver", "participant", "viewer"]);

function userCan(roles: string[], cap: "transition" | "approve" | "comment" | "anything") {
  const set = cap === "anything" ? CAN_DO_ANYTHING : cap === "approve" ? CAN_APPROVE : cap === "comment" ? CAN_COMMENT : CAN_TRANSITION;
  return roles.some(r => set.has(r));
}

function canFireTransition(roles: string[], requiresApproval: boolean) {
  if (requiresApproval) return userCan(roles, "approve");
  return userCan(roles, "transition");
}

export default function InstanceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const [blockReason, setBlockReason] = useState<string | null>(null);
  const [successMsg, setSuccessMsg]   = useState<string | null>(null);
  const [commentText, setCommentText] = useState("");
  const [commentErr, setCommentErr]   = useState<string | null>(null);
  const [commentOk, setCommentOk]     = useState(false);

  // Metadata editor state
  const [editingMeta, setEditingMeta]   = useState(false);
  const [metaRows, setMetaRows]         = useState<Array<{ key: string; value: string }>>([]);
  const [metaSaveErr, setMetaSaveErr]   = useState<string | null>(null);
  const [metaSaveOk, setMetaSaveOk]     = useState(false);

  // Relationship link form state
  const [linkQuery, setLinkQuery]       = useState("");
  const [linkResults, setLinkResults]   = useState<InstanceSearchResult[]>([]);
  const [linkTarget, setLinkTarget]     = useState<InstanceSearchResult | null>(null);
  const [linkType, setLinkType]         = useState("");
  const [linkNotes, setLinkNotes]       = useState("");
  const [linkErr, setLinkErr]           = useState<string | null>(null);
  const [showLinkForm, setShowLinkForm] = useState(false);

  /* ── Queries ── */
  const { data: me } = useQuery<UserProfile>({
    queryKey: ["me"],
    queryFn: async () => (await apiClient.get("/auth/me/")).data,
    staleTime: 60_000,
  });

  const { data: instance, isLoading } = useQuery<WorkflowInstance>({
    queryKey: ["instance", id],
    queryFn: async () => (await apiClient.get(`/instances/${id}/`)).data,
    enabled: Boolean(id),
  });

  const { data: workflow } = useQuery({
    queryKey: ["workflow", instance?.workflow_definition],
    queryFn: async () => (await apiClient.get(`/workflows/${instance!.workflow_definition}/`)).data,
    enabled: Boolean(instance?.workflow_definition),
  });

  const { data: auditData } = useQuery<{ results: AuditEntry[] }>({
    queryKey: ["audit-trail", id],
    queryFn: async () => (await apiClient.get(`/audit/${id}/`)).data,
    enabled: Boolean(id),
  });

  /* ── Derived values ── */
  const myRoles: string[] = me?.roles ?? [];
  const isCompleted = Boolean(instance?.completed_at);

  const allTransitions: Transition[] = (workflow?.transitions ?? []).filter(
    (t: Transition) => t.from_state === instance?.current_state
  );

  // Split into what the user can actually fire vs what's blocked by role
  const fireableTransitions = allTransitions.filter(t => canFireTransition(myRoles, t.requires_approval));
  const blockedByRole       = allTransitions.filter(t => !canFireTransition(myRoles, t.requires_approval));

  const visitedStateNames: string[] = [
    ...(auditData?.results ?? []).filter(e => e.to_state).map(e => e.to_state as string),
  ];

  /* ── Mutations ── */
  const transitionMutation = useMutation({
    mutationFn: async (transition_id: string) =>
      (await apiClient.post(`/instances/${id}/transition/`, { transition_id })).data,
    onSuccess: (data) => {
      setBlockReason(null);
      setSuccessMsg(`Moved to "${data.current_state_name}"`);
      qc.invalidateQueries({ queryKey: ["instance", id] });
      qc.invalidateQueries({ queryKey: ["audit-trail", id] });
      qc.invalidateQueries({ queryKey: ["instances"] });
      setTimeout(() => setSuccessMsg(null), 3000);
    },
    onError: (err: any) => {
      setSuccessMsg(null);
      setBlockReason(err?.response?.data?.detail ?? "Transition failed");
    },
  });

  const metaMutation = useMutation({
    mutationFn: async (metadata_json: Record<string, unknown>) => {
      const headers: Record<string, string> = {};
      // Optimistic locking: include If-Match header if we have the instance
      if (instance?.updated_at) {
        headers["If-Match"] = instance.updated_at;
      }
      return (await apiClient.patch(`/instances/${id}/metadata/`, { metadata_json }, { headers })).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instance", id] });
      qc.invalidateQueries({ queryKey: ["audit-trail", id] });
      setEditingMeta(false);
      setMetaSaveErr(null);
      setMetaSaveOk(true);
      setTimeout(() => setMetaSaveOk(false), 3000);
    },
    onError: (err: any) => {
      if (err?.response?.status === 409) {
        // Conflict: show the server's current state for merge
        const serverInstance = err?.response?.data?.current_instance;
        if (serverInstance) {
          setMetaSaveErr(
            `Conflict: This instance was modified by another user. ` +
            `Current server values: ${JSON.stringify(serverInstance.metadata_json || {})}. ` +
            `Please refresh to see the latest changes.`
          );
        } else {
          setMetaSaveErr("Conflict: Instance was modified by another user. Please refresh.");
        }
      } else {
        setMetaSaveErr(err?.response?.data?.detail ?? "Failed to save metadata");
      }
    },
  });

  const commentMutation = useMutation({
    mutationFn: async (body: string) =>
      (await apiClient.post(`/instances/${id}/comment/`, { body })).data,
    onSuccess: () => {
      setCommentText("");
      setCommentErr(null);
      setCommentOk(true);
      qc.invalidateQueries({ queryKey: ["audit-trail", id] });
      setTimeout(() => setCommentOk(false), 3000);
    },
    onError: (err: any) =>
      setCommentErr(err?.response?.data?.detail ?? "Failed to post comment"),
  });

  const formMutation = useMutation({
    mutationFn: async (payload: { form_definition: string; data: Record<string, unknown> }) =>
      (await apiClient.post("/submissions/", { workflow_instance: id, ...payload })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instance", id] });
      qc.invalidateQueries({ queryKey: ["audit-trail", id] });
      setBlockReason(null);
    },
  });

  const linkMutation = useMutation({
    mutationFn: async (payload: { to_instance: string; rel_type: string; notes: string }) =>
      (await apiClient.post(`/instances/${id}/link/`, payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instance", id] });
      qc.invalidateQueries({ queryKey: ["audit-trail", id] });
      setLinkTarget(null); setLinkQuery(""); setLinkResults([]);
      setLinkType(""); setLinkNotes(""); setLinkErr(null);
      setShowLinkForm(false);
    },
    onError: (err: any) => setLinkErr(err?.response?.data?.detail ?? "Failed to create link"),
  });

  const unlinkMutation = useMutation({
    mutationFn: async (relId: string) =>
      apiClient.delete(`/instances/${id}/link/${relId}/`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instance", id] });
      qc.invalidateQueries({ queryKey: ["audit-trail", id] });
    },
  });

  const searchInstances = useCallback(async (q: string) => {
    setLinkQuery(q);
    if (q.length < 2) { setLinkResults([]); return; }
    const res = await apiClient.get(`/instances/search/?q=${encodeURIComponent(q)}`);
    setLinkResults((res.data as InstanceSearchResult[]).filter(r => r.id !== id));
  }, [id]);

  // Start editing: populate rows from current metadata
  const startEdit = () => {
    const entries = Object.entries(instance?.metadata_json ?? {});
    setMetaRows(entries.length ? entries.map(([k, v]) => ({ key: k, value: String(v) })) : [{ key: "", value: "" }]);
    setMetaSaveErr(null);
    setEditingMeta(true);
  };

  // Coerce string → number | boolean | string
  const coerce = (v: string): unknown => {
    if (v === "true")  return true;
    if (v === "false") return false;
    const n = Number(v);
    return v !== "" && !isNaN(n) ? n : v;
  };

  const saveMeta = () => {
    const errs = metaRows.filter(r => !r.key.trim());
    if (errs.length) { setMetaSaveErr("All fields must have a key."); return; }
    const obj: Record<string, unknown> = {};
    for (const { key, value } of metaRows) {
      if (key.trim()) obj[key.trim()] = coerce(value);
    }
    metaMutation.mutate(obj);
  };

  const submitComment = () => {
    const body = commentText.trim();
    if (!body) { setCommentErr("Comment cannot be empty."); return; }
    setCommentErr(null);
    commentMutation.mutate(body);
  };

  /* ── Loading states ── */
  if (isLoading) {
    return (
      <div>
        <div className="breadcrumb"><Link to="/instances">Instances</Link><span>/</span>Loading…</div>
        <div className="skeleton" style={{ height: 300, borderRadius: 14 }} />
      </div>
    );
  }
  if (!instance) {
    return (
      <div>
        <div className="breadcrumb"><Link to="/instances">Instances</Link><span>/</span>Not found</div>
        <div className="card empty-state"><p>Instance not found.</p></div>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb — includes the parent chain for contained instances */}
      <div className="breadcrumb">
        <Link to="/instances">Instances</Link>
        <span>/</span>
        {instance.parent && instance.parent_reference && (
          <>
            <Link to={`/instances/${instance.parent}`} style={{ fontFamily: "monospace" }}>
              {instance.parent_reference}
            </Link>
            <span>/</span>
          </>
        )}
        <span style={{ color: "var(--text-primary)" }}>{instance.reference_number}</span>
      </div>

      {/* Header */}
      <div className="page-header">
        <div className="page-header-left">
          <h2>{instance.reference_number}</h2>
          <p>{instance.workflow_definition_name}</p>
        </div>
        <div className="flex items-center gap-2">
          {myRoles.map(r => (
            <span key={r} className={`badge badge-role-${r}`} style={{ fontSize: "0.7rem" }}>{r}</span>
          ))}
          <span className={`badge ${isCompleted ? "badge-terminal" : "badge-active"}`}>
            {isCompleted ? "Completed" : "In Progress"}
          </span>
        </div>
      </div>

      {/* State graph */}
      {workflow && (
        <div className="mb-4">
          <StateGraph
            states={workflow.states ?? []}
            transitions={workflow.transitions ?? []}
            currentStateId={instance.current_state}
            visitedStateNames={visitedStateNames}
            isTerminal={isCompleted}
          />
        </div>
      )}

      {/* Alert banners */}
      {blockReason && (
        <div className="alert alert-error">
          <span>⚠</span>
          <div>
            <strong>Transition blocked</strong>
            <div style={{ marginTop: 2 }}>{blockReason}</div>
          </div>
        </div>
      )}
      {successMsg && (
        <div className="alert alert-success"><span>✓</span> {successMsg}</div>
      )}

      <div className="grid grid-2">
        {/* ── Transitions + Comment panel ── */}
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          <div className="card-header">
            <h3>Actions <Hint tip="These buttons move the item to its next stage. A button can be blocked by a rule, a required form, or need a higher role — the error message will say why." below /></h3>
            {!isCompleted && (
              <span className="badge badge-inactive" style={{ fontSize: "0.7rem" }}>
                {instance.current_state_name}
              </span>
            )}
          </div>

          {isCompleted ? (
            <div className="empty-state" style={{ padding: "20px 0" }}>
              <p>Instance complete — no further transitions.</p>
            </div>
          ) : (
            <>
              {/* Fireable transitions */}
              {fireableTransitions.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
                  {fireableTransitions.map((t) => {
                    const toState = (workflow?.states ?? []).find((s: any) => s.id === t.to_state);
                    return (
                      <button
                        key={t.id}
                        className="transition-btn"
                        onClick={() => transitionMutation.mutate(t.id)}
                        disabled={transitionMutation.isPending}
                      >
                        <span className="t-name">{t.display_name || t.name}</span>
                        <span className="t-arrow">
                          {instance.current_state_name} → {toState?.display_name || toState?.name || "…"}
                          {t.requires_approval && (
                            <span className="badge badge-warning" style={{ marginLeft: 6, fontSize: "0.65rem" }}>Approval</span>
                          )}
                        </span>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="empty-state" style={{ padding: "16px 0" }}>
                  <p className="text-sm">
                    {allTransitions.length === 0
                      ? "No transitions from this state."
                      : "Your role doesn't allow any transitions from here."}
                  </p>
                </div>
              )}

              {/* Blocked-by-role transitions (shown grayed out as information) */}
              {blockedByRole.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div className="text-xs text-muted mb-2" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                    Requires higher role
                  </div>
                  {blockedByRole.map((t) => {
                    const toState = (workflow?.states ?? []).find((s: any) => s.id === t.to_state);
                    return (
                      <div key={t.id} style={{
                        padding: "8px 12px", borderRadius: 8, border: "1px solid var(--border)",
                        background: "var(--bg-elevated)", opacity: 0.5, marginBottom: 6,
                        display: "flex", justifyContent: "space-between", alignItems: "center",
                      }}>
                        <span className="text-sm" style={{ fontWeight: 500 }}>{t.display_name || t.name}</span>
                        <span className="text-xs text-muted">
                          → {toState?.name}
                          {t.requires_approval && " · approver only"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {/* ── Comment box ── */}
          <div className="divider" />
          <div>
            <div className="text-xs text-muted mb-2" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Add Comment
            </div>
            {userCan(myRoles, "comment") ? (
              <>
                <textarea
                  value={commentText}
                  onChange={e => setCommentText(e.target.value)}
                  placeholder="Add a note, decision rationale, or escalation reason…"
                  rows={3}
                  style={{
                    width: "100%", resize: "vertical", padding: "8px 10px",
                    background: "var(--bg-elevated)", border: "1px solid var(--border)",
                    borderRadius: 8, color: "var(--text-primary)", fontSize: "0.85rem",
                    lineHeight: 1.5, fontFamily: "inherit", boxSizing: "border-box",
                    outline: "none",
                  }}
                  onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submitComment(); }}
                />
                {commentErr && <div className="alert alert-error" style={{ marginTop: 6 }}>{commentErr}</div>}
                {commentOk  && <div className="alert alert-success" style={{ marginTop: 6 }}>Comment posted.</div>}
                <div className="flex gap-2 items-center" style={{ marginTop: 8 }}>
                  <button
                    className="btn-primary btn-sm"
                    onClick={submitComment}
                    disabled={commentMutation.isPending || !commentText.trim()}
                  >
                    {commentMutation.isPending ? "Posting…" : "Post Comment"}
                  </button>
                  <span className="text-xs text-muted">⌘↵ to submit</span>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted">Comments require at least viewer role.</p>
            )}
          </div>
        </div>

        {/* ── Metadata ── */}
        <div className="card">
          <div className="card-header">
            <h3>Metadata <Hint tip="Extra details stored on this item as name/value pairs. Rules read these values, so editing them can unlock or block the action buttons." below /></h3>
            {!editingMeta && (
              <button className="btn-secondary btn-sm" onClick={startEdit}>Edit</button>
            )}
          </div>

          {editingMeta ? (
            <div>
              {/* Editor rows */}
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 10 }}>
                {metaRows.map((row, i) => (
                  <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr auto", gap: 6, alignItems: "center" }}>
                    <input
                      placeholder="field name"
                      value={row.key}
                      onChange={e => setMetaRows(rows => rows.map((r, j) => j === i ? { ...r, key: e.target.value } : r))}
                      style={{ fontFamily: "monospace", fontSize: "0.82rem", padding: "5px 8px" }}
                    />
                    <input
                      placeholder="value"
                      value={row.value}
                      onChange={e => setMetaRows(rows => rows.map((r, j) => j === i ? { ...r, value: e.target.value } : r))}
                      style={{ fontSize: "0.82rem", padding: "5px 8px" }}
                    />
                    <button
                      className="btn-ghost btn-sm"
                      style={{ color: "var(--danger)", padding: "4px 8px" }}
                      onClick={() => setMetaRows(rows => rows.filter((_, j) => j !== i))}
                    >✕</button>
                  </div>
                ))}
              </div>

              {/* Type hint */}
              <div className="text-xs text-muted mb-3" style={{ lineHeight: 1.5 }}>
                Values are auto-typed: <code>42</code> → number · <code>true</code>/<code>false</code> → boolean · anything else → string
              </div>

              <button
                className="btn-ghost btn-sm"
                style={{ marginBottom: 12, width: "100%", borderStyle: "dashed" }}
                onClick={() => setMetaRows(rows => [...rows, { key: "", value: "" }])}
              >
                + Add field
              </button>

              {metaSaveErr && <div className="alert alert-error mb-2">{metaSaveErr}</div>}

              <div className="flex gap-2">
                <button className="btn-primary btn-sm" onClick={saveMeta} disabled={metaMutation.isPending}>
                  {metaMutation.isPending ? "Saving…" : "Save"}
                </button>
                <button className="btn-secondary btn-sm" onClick={() => { setEditingMeta(false); setMetaSaveErr(null); }}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              {metaSaveOk && <div className="alert alert-success mb-2">Metadata saved.</div>}
              {Object.keys(instance.metadata_json ?? {}).length === 0 ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, padding: "20px 0", color: "var(--text-secondary)" }}>
                  <p className="text-sm">No metadata yet.</p>
                  <button className="btn-primary btn-sm" onClick={startEdit}>+ Add fields</button>
                </div>
              ) : (
                <table className="table">
                  <tbody>
                    {Object.entries(instance.metadata_json ?? {}).map(([k, v]) => (
                      <tr key={k}>
                        <td style={{ color: "var(--text-secondary)", width: "42%", fontFamily: "monospace", fontSize: "0.8rem" }}>{k}</td>
                        <td style={{ fontWeight: 500, wordBreak: "break-word" }}>
                          {typeof v === "boolean"
                            ? <span className={`badge ${v ? "badge-active" : "badge-inactive"}`}>{String(v)}</span>
                            : typeof v === "number"
                            ? <span style={{ fontFamily: "monospace" }}>{v}</span>
                            : String(v)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}

          {instance.completed_at && !editingMeta && (
            <>
              <div className="divider" />
              <div className="text-sm text-muted">Completed {formatDateTime(instance.completed_at)}</div>
            </>
          )}
        </div>
      </div>

      {/* ── State form ── */}
      {instance.current_form && !isCompleted && (
        <StateFormPanel
          form={instance.current_form}
          canSubmit={userCan(myRoles, "transition")}
          isPending={formMutation.isPending}
          onSubmit={(data) =>
            formMutation.mutate({ form_definition: instance.current_form!.id, data })
          }
          submitError={
            (formMutation.error as any)?.response?.data
              ? JSON.stringify((formMutation.error as any).response.data)
              : formMutation.isError ? "Submission failed" : null
          }
        />
      )}

      {/* ── Sub-instances ── */}
      <ChildrenPanel
        instance={instance}
        workflow={workflow}
        canEdit={userCan(myRoles, "transition")}
      />

      {/* ── Relationships ── */}
      <RelationshipsPanel
        instance={instance}
        myRoles={myRoles}
        showLinkForm={showLinkForm}
        setShowLinkForm={setShowLinkForm}
        linkQuery={linkQuery}
        linkResults={linkResults}
        linkTarget={linkTarget}
        setLinkTarget={setLinkTarget}
        linkType={linkType}
        setLinkType={setLinkType}
        linkNotes={linkNotes}
        setLinkNotes={setLinkNotes}
        linkErr={linkErr}
        onSearch={searchInstances}
        onLink={() => {
          if (!linkTarget) { setLinkErr("Select a target instance."); return; }
          if (!linkType.trim()) { setLinkErr("Relationship type is required."); return; }
          linkMutation.mutate({ to_instance: linkTarget.id, rel_type: linkType.trim(), notes: linkNotes });
        }}
        onUnlink={(relId) => unlinkMutation.mutate(relId)}
        isPending={linkMutation.isPending}
      />

      {/* ── Audit trail / comments ── */}
      <div className="card mt-4">
        <div className="card-header">
          <h3>Timeline <Hint tip="A permanent history of everything that happened to this item — every stage change, comment, and edit, with who did it and when. It cannot be altered." /></h3>
          <span className="badge badge-inactive">{(auditData?.results ?? []).length} events</span>
        </div>
        {(auditData?.results ?? []).length === 0 ? (
          <p className="text-muted text-sm">No events yet.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            {[...(auditData?.results ?? [])].reverse().map((entry: AuditEntry, i) => {
              const isComment = entry.action_type === "comment";
              const body = isComment ? (entry.payload?.body as string) : null;
              return (
                <div key={entry.id} style={{
                  display: "flex", gap: 12, padding: "12px 0",
                  borderBottom: i < (auditData?.results?.length ?? 0) - 1 ? "1px solid var(--border)" : "none",
                }}>
                  {/* Timeline dot */}
                  <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 2 }}>
                    <div style={{
                      width: 28, height: 28, borderRadius: "50%",
                      background: isComment ? "rgba(99,102,241,0.12)" : "var(--bg-elevated)",
                      border: `2px solid ${isComment ? "#6366f1" : "var(--border)"}`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 12,
                    }}>
                      {isComment ? "💬" : eventIcon(entry.action_type)}
                    </div>
                  </div>

                  {/* Content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="flex items-center gap-2" style={{ marginBottom: 4, flexWrap: "wrap" }}>
                      <span className={`badge ${auditBadgeClass(entry.action_type)}`} style={{ fontSize: "0.7rem" }}>
                        {entry.action_type.replace(/_/g, " ")}
                      </span>
                      {entry.from_state && entry.to_state && (
                        <span className="text-xs text-muted">
                          {entry.from_state} → {entry.to_state}
                        </span>
                      )}
                      {entry.from_state && !entry.to_state && !isComment && (
                        <span className="text-xs text-muted">{entry.from_state}</span>
                      )}
                    </div>

                    {/* Comment body */}
                    {body && (
                      <div style={{
                        background: "var(--bg-elevated)", borderRadius: 8, padding: "8px 12px",
                        marginBottom: 6, fontSize: "0.85rem", lineHeight: 1.6,
                        borderLeft: "3px solid rgba(99,102,241,0.5)",
                        color: "var(--text-primary)",
                      }}>
                        {body}
                      </div>
                    )}

                    <div className="flex gap-3 text-xs text-muted" style={{ flexWrap: "wrap" }}>
                      <span>{entry.actor_email || "System"}</span>
                      <span>{formatDateTime(entry.created_at)}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function auditBadgeClass(action: string) {
  if (action === "comment")                    return "badge-initial";
  if (action === "metadata_updated")           return "badge-inactive";
  if (action === "sla_breached")               return "badge-warning";
  if (action.includes("relationship"))         return "badge-role-workflow_designer";
  if (action.includes("transition"))           return "badge-active";
  if (action.includes("created"))              return "badge-active";
  if (action.includes("rule"))                 return "badge-warning";
  if (action.includes("task"))                 return "badge-pending";
  return "badge-inactive";
}

function eventIcon(action: string) {
  if (action === "metadata_updated")           return "✎";
  if (action.includes("form"))                 return "📋";
  if (action === "sla_breached")               return "⏱";
  if (action.includes("relationship_added"))   return "⇌";
  if (action.includes("relationship_removed")) return "✂";
  if (action.includes("transition"))           return "→";
  if (action.includes("created"))              return "✦";
  if (action.includes("task"))                 return "☑";
  if (action.includes("rule"))                 return "⚡";
  return "·";
}

/* ── State form panel component ────────────────────────────────────────── */

function StateFormPanel({
  form, canSubmit, isPending, onSubmit, submitError,
}: {
  form: CurrentForm;
  canSubmit: boolean;
  isPending: boolean;
  onSubmit: (data: Record<string, unknown>) => void;
  submitError: string | null;
}) {
  const fields = form.schema.fields ?? [];
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [localErrs, setLocalErrs] = useState<Record<string, string>>({});

  const setValue = (name: string, v: unknown) =>
    setValues(prev => ({ ...prev, [name]: v }));

  const submit = () => {
    const errs: Record<string, string> = {};
    for (const f of fields) {
      const v = values[f.name];
      if (f.required && (v === undefined || v === null || v === "")) {
        errs[f.name] = "Required";
      }
      if (v !== undefined && v !== "" && (f.type === "number" || f.type === "currency")) {
        const n = Number(v);
        if (Number.isNaN(n)) errs[f.name] = "Must be a number";
        else if (f.min !== undefined && n < f.min) errs[f.name] = `Must be ≥ ${f.min}`;
        else if (f.max !== undefined && n > f.max) errs[f.name] = `Must be ≤ ${f.max}`;
      }
    }
    setLocalErrs(errs);
    if (Object.keys(errs).length > 0) return;

    const data: Record<string, unknown> = {};
    for (const f of fields) {
      let v = values[f.name];
      if (v === undefined || v === "") {
        if (f.type === "checkbox" || f.type === "toggle") v = false;
        else continue;
      }
      if (f.type === "number" || f.type === "currency") v = Number(v);
      data[f.name] = v;
    }
    onSubmit(data);
  };

  if (form.submitted) {
    return (
      <div className="card mt-4">
        <div className="card-header">
          <h3>{form.name}</h3>
          <span className="badge badge-active">✓ Submitted</span>
        </div>
        <table className="table">
          <tbody>
            {Object.entries(form.submission_data ?? {}).map(([k, v]) => {
              const field = fields.find(f => f.name === k);
              return (
                <tr key={k}>
                  <td style={{ color: "var(--text-secondary)", width: "42%", fontSize: "0.85rem" }}>
                    {field?.label || k}
                  </td>
                  <td style={{ fontWeight: 500 }}>
                    {typeof v === "boolean"
                      ? <span className={`badge ${v ? "badge-active" : "badge-inactive"}`}>{String(v)}</span>
                      : String(v)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {form.submitted_at && (
          <div className="text-xs text-muted" style={{ marginTop: 8 }}>
            Submitted {formatDateTime(form.submitted_at)}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="card mt-4">
      <div className="card-header">
        <h3>{form.name}</h3>
        {form.required_to_transition && (
          <span className="badge badge-warning" style={{ fontSize: "0.7rem" }}>
            Required before transition
          </span>
        )}
      </div>

      {!canSubmit ? (
        <p className="text-sm text-muted">Submitting this form requires at least participant role.</p>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
            {fields.map(f => (
              <FormFieldInput
                key={f.name}
                field={f}
                value={values[f.name]}
                error={localErrs[f.name]}
                onChange={v => setValue(f.name, v)}
              />
            ))}
          </div>

          {submitError && <div className="alert alert-error mb-2">{submitError}</div>}

          <button className="btn-primary btn-sm" onClick={submit} disabled={isPending}>
            {isPending ? "Submitting…" : `Submit ${form.name}`}
          </button>
        </>
      )}
    </div>
  );
}

function FormFieldInput({
  field, value, error, onChange,
}: {
  field: FormField;
  value: unknown;
  error?: string;
  onChange: (v: unknown) => void;
}) {
  const label = (
    <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, marginBottom: 4, color: "var(--text-secondary)" }}>
      {field.label || field.name}
      {field.required && <span style={{ color: "var(--danger)", marginLeft: 3 }}>*</span>}
    </label>
  );
  const errEl = error && (
    <div className="text-xs" style={{ color: "var(--danger)", marginTop: 3 }}>{error}</div>
  );
  const inputStyle = {
    width: "100%", padding: "7px 10px", background: "var(--bg-elevated)",
    border: `1px solid ${error ? "var(--danger)" : "var(--border)"}`,
    borderRadius: 8, color: "var(--text-primary)", fontSize: "0.85rem",
    fontFamily: "inherit", boxSizing: "border-box" as const, outline: "none",
  };

  if (field.type === "checkbox" || field.type === "toggle") {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, paddingTop: 18 }}>
        <input
          type="checkbox"
          id={`ff-${field.name}`}
          checked={Boolean(value)}
          onChange={e => onChange(e.target.checked)}
          style={{ width: 16, height: 16, accentColor: "#6366f1" }}
        />
        <label htmlFor={`ff-${field.name}`} style={{ fontSize: "0.85rem", cursor: "pointer" }}>
          {field.label || field.name}
          {field.required && <span style={{ color: "var(--danger)", marginLeft: 3 }}>*</span>}
        </label>
        {errEl}
      </div>
    );
  }

  if (field.type === "textarea") {
    return (
      <div style={{ gridColumn: "1 / -1" }}>
        {label}
        <textarea
          rows={3}
          value={(value as string) ?? ""}
          onChange={e => onChange(e.target.value)}
          style={{ ...inputStyle, resize: "vertical" }}
        />
        {errEl}
      </div>
    );
  }

  if (field.type === "dropdown" && field.options?.length) {
    return (
      <div>
        {label}
        <select
          value={(value as string) ?? ""}
          onChange={e => onChange(e.target.value)}
          style={inputStyle}
        >
          <option value="">Select…</option>
          {field.options.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
        {errEl}
      </div>
    );
  }

  return (
    <div>
      {label}
      <input
        type={field.type === "number" || field.type === "currency" ? "number"
          : field.type === "date" ? "date"
          : field.type === "datetime" ? "datetime-local"
          : "text"}
        value={(value as string | number) ?? ""}
        onChange={e => onChange(e.target.value)}
        style={inputStyle}
      />
      {errEl}
    </div>
  );
}

/* ── Relationships panel component ─────────────────────────────────────── */

interface RelPanelProps {
  instance: WorkflowInstance;
  myRoles: string[];
  showLinkForm: boolean;
  setShowLinkForm: (v: boolean) => void;
  linkQuery: string;
  linkResults: InstanceSearchResult[];
  linkTarget: InstanceSearchResult | null;
  setLinkTarget: (v: InstanceSearchResult | null) => void;
  linkType: string;
  setLinkType: (v: string) => void;
  linkNotes: string;
  setLinkNotes: (v: string) => void;
  linkErr: string | null;
  onSearch: (q: string) => void;
  onLink: () => void;
  onUnlink: (relId: string) => void;
  isPending: boolean;
}

const CAN_LINK = new Set(["platform_admin", "workflow_designer", "approver", "participant"]);

function RelationshipsPanel({
  instance, myRoles, showLinkForm, setShowLinkForm,
  linkQuery, linkResults, linkTarget, setLinkTarget,
  linkType, setLinkType, linkNotes, setLinkNotes,
  linkErr, onSearch, onLink, onUnlink, isPending,
}: RelPanelProps) {
  const rels: InstanceRelationship[] = instance.relationships ?? [];
  const canLink = myRoles.some(r => CAN_LINK.has(r));

  return (
    <div className="card mt-4">
      <div className="card-header">
        <h3>Relationships <Hint tip="Links between this item and related items in other workflows — for example a bug found during a test run. Links are informational connections; they do not move anything." /></h3>
        <div className="flex gap-2 items-center">
          <span className="badge badge-inactive">{rels.length}</span>
          {canLink && !instance.completed_at && (
            <button
              className={showLinkForm ? "btn-secondary btn-sm" : "btn-primary btn-sm"}
              onClick={() => setShowLinkForm(!showLinkForm)}
            >
              {showLinkForm ? "Cancel" : "+ Link instance"}
            </button>
          )}
        </div>
      </div>

      {/* ── Link form ── */}
      {showLinkForm && (
        <div style={{
          background: "var(--bg-elevated)", border: "1px solid var(--border)",
          borderRadius: 10, padding: 16, marginBottom: 16,
        }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
            {/* Instance search */}
            <div className="form-group" style={{ marginBottom: 0, position: "relative" }}>
              <label>Target instance</label>
              {linkTarget ? (
                <div style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "6px 10px", background: "rgba(99,102,241,0.08)",
                  border: "1px solid rgba(99,102,241,0.3)", borderRadius: 6,
                }}>
                  <span style={{ fontFamily: "monospace", fontSize: "0.82rem", fontWeight: 600, color: "var(--accent-light)" }}>
                    {linkTarget.reference_number}
                  </span>
                  <span className="text-xs text-muted">{linkTarget.workflow_name} · {linkTarget.current_state}</span>
                  <button
                    onClick={() => setLinkTarget(null)}
                    style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 12 }}
                  >✕</button>
                </div>
              ) : (
                <>
                  <input
                    placeholder="Search by reference or workflow name…"
                    value={linkQuery}
                    onChange={e => onSearch(e.target.value)}
                    autoComplete="off"
                  />
                  {linkResults.length > 0 && (
                    <div style={{
                      position: "absolute", top: "100%", left: 0, right: 0, zIndex: 20,
                      background: "var(--bg-secondary)", border: "1px solid var(--border)",
                      borderRadius: 8, overflow: "hidden", boxShadow: "0 8px 24px rgba(0,0,0,.4)",
                      marginTop: 2,
                    }}>
                      {linkResults.map(r => (
                        <button
                          key={r.id}
                          onClick={() => { setLinkTarget(r); }}
                          style={{
                            width: "100%", display: "flex", alignItems: "center", gap: 10,
                            padding: "8px 12px", background: "none", border: "none",
                            borderBottom: "1px solid var(--border)", cursor: "pointer", textAlign: "left",
                          }}
                          onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,0.04)")}
                          onMouseLeave={e => (e.currentTarget.style.background = "none")}
                        >
                          <span style={{ fontFamily: "monospace", fontSize: "0.82rem", fontWeight: 600, color: "var(--accent-light)", minWidth: 100 }}>
                            {r.reference_number}
                          </span>
                          <span className="text-xs text-muted">{r.workflow_name}</span>
                          <span className={`badge ${r.completed ? "badge-terminal" : "badge-active"}`} style={{ marginLeft: "auto", fontSize: "0.65rem" }}>
                            {r.current_state}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Relationship type */}
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>Relationship type</label>
              <input
                placeholder="e.g. reported_in, blocks, part_of, duplicate_of"
                value={linkType}
                onChange={e => setLinkType(e.target.value)}
                style={{ fontFamily: "monospace" }}
              />
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: 10 }}>
            <label>Notes <span className="text-muted">(optional)</span></label>
            <input
              placeholder="Context for this link…"
              value={linkNotes}
              onChange={e => setLinkNotes(e.target.value)}
            />
          </div>

          {linkErr && <div className="alert alert-error mb-2">{linkErr}</div>}

          <button className="btn-primary btn-sm" onClick={onLink} disabled={isPending}>
            {isPending ? "Linking…" : "Create link"}
          </button>
        </div>
      )}

      {/* ── Relationship list ── */}
      {rels.length === 0 ? (
        <div className="empty-state" style={{ padding: "20px 0" }}>
          <p>No linked instances yet.</p>
          {canLink && !instance.completed_at && (
            <p className="text-xs" style={{ marginTop: 6 }}>
              Link this instance to related Test Runs, Bug Reports, Releases, or any other instance.
            </p>
          )}
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Direction</th>
              <th>Reference</th>
              <th>Workflow</th>
              <th>State</th>
              <th>Type</th>
              {canLink && <th style={{ width: 48 }}></th>}
            </tr>
          </thead>
          <tbody>
            {rels.map(rel => {
              const isOutgoing = rel.from_instance === instance.id;
              const ref        = isOutgoing ? rel.to_reference   : rel.from_reference;
              const wfName     = isOutgoing ? rel.to_workflow     : rel.from_workflow;
              const stateName  = isOutgoing ? rel.to_state        : rel.from_state;
              const completed  = isOutgoing ? rel.to_completed    : rel.from_completed;
              const otherId    = isOutgoing ? rel.to_instance     : rel.from_instance;
              return (
                <tr key={rel.id}>
                  <td>
                    <span style={{
                      fontSize: "0.7rem", fontWeight: 700, padding: "2px 6px",
                      borderRadius: 99, background: isOutgoing ? "rgba(99,102,241,0.12)" : "rgba(63,185,80,0.12)",
                      color: isOutgoing ? "#818cf8" : "#3fb950",
                    }}>
                      {isOutgoing ? "→ out" : "← in"}
                    </span>
                  </td>
                  <td>
                    <Link
                      to={`/instances/${otherId}`}
                      style={{ fontFamily: "monospace", fontSize: "0.82rem", color: "var(--accent-light)" }}
                    >
                      {ref}
                    </Link>
                  </td>
                  <td className="text-sm text-muted">{wfName}</td>
                  <td>
                    <span className={`badge ${completed ? "badge-terminal" : "badge-active"}`}>
                      {stateName}
                    </span>
                  </td>
                  <td>
                    <span style={{ fontFamily: "monospace", fontSize: "0.78rem", color: "var(--accent-light)" }}>
                      {rel.rel_type}
                    </span>
                    {rel.notes && (
                      <div className="text-xs text-muted" style={{ marginTop: 2 }}>{rel.notes}</div>
                    )}
                  </td>
                  {canLink && (
                    <td>
                      <button
                        className="btn-ghost btn-sm"
                        title="Remove link"
                        onClick={() => onUnlink(rel.id)}
                        style={{ color: "var(--danger)", padding: "4px 8px" }}
                      >
                        ✕
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
