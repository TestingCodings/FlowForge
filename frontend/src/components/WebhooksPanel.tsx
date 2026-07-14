import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { WebhookSubscription } from "../types/api";
import Hint from "./Hint";

const EVENT_OPTIONS = [
  { value: "instance_created",  label: "Instance created" },
  { value: "state_transition",  label: "State transition" },
  { value: "comment_added",     label: "Comment added" },
  { value: "rule_blocked",      label: "Rule blocked transition" },
  { value: "form_submitted",    label: "Form submitted" },
  { value: "sla_breached",      label: "SLA breached" },
  { value: "task_created",      label: "Task created" },
  { value: "task_completed",    label: "Task completed" },
];

interface Props {
  workflowId: string;
  canEdit: boolean;
}

export default function WebhooksPanel({ workflowId, canEdit }: Props) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const { data: hooks = [] } = useQuery<WebhookSubscription[]>({
    queryKey: ["webhooks", workflowId],
    queryFn: async () =>
      (await apiClient.get(`/webhooks/?workflow_definition=${workflowId}`)).data.results ?? [],
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["webhooks", workflowId] });

  const addHook = useMutation({
    mutationFn: async () =>
      (await apiClient.post("/webhooks/", {
        workflow_definition: workflowId,
        url: url.trim(),
        secret: secret.trim(),
        events,
      })).data,
    onSuccess: () => {
      invalidate();
      setUrl(""); setSecret(""); setEvents([]); setErr(null); setShowForm(false);
    },
    onError: (e: any) =>
      setErr(e?.response?.data?.url?.[0] ?? e?.response?.data?.detail ?? "Failed to add webhook"),
  });

  const toggleHook = useMutation({
    mutationFn: async (h: WebhookSubscription) =>
      apiClient.patch(`/webhooks/${h.id}/`, { is_active: !h.is_active }),
    onSuccess: invalidate,
  });

  const deleteHook = useMutation({
    mutationFn: async (hookId: string) => apiClient.delete(`/webhooks/${hookId}/`),
    onSuccess: invalidate,
  });

  const toggleEvent = (ev: string) =>
    setEvents(cur => cur.includes(ev) ? cur.filter(e => e !== ev) : [...cur, ev]);

  return (
    <div className="card mt-4">
      <div className="card-header">
        <h3>Webhooks <Hint tip="Automatic notifications to other systems. When something happens in this workflow (like a stage change), FlowForge sends a message to the web address you add — useful for Slack alerts or keeping other tools in sync." /></h3>
        <div className="flex gap-2 items-center">
          <span className="badge badge-inactive">{hooks.length}</span>
          {canEdit && (
            <button
              className={showForm ? "btn-secondary btn-sm" : "btn-primary btn-sm"}
              onClick={() => setShowForm(!showForm)}
            >
              {showForm ? "Cancel" : "+ Add webhook"}
            </button>
          )}
        </div>
      </div>

      {showForm && (
        <div style={{
          background: "var(--bg-elevated)", border: "1px solid var(--border)",
          borderRadius: 10, padding: 16, marginBottom: 16,
        }}>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 10, marginBottom: 10 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>Endpoint URL</label>
              <input
                placeholder="https://hooks.example.com/flowforge"
                value={url}
                onChange={e => setUrl(e.target.value)}
                style={{ fontFamily: "monospace", fontSize: "0.82rem" }}
              />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>Signing secret <span className="text-muted">(optional)</span></label>
              <input
                placeholder="HMAC-SHA256 key"
                value={secret}
                onChange={e => setSecret(e.target.value)}
                style={{ fontFamily: "monospace", fontSize: "0.82rem" }}
              />
            </div>
          </div>

          <div className="text-xs text-muted mb-2" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Events (none selected = all events)
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6, marginBottom: 12 }}>
            {EVENT_OPTIONS.map(opt => (
              <label
                key={opt.value}
                className="text-sm"
                style={{
                  display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
                  padding: "6px 8px", borderRadius: 6,
                  border: `1px solid ${events.includes(opt.value) ? "rgba(99,102,241,0.5)" : "var(--border)"}`,
                  background: events.includes(opt.value) ? "rgba(99,102,241,0.08)" : "transparent",
                }}
              >
                <input
                  type="checkbox"
                  checked={events.includes(opt.value)}
                  onChange={() => toggleEvent(opt.value)}
                />
                {opt.label}
              </label>
            ))}
          </div>

          {err && <div className="alert alert-error mb-2">{err}</div>}

          <button
            className="btn-primary btn-sm"
            onClick={() => addHook.mutate()}
            disabled={addHook.isPending || !url.trim()}
          >
            {addHook.isPending ? "Adding…" : "Add webhook"}
          </button>
          <div className="text-xs text-muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
            Payloads are JSON with <code>X-FlowForge-Event</code> and, when a secret is set,{" "}
            <code>X-FlowForge-Signature: sha256=…</code> (HMAC-SHA256 of the raw body).
          </div>
        </div>
      )}

      {hooks.length === 0 ? (
        <p className="text-muted text-sm">
          No webhooks configured. Add one to POST signed JSON to your systems on workflow events.
        </p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>URL</th>
              <th>Events</th>
              <th>Status</th>
              {canEdit && <th style={{ width: 120 }}></th>}
            </tr>
          </thead>
          <tbody>
            {hooks.map(h => (
              <tr key={h.id} style={{ opacity: h.is_active ? 1 : 0.5 }}>
                <td style={{ fontFamily: "monospace", fontSize: "0.8rem", wordBreak: "break-all" }}>{h.url}</td>
                <td>
                  {h.events.length === 0 ? (
                    <span className="badge badge-inactive">all events</span>
                  ) : (
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {h.events.map(ev => (
                        <span key={ev} className="badge badge-initial" style={{ fontSize: "0.65rem" }}>
                          {ev.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td>
                  <span className={`badge ${h.is_active ? "badge-active" : "badge-inactive"}`}>
                    {h.is_active ? "active" : "paused"}
                  </span>
                </td>
                {canEdit && (
                  <td>
                    <div className="flex gap-1">
                      <button className="btn-ghost btn-sm" onClick={() => toggleHook.mutate(h)}>
                        {h.is_active ? "Pause" : "Resume"}
                      </button>
                      <button
                        className="btn-ghost btn-sm"
                        style={{ color: "var(--danger)" }}
                        onClick={() => deleteHook.mutate(h.id)}
                      >
                        ✕
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
