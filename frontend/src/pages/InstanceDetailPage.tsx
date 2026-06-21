import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { WorkflowInstance, Transition, AuditEntry, UserProfile } from "../types/api";
import StateGraph from "../components/StateGraph";

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
      {/* Breadcrumb */}
      <div className="breadcrumb">
        <Link to="/instances">Instances</Link>
        <span>/</span>
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
            <h3>Actions</h3>
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
          <div className="card-header"><h3>Metadata</h3></div>
          {Object.keys(instance.metadata_json ?? {}).length === 0 ? (
            <p className="text-muted text-sm">No metadata recorded.</p>
          ) : (
            <table className="table">
              <tbody>
                {Object.entries(instance.metadata_json ?? {}).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ color: "var(--text-secondary)", width: "40%", fontFamily: "monospace", fontSize: "0.8rem" }}>{k}</td>
                    <td style={{ fontWeight: 500, wordBreak: "break-word" }}>{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {instance.completed_at && (
            <>
              <div className="divider" />
              <div className="text-sm text-muted">Completed {new Date(instance.completed_at).toLocaleString()}</div>
            </>
          )}
        </div>
      </div>

      {/* ── Audit trail / comments ── */}
      <div className="card mt-4">
        <div className="card-header">
          <h3>Timeline</h3>
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
                      <span>{new Date(entry.created_at).toLocaleString()}</span>
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
  if (action === "comment")               return "badge-initial";
  if (action.includes("transition"))      return "badge-active";
  if (action.includes("created"))         return "badge-active";
  if (action.includes("rule"))            return "badge-warning";
  if (action.includes("task"))            return "badge-pending";
  return "badge-inactive";
}

function eventIcon(action: string) {
  if (action.includes("transition")) return "→";
  if (action.includes("created"))    return "✦";
  if (action.includes("task"))       return "☑";
  if (action.includes("rule"))       return "⚡";
  return "·";
}
