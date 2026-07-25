import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { TransitionHook, Transition } from "../types/api";
import Hint from "./Hint";

interface Props {
  workflowId: string;
  transitions: Transition[];
  canEdit: boolean;
}

export default function HooksPanel({ transitions, canEdit }: Props) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [transition, setTransition] = useState("");
  const [action, setAction] = useState<"http_request" | "probe">("http_request");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState("POST");
  const [headersText, setHeadersText] = useState("");
  const [bodyTemplate, setBodyTemplate] = useState("");
  const [outputTo, setOutputTo] = useState("");
  const [onFailure, setOnFailure] = useState<"warn" | "ignore">("warn");
  const [err, setErr] = useState<string | null>(null);

  const transitionIds = transitions.map((t) => t.id);
  const { data: hooks = [] } = useQuery<TransitionHook[]>({
    queryKey: ["hooks", ...transitionIds],
    queryFn: async () => {
      // Fetch hooks for each transition in this workflow and flatten.
      const all = await Promise.all(
        transitionIds.map((id) => apiClient.get(`/hooks/?transition=${id}`).then((r) => r.data.results ?? r.data)),
      );
      return all.flat();
    },
    enabled: transitionIds.length > 0,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["hooks"] });

  const addHook = useMutation({
    mutationFn: async () => {
      const headers: Record<string, string> = {};
      for (const line of headersText.split("\n")) {
        const i = line.indexOf(":");
        if (i > 0) headers[line.slice(0, i).trim()] = line.slice(i + 1).trim();
      }
      return (await apiClient.post("/hooks/", {
        transition, trigger: "after", action,
        config: {
          url: url.trim(),
          ...(action === "http_request" ? { method, body_template: bodyTemplate, headers } : {}),
        },
        output_to: outputTo.trim(),
        on_failure: onFailure,
      })).data;
    },
    onSuccess: () => {
      invalidate();
      setUrl(""); setHeadersText(""); setBodyTemplate(""); setOutputTo(""); setTransition("");
      setErr(null); setShowForm(false);
    },
    onError: (e: any) =>
      setErr(e?.response?.data?.detail ?? e?.response?.data?.non_field_errors?.[0] ?? "Failed to add hook"),
  });

  const toggle = useMutation({
    mutationFn: async (h: TransitionHook) => apiClient.patch(`/hooks/${h.id}/`, { is_active: !h.is_active }),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => apiClient.delete(`/hooks/${id}/`),
    onSuccess: invalidate,
  });

  return (
    <div className="card mt-4">
      <div className="card-header">
        <h3>Action hooks <Hint tip="When a transition fires, call an external system — with credentials from the secret store, referenced as {{secret.NAME}}. The response can be written back into metadata. Outbound URLs are SSRF-guarded; deliveries retry." /></h3>
        <div className="flex gap-2 items-center">
          <span className="badge badge-inactive">{hooks.length}</span>
          {canEdit && (
            <button className={showForm ? "btn-secondary btn-sm" : "btn-primary btn-sm"} onClick={() => setShowForm(!showForm)}>
              {showForm ? "Cancel" : "+ Add hook"}
            </button>
          )}
        </div>
      </div>

      {showForm && (
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 10, padding: 16, marginBottom: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 10 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>On transition</label>
              <select value={transition} onChange={(e) => setTransition(e.target.value)}>
                <option value="">Select…</option>
                {transitions.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>Action</label>
              <select value={action} onChange={(e) => setAction(e.target.value as any)}>
                <option value="http_request">HTTP request</option>
                <option value="probe">Probe (GET)</option>
              </select>
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>On failure</label>
              <select value={onFailure} onChange={(e) => setOnFailure(e.target.value as any)}>
                <option value="warn">Warn but proceed</option>
                <option value="ignore">Ignore</option>
              </select>
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: 10 }}>
            <label>URL <span className="text-muted">(supports {"{{secret.NAME}}"}, {"{{metadata.key}}"}, {"{{instance.reference_number}}"})</span></label>
            <input placeholder="https://api.example.com/deploy" value={url} onChange={(e) => setUrl(e.target.value)} style={{ fontFamily: "monospace", fontSize: "0.82rem" }} />
          </div>

          {action === "http_request" && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 10, marginBottom: 10 }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Method</label>
                  <select value={method} onChange={(e) => setMethod(e.target.value)}>
                    {["POST", "PUT", "PATCH", "GET", "DELETE"].map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Headers <span className="text-muted">(one per line, <code>Name: value</code>)</span></label>
                  <textarea rows={2} placeholder="Authorization: Bearer {{secret.API_TOKEN}}" value={headersText} onChange={(e) => setHeadersText(e.target.value)} style={{ fontFamily: "monospace", fontSize: "0.8rem" }} />
                </div>
              </div>
              <div className="form-group" style={{ marginBottom: 10 }}>
                <label>Body template <span className="text-muted">(optional)</span></label>
                <textarea rows={2} placeholder='{"ref": "{{instance.reference_number}}"}' value={bodyTemplate} onChange={(e) => setBodyTemplate(e.target.value)} style={{ fontFamily: "monospace", fontSize: "0.8rem" }} />
              </div>
            </>
          )}

          <div className="form-group" style={{ marginBottom: 10 }}>
            <label>Write response to <span className="text-muted">(optional, e.g. <code>metadata.deploy_id</code>)</span></label>
            <input placeholder="metadata.deploy_id" value={outputTo} onChange={(e) => setOutputTo(e.target.value)} style={{ fontFamily: "monospace", fontSize: "0.82rem" }} />
          </div>

          {err && <div className="alert alert-error mb-2">{err}</div>}
          <button className="btn-primary btn-sm" onClick={() => addHook.mutate()} disabled={addHook.isPending || !transition || !url.trim()}>
            {addHook.isPending ? "Adding…" : "Add hook"}
          </button>
          <div className="text-xs text-muted" style={{ marginTop: 8 }}>
            Fires <strong>after</strong> the transition commits. Before-hooks (gating) are coming next.
          </div>
        </div>
      )}

      {hooks.length === 0 ? (
        <p className="text-muted text-sm">
          No action hooks. Add one to call an external system when a transition fires — e.g. provision a resource, notify a service, or write a result back into metadata.
        </p>
      ) : (
        <table className="table">
          <thead>
            <tr><th>Transition</th><th>Action</th><th>URL</th><th>Output</th><th>Fired</th><th>Status</th>{canEdit && <th style={{ width: 110 }}></th>}</tr>
          </thead>
          <tbody>
            {hooks.map((h) => (
              <tr key={h.id} style={{ opacity: h.is_active ? 1 : 0.5 }}>
                <td style={{ fontWeight: 600 }}>{h.transition_name}</td>
                <td><span className="badge badge-initial" style={{ fontSize: "0.65rem" }}>{h.action === "probe" ? "probe" : h.config.method ?? "POST"}</span></td>
                <td style={{ fontFamily: "monospace", fontSize: "0.75rem", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.config.url}</td>
                <td className="text-xs text-muted">{h.output_to || "—"}</td>
                <td className="text-sm text-muted">{h.execution_count}×</td>
                <td><span className={`badge ${h.is_active ? "badge-active" : "badge-inactive"}`}>{h.is_active ? "active" : "paused"}</span></td>
                {canEdit && (
                  <td>
                    <div className="flex gap-1">
                      <button className="btn-ghost btn-sm" onClick={() => toggle.mutate(h)}>{h.is_active ? "Pause" : "Resume"}</button>
                      <button className="btn-ghost btn-sm" style={{ color: "var(--danger)" }} onClick={() => remove.mutate(h.id)}>✕</button>
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
