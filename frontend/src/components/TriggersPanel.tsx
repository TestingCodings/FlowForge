import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { Trigger, Transition } from "../types/api";
import Hint from "./Hint";

interface Props {
  workflowId: string;
  transitions: Transition[];
  canEdit: boolean;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export default function TriggersPanel({ workflowId, transitions, canEdit }: Props) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [action, setAction] = useState<"create_instance" | "fire_transition">("create_instance");
  const [transition, setTransition] = useState("");
  const [lookupField, setLookupField] = useState("reference_number");
  const [mappingText, setMappingText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const { data: triggers = [] } = useQuery<Trigger[]>({
    queryKey: ["triggers", workflowId],
    queryFn: async () =>
      (await apiClient.get(`/triggers/?workflow_definition=${workflowId}`)).data.results ?? [],
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["triggers", workflowId] });

  const addTrigger = useMutation({
    mutationFn: async () => {
      let metadata_mapping: Record<string, string> = {};
      if (mappingText.trim()) {
        // "metaKey=payloadKey, other=field" → {metaKey: payloadKey, ...}
        for (const pair of mappingText.split(",")) {
          const [k, v] = pair.split("=").map((s) => s.trim());
          if (k && v) metadata_mapping[k] = v;
        }
      }
      return (await apiClient.post("/triggers/", {
        workflow_definition: workflowId,
        name: name.trim(),
        action,
        transition: action === "fire_transition" ? transition : null,
        lookup_field: lookupField,
        metadata_mapping,
      })).data;
    },
    onSuccess: () => {
      invalidate();
      setName(""); setTransition(""); setMappingText(""); setErr(null); setShowForm(false);
    },
    onError: (e: any) =>
      setErr(e?.response?.data?.detail ?? e?.response?.data?.non_field_errors?.[0] ?? "Failed to add trigger"),
  });

  const toggle = useMutation({
    mutationFn: async (t: Trigger) => apiClient.patch(`/triggers/${t.id}/`, { is_active: !t.is_active }),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => apiClient.delete(`/triggers/${id}/`),
    onSuccess: invalidate,
  });

  const fireUrl = (t: Trigger) => `${API_BASE.replace(/\/$/, "")}${t.fire_path}`;
  const copy = (t: Trigger) => {
    navigator.clipboard.writeText(fireUrl(t));
    setCopied(t.id);
    setTimeout(() => setCopied((c) => (c === t.id ? null : c)), 1500);
  };

  return (
    <div className="card mt-4">
      <div className="card-header">
        <h3>Triggers <Hint tip="The inbound counterpart to webhooks. Give an external system (like CI) a secret URL; when it POSTs, FlowForge creates an instance or fires a transition — so the outside world can drive this workflow automatically." /></h3>
        <div className="flex gap-2 items-center">
          <span className="badge badge-inactive">{triggers.length}</span>
          {canEdit && (
            <button className={showForm ? "btn-secondary btn-sm" : "btn-primary btn-sm"} onClick={() => setShowForm(!showForm)}>
              {showForm ? "Cancel" : "+ Add trigger"}
            </button>
          )}
        </div>
      </div>

      {showForm && (
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 10, padding: 16, marginBottom: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 10, marginBottom: 10 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>Name</label>
              <input placeholder="CI marks run passed" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>Action</label>
              <select value={action} onChange={(e) => setAction(e.target.value as any)}>
                <option value="create_instance">Create instance</option>
                <option value="fire_transition">Fire transition</option>
              </select>
            </div>
          </div>

          {action === "fire_transition" && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Transition to fire</label>
                <select value={transition} onChange={(e) => setTransition(e.target.value)}>
                  <option value="">Select…</option>
                  {transitions.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Find instance by <Hint tip="How the incoming payload identifies which instance to advance." /></label>
                <input placeholder="reference_number or metadata.<key>" value={lookupField} onChange={(e) => setLookupField(e.target.value)} style={{ fontFamily: "monospace", fontSize: "0.82rem" }} />
              </div>
            </div>
          )}

          <div className="form-group" style={{ marginBottom: 10 }}>
            <label>Metadata mapping <span className="text-muted">(optional — blank copies the whole payload)</span></label>
            <input placeholder="build=build_number, suite=suite" value={mappingText} onChange={(e) => setMappingText(e.target.value)} style={{ fontFamily: "monospace", fontSize: "0.82rem" }} />
            <div className="text-xs text-muted" style={{ marginTop: 4 }}>
              <code>metadataKey=payloadKey</code>, comma-separated. Maps incoming JSON fields onto instance metadata.
            </div>
          </div>

          {err && <div className="alert alert-error mb-2">{err}</div>}
          <button className="btn-primary btn-sm" onClick={() => addTrigger.mutate()}
            disabled={addTrigger.isPending || !name.trim() || (action === "fire_transition" && !transition)}>
            {addTrigger.isPending ? "Creating…" : "Create trigger"}
          </button>
        </div>
      )}

      {triggers.length === 0 ? (
        <p className="text-muted text-sm">
          No triggers yet. Add one to let an external system create instances or fire transitions by POSTing to a secret URL.
        </p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Action</th><th>Fire URL</th><th>Fired</th><th>Status</th>
              {canEdit && <th style={{ width: 120 }}></th>}
            </tr>
          </thead>
          <tbody>
            {triggers.map((t) => (
              <tr key={t.id} style={{ opacity: t.is_active ? 1 : 0.5 }}>
                <td style={{ fontWeight: 600 }}>{t.name}</td>
                <td>
                  <span className="badge badge-initial" style={{ fontSize: "0.65rem" }}>
                    {t.action === "create_instance" ? "create" : `→ ${t.transition_name ?? "transition"}`}
                  </span>
                </td>
                <td>
                  <button className="btn-ghost btn-sm" onClick={() => copy(t)} title={fireUrl(t)}
                    style={{ fontFamily: "monospace", fontSize: "0.72rem", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {copied === t.id ? "✓ copied" : `${t.fire_path.slice(0, 24)}… ⧉`}
                  </button>
                </td>
                <td className="text-sm text-muted">{t.trigger_count}×</td>
                <td><span className={`badge ${t.is_active ? "badge-active" : "badge-inactive"}`}>{t.is_active ? "active" : "paused"}</span></td>
                {canEdit && (
                  <td>
                    <div className="flex gap-1">
                      <button className="btn-ghost btn-sm" onClick={() => toggle.mutate(t)}>{t.is_active ? "Pause" : "Resume"}</button>
                      <button className="btn-ghost btn-sm" style={{ color: "var(--danger)" }} onClick={() => remove.mutate(t.id)}>✕</button>
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
