import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { Workflow, FormDefinitionApi, FormField } from "../types/api";
import StateGraph from "../components/StateGraph";
import Hint from "../components/Hint";
import WebhooksPanel from "../components/WebhooksPanel";
import PresentationPanel from "../components/PresentationPanel";
import { formatDate } from "../hooks/useWorkspace";

const FIELD_TYPES = ["text", "textarea", "number", "checkbox", "dropdown", "date"] as const;

/* ─── Constants ─── */
const OPERATORS = [
  { value: "gt",          label: "> greater than" },
  { value: "gte",         label: "≥ greater or equal" },
  { value: "lt",          label: "< less than" },
  { value: "lte",         label: "≤ less or equal" },
  { value: "eq",          label: "= equals" },
  { value: "ne",          label: "≠ not equals" },
  { value: "contains",    label: "contains (string)" },
  { value: "starts_with", label: "starts with (string)" },
  { value: "is_true",     label: "is true (boolean)" },
  { value: "is_false",    label: "is false (boolean)" },
];

const ACTION_TYPES = [
  { value: "block_transition", label: "Block transition" },
  { value: "assign_role",      label: "Assign role" },
];

const ROLES = [
  { value: "approver",          label: "Approver" },
  { value: "platform_admin",    label: "Platform Admin" },
  { value: "workflow_designer", label: "Workflow Designer" },
  { value: "participant",       label: "Participant" },
  { value: "viewer",            label: "Viewer" },
];

const BOOLEAN_OPS = ["is_true", "is_false"];

/* ─── Empty rule form state ─── */
const emptyForm = () => ({
  transitionId: "",  // "" = all transitions
  field: "",
  operator: "gt",
  value: "",
  actionType: "block_transition",
  reason: "",
  role: "approver",
  priority: 1,
});

export default function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const [showRuleForm, setShowRuleForm] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [ruleError, setRuleError] = useState("");
  const [createMsg, setCreateMsg] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [versionMsg, setVersionMsg] = useState<string | null>(null);

  /* ─── Queries ─── */
  const { data: wf, isLoading } = useQuery<Workflow>({
    queryKey: ["workflow", id],
    queryFn: async () => (await apiClient.get(`/workflows/${id}/`)).data,
    enabled: Boolean(id),
  });

  /* ─── Mutations ─── */
  const createInstance = useMutation({
    mutationFn: async () =>
      (await apiClient.post("/instances/", { workflow_definition: id })).data,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["instances"] });
      setCreateMsg(`Created ${data.reference_number}`);
      setCreateError(null);
      setTimeout(() => setCreateMsg(null), 4000);
    },
    onError: (err: any) =>
      setCreateError(err?.response?.data?.detail ?? "Failed to create instance"),
  });

  const addRule = useMutation({
    mutationFn: async () => {
      if (!form.field.trim()) throw new Error("Field is required");
      if (!BOOLEAN_OPS.includes(form.operator) && !form.value.toString().trim())
        throw new Error("Value is required");
      if (form.actionType === "block_transition" && !form.reason.trim())
        throw new Error("Block reason is required");

      const condition: Record<string, unknown> = { field: form.field.trim(), operator: form.operator };
      if (!BOOLEAN_OPS.includes(form.operator)) {
        const raw = form.value.trim();
        condition.value = isNaN(Number(raw)) ? raw : Number(raw);
      }

      const action: Record<string, unknown> =
        form.actionType === "block_transition"
          ? { type: "block_transition", reason: form.reason.trim() }
          : { type: "assign_role", role: form.role };

      return (
        await apiClient.post("/rules/", {
          workflow_definition: id,
          transition: form.transitionId || null,
          condition,
          action,
          priority: Number(form.priority),
        })
      ).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow", id] });
      setForm(emptyForm());
      setShowRuleForm(false);
      setRuleError("");
    },
    onError: (err: any) => {
      const msg = err.message?.startsWith("Field") || err.message?.startsWith("Value") || err.message?.startsWith("Block")
        ? err.message
        : err?.response?.data?.detail ?? JSON.stringify(err?.response?.data ?? "Failed to save rule");
      setRuleError(msg);
    },
  });

  const deleteRule = useMutation({
    mutationFn: async (ruleId: string) => apiClient.delete(`/rules/${ruleId}/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflow", id] }),
  });

  const publishNewVersion = useMutation({
    mutationFn: async () =>
      (await apiClient.post(`/workflows/${id}/publish-new-version/`)).data,
    onSuccess: (newWf) => {
      qc.invalidateQueries({ queryKey: ["workflow", id] });
      qc.invalidateQueries({ queryKey: ["workflows"] });
      qc.invalidateQueries({ queryKey: ["versionHistory", id] });
      setVersionMsg(`v${newWf.version} draft created — "${newWf.name}"`);
      setTimeout(() => setVersionMsg(null), 5000);
    },
  });

  const { data: versionHistory = [] } = useQuery<Workflow[]>({
    queryKey: ["versionHistory", id],
    queryFn: async () => (await apiClient.get(`/workflows/${id}/version-history/`)).data,
    enabled: Boolean(id),
  });

  const exportBundle = async () => {
    const resp = await apiClient.get(`/workflows/${id}/export/`, { responseType: "blob" });
    const url = URL.createObjectURL(resp.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(wf?.name ?? "workflow").toLowerCase().replace(/[^a-z0-9-_]+/g, "-")}-v${wf?.version ?? 1}.flowforge.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  /* ─── State forms ─── */
  const { data: stateForms = [] } = useQuery<FormDefinitionApi[]>({
    queryKey: ["stateForms", id],
    queryFn: async () =>
      (await apiClient.get(`/forms/?workflow_definition=${id}`)).data.results ?? [],
    enabled: Boolean(id),
  });

  const [formEditorState, setFormEditorState] = useState<string | null>(null); // state id being edited
  const [formName, setFormName] = useState("");
  const [formRequired, setFormRequired] = useState(true);
  const [formFields, setFormFields] = useState<FormField[]>([]);
  const [formSaveErr, setFormSaveErr] = useState<string | null>(null);

  const saveForm = useMutation({
    mutationFn: async () => {
      const payload = {
        workflow_definition: id,
        state: formEditorState,
        name: formName.trim(),
        schema: {
          required_to_transition: formRequired,
          fields: formFields.filter(f => f.name.trim()),
        },
        version: 1,
      };
      const existing = stateForms.find(f => f.state === formEditorState);
      if (existing) {
        return (await apiClient.put(`/forms/${existing.id}/`, { ...payload, version: existing.version })).data;
      }
      return (await apiClient.post("/forms/", payload)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stateForms", id] });
      setFormEditorState(null);
      setFormSaveErr(null);
    },
    onError: (err: any) =>
      setFormSaveErr(JSON.stringify(err?.response?.data ?? "Save failed")),
  });

  const deleteForm = useMutation({
    mutationFn: async (formId: string) => apiClient.delete(`/forms/${formId}/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["stateForms", id] }),
  });

  const openFormEditor = (stateId: string) => {
    const existing = stateForms.find(f => f.state === stateId);
    setFormName(existing?.name ?? "");
    setFormRequired(existing?.schema?.required_to_transition ?? true);
    setFormFields(existing?.schema?.fields ?? [{ name: "", type: "text", required: false, label: "" }]);
    setFormSaveErr(null);
    setFormEditorState(stateId);
  };

  /* ─── Loading / not found ─── */
  if (isLoading) {
    return (
      <div>
        <div className="breadcrumb"><Link to="/workflows">Workflows</Link><span>/</span>Loading…</div>
        <div className="skeleton" style={{ height: 300, borderRadius: 14, marginTop: 16 }} />
      </div>
    );
  }
  if (!wf) return <div className="card empty-state"><p>Workflow not found.</p></div>;

  const isBooleanOp = BOOLEAN_OPS.includes(form.operator);
  const initialState = (wf.states ?? []).find((s) => s.is_initial);

  /* ─── Render ─── */
  return (
    <div>
      {/* Breadcrumb + header */}
      <div className="breadcrumb">
        <Link to="/workflows">Workflows</Link><span>/</span>
        <span style={{ color: "var(--text-primary)" }}>{wf.name}</span>
      </div>

      <div className="page-header" style={{ marginTop: 8 }}>
        <div className="page-header-left">
          <h2>{wf.name}</h2>
          <p>{wf.description || "No description"}</p>
        </div>
        <div className="flex gap-2 items-center">
          <span className="badge badge-role-workflow_designer" style={{ fontFamily: "monospace" }}>{wf.reference_prefix}</span>
          <span className={`badge ${wf.is_active ? "badge-active" : "badge-inactive"}`}>
            {wf.is_active ? "Active" : "Inactive"}
          </span>
          <span className="badge badge-inactive">
            v{wf.version}{wf.published_at ? "" : " · draft"}
          </span>
          {(wf.ui_schema?.shell ?? "list") !== "list" && (
            <Link to={`/workflows/${id}/view`} className="btn-primary btn-sm" style={{ textDecoration: "none" }}>
              Open {wf.ui_schema?.shell} view
            </Link>
          )}
          <Link
            to={`/workflows/${id}/edit`}
            className="btn-secondary btn-sm"
            style={{ textDecoration: "none" }}
            title="Open this workflow's graph in the visual builder"
          >
            Edit in Builder
          </Link>
          <button
            className="btn-secondary btn-sm"
            onClick={exportBundle}
            title="Download this workflow as a portable .flowforge.json bundle"
          >
            Export
          </button>
          <button
            className="btn-secondary btn-sm"
            onClick={() => publishNewVersion.mutate()}
            disabled={publishNewVersion.isPending}
            title="Stamp this version as published and create a v+1 draft"
          >
            {publishNewVersion.isPending ? "Creating…" : "Publish new version"}
          </button>
        </div>
      </div>

      {/* State graph */}
      <div className="mb-4">
        <StateGraph
          states={wf.states ?? []}
          transitions={wf.transitions ?? []}
          currentStateId={initialState?.id ?? ""}
        />
      </div>

      {/* Create-instance banner */}
      {wf.is_active && (
        <div className="card mb-4" style={{ background: "rgba(99,102,241,0.07)", borderColor: "rgba(99,102,241,0.3)" }}>
          <div className="flex items-center gap-3">
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, marginBottom: 3 }}>Start a new instance</div>
              <div className="text-sm text-muted">
                Creates a new {wf.reference_prefix} case at "{initialState?.display_name ?? initialState?.name}" state
              </div>
            </div>
            <button className="btn-primary" onClick={() => createInstance.mutate()} disabled={createInstance.isPending}>
              {createInstance.isPending ? "Creating…" : `+ New ${wf.reference_prefix}`}
            </button>
          </div>
          {createMsg   && <div className="alert alert-success mt-2">{createMsg}</div>}
          {createError && <div className="alert alert-error   mt-2">{createError}</div>}
        </div>
      )}

      {/* States + Transitions */}
      <div className="grid grid-2 mb-4">
        <div className="card">
          <div className="card-header">
            <h3>States <Hint tip="The stages an item can be in, from start to finish. Every item is always in exactly one state." below /></h3>
            <span className="badge badge-inactive">{wf.states?.length ?? 0}</span>
          </div>
          <table className="table">
            <thead><tr><th>Name</th><th>Type</th><th>SLA</th></tr></thead>
            <tbody>
              {(wf.states ?? []).sort((a, b) => a.position_order - b.position_order).map((s) => (
                <tr key={s.id}>
                  <td style={{ fontWeight: 500 }}>{s.display_name || s.name}</td>
                  <td>
                    {s.is_initial  && <span className="badge badge-initial">Start</span>}
                    {s.is_terminal && <span className="badge badge-terminal">End</span>}
                    {!s.is_initial && !s.is_terminal && <span className="badge badge-inactive">Step</span>}
                  </td>
                  <td className="text-muted text-sm">
                    {(s.sla_config as any)?.sla_hours ? `${(s.sla_config as any).sla_hours}h` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <div className="card-header">
            <h3>Transitions <Hint tip="The allowed moves between stages — the buttons people see on an item. A transition can require approver sign-off." below /></h3>
            <span className="badge badge-inactive">{wf.transitions?.length ?? 0}</span>
          </div>
          <table className="table">
            <thead><tr><th>Name</th><th>From → To</th><th>Approval</th></tr></thead>
            <tbody>
              {(wf.transitions ?? []).map((t) => {
                const from = (wf.states ?? []).find((s) => s.id === t.from_state);
                const to   = (wf.states ?? []).find((s) => s.id === t.to_state);
                return (
                  <tr key={t.id}>
                    <td style={{ fontWeight: 500 }}>{t.name}</td>
                    <td className="text-sm text-muted">{from?.name} → {to?.name}</td>
                    <td>
                      {t.requires_approval
                        ? <span className="badge badge-pending">Required</span>
                        : <span className="badge badge-inactive">None</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Rules section ── */}
      <div className="card">
        <div className="card-header">
          <div className="flex items-center gap-3">
            <h3>Rules <Hint tip="Automatic checks that run when someone tries to move an item. A rule can block the move (with a message) or assign it to a role, based on the item's data." below /></h3>
            {(wf.rules ?? []).length > 0 && (
              <span className="badge badge-warning">{wf.rules.length} active</span>
            )}
          </div>
          <button
            className={showRuleForm ? "btn-secondary btn-sm" : "btn-primary btn-sm"}
            onClick={() => { setShowRuleForm((v) => !v); setRuleError(""); }}
          >
            {showRuleForm ? "Cancel" : "+ Add Rule"}
          </button>
        </div>

        {/* ── Rule Builder Form ── */}
        {showRuleForm && (
          <div style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: 20,
            marginBottom: 20,
          }}>
            <div style={{ fontSize: "0.78rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--text-secondary)", marginBottom: 16 }}>
              New Rule
            </div>

            {/* Row 1: Trigger */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Trigger transition</label>
                <select value={form.transitionId} onChange={(e) => setForm({ ...form, transitionId: e.target.value })}>
                  <option value="">All transitions (global)</option>
                  {(wf.transitions ?? []).map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
                <span className="text-xs text-muted" style={{ marginTop: 4, display: "block" }}>
                  Which transition fires this rule. "All" = fires on every transition attempt.
                </span>
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Priority</label>
                <input
                  type="number" min={1} max={100}
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
                />
                <span className="text-xs text-muted" style={{ marginTop: 4, display: "block" }}>
                  Lower number = evaluated first. Use 1 for highest priority.
                </span>
              </div>
            </div>

            {/* Condition builder */}
            <div style={{
              background: "var(--bg-base)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 14,
              marginBottom: 12,
            }}>
              <div className="text-xs text-muted mb-2" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Condition — reads from instance metadata
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr 1fr", gap: 10 }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Field</label>
                  <input
                    placeholder="e.g. claim_value"
                    value={form.field}
                    onChange={(e) => setForm({ ...form, field: e.target.value })}
                    style={{ fontFamily: "monospace" }}
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Operator</label>
                  <select value={form.operator} onChange={(e) => setForm({ ...form, operator: e.target.value })}>
                    {OPERATORS.map((op) => (
                      <option key={op.value} value={op.value}>{op.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Value</label>
                  <input
                    placeholder={isBooleanOp ? "— not needed —" : "e.g. 10000"}
                    value={form.value}
                    onChange={(e) => setForm({ ...form, value: e.target.value })}
                    disabled={isBooleanOp}
                    style={{ fontFamily: "monospace", opacity: isBooleanOp ? 0.4 : 1 }}
                  />
                </div>
              </div>
              {/* Live preview */}
              {form.field && (
                <div style={{ marginTop: 10, padding: "6px 10px", background: "rgba(99,102,241,0.08)", borderRadius: 6, fontFamily: "monospace", fontSize: "0.8rem", color: "var(--accent-light)" }}>
                  IF {form.field} {form.operator}{!isBooleanOp && form.value ? ` ${form.value}` : ""}
                </div>
              )}
            </div>

            {/* Action builder */}
            <div style={{
              background: "var(--bg-base)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 14,
              marginBottom: 14,
            }}>
              <div className="text-xs text-muted mb-2" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Action — what happens when condition is met
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 10 }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Action type</label>
                  <select value={form.actionType} onChange={(e) => setForm({ ...form, actionType: e.target.value })}>
                    {ACTION_TYPES.map((a) => (
                      <option key={a.value} value={a.value}>{a.label}</option>
                    ))}
                  </select>
                </div>
                {form.actionType === "block_transition" ? (
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label>Block reason (shown to user)</label>
                    <input
                      placeholder="e.g. Claims over £10,000 require Director approval."
                      value={form.reason}
                      onChange={(e) => setForm({ ...form, reason: e.target.value })}
                    />
                  </div>
                ) : (
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label>Assign to role</label>
                    <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                      {ROLES.map((r) => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
              {/* Action preview */}
              {form.field && (
                <div style={{ marginTop: 10, padding: "6px 10px", background: form.actionType === "block_transition" ? "rgba(248,81,73,0.08)" : "rgba(63,185,80,0.08)", borderRadius: 6, fontFamily: "monospace", fontSize: "0.8rem", color: form.actionType === "block_transition" ? "#ff8a84" : "#6fda8a" }}>
                  THEN {form.actionType === "block_transition"
                    ? `block — "${form.reason || "reason required"}"`
                    : `assign role → ${form.role}`}
                </div>
              )}
            </div>

            {ruleError && <div className="alert alert-error mb-3">{ruleError}</div>}

            <div className="flex gap-2">
              <button
                className="btn-primary"
                onClick={() => addRule.mutate()}
                disabled={addRule.isPending}
              >
                {addRule.isPending ? "Saving…" : "Save Rule"}
              </button>
              <button className="btn-secondary" onClick={() => { setShowRuleForm(false); setForm(emptyForm()); setRuleError(""); }}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* ── Rules table ── */}
        {(wf.rules ?? []).length === 0 && !showRuleForm ? (
          <div className="empty-state" style={{ padding: "28px 0" }}>
            <p>No rules yet.</p>
            <p className="text-xs" style={{ marginTop: 6 }}>
              Rules automatically block or modify transitions based on instance data.
              <br />Click <strong>+ Add Rule</strong> to create your first one.
            </p>
          </div>
        ) : (wf.rules ?? []).length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Trigger</th>
                <th>Condition</th>
                <th>Action</th>
                <th style={{ width: 60 }}>Priority</th>
                <th style={{ width: 48 }}></th>
              </tr>
            </thead>
            <tbody>
              {(wf.rules ?? []).sort((a, b) => a.priority - b.priority).map((r) => {
                const tr   = (wf.transitions ?? []).find((t) => t.id === r.transition);
                const cond = r.condition as any;
                const act  = r.action as any;
                const isBool = BOOLEAN_OPS.includes(cond.operator);

                return (
                  <tr key={r.id}>
                    <td className="text-sm">
                      {tr
                        ? <span style={{ fontWeight: 500 }}>{tr.name}</span>
                        : <span className="text-muted">All transitions</span>}
                    </td>
                    <td>
                      <span style={{ fontFamily: "monospace", fontSize: "0.8rem", color: "var(--accent-light)" }}>
                        {cond.field} {cond.operator}{!isBool && cond.value !== undefined ? ` ${cond.value}` : ""}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                        <span className={`badge ${act.type === "block_transition" ? "badge-danger" : "badge-active"}`} style={{ alignSelf: "flex-start" }}>
                          {act.type === "block_transition" ? "Block" : "Assign role"}
                        </span>
                        {act.reason && (
                          <span className="text-xs text-muted" style={{ maxWidth: 280, lineHeight: 1.4 }}>{act.reason}</span>
                        )}
                        {act.role && (
                          <span className={`badge badge-role-${act.role}`} style={{ alignSelf: "flex-start", fontSize: "0.68rem" }}>{act.role}</span>
                        )}
                      </div>
                    </td>
                    <td className="text-muted text-sm">{r.priority}</td>
                    <td>
                      <button
                        className="btn-ghost btn-sm"
                        title="Delete rule"
                        onClick={() => deleteRule.mutate(r.id)}
                        disabled={deleteRule.isPending}
                        style={{ color: "var(--danger)", padding: "4px 8px" }}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : null}

        {/* Operator reference */}
        {showRuleForm && (
          <details style={{ marginTop: 16 }}>
            <summary className="text-xs text-muted" style={{ cursor: "pointer", userSelect: "none" }}>
              Operator reference
            </summary>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 6, marginTop: 10 }}>
              {OPERATORS.map((op) => (
                <div key={op.value} style={{ padding: "6px 10px", background: "var(--bg-base)", borderRadius: 6, fontSize: "0.78rem" }}>
                  <span style={{ fontFamily: "monospace", color: "var(--accent-light)", marginRight: 6 }}>{op.value}</span>
                  <span className="text-muted">{op.label.replace(/^[^(]+/, "").replace(/[()]/g, "").trim() || op.label}</span>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>

      {/* ── State forms ── */}
      <div className="card mt-4">
        <div className="card-header">
          <div className="flex items-center gap-3">
            <h3>State Forms <Hint tip="Forms collect required information at each stage. If a form is marked as blocking, the item cannot leave that stage until the form is filled in." /></h3>
            {stateForms.length > 0 && (
              <span className="badge badge-active">{stateForms.length} configured</span>
            )}
          </div>
        </div>
        <p className="text-sm text-muted" style={{ marginBottom: 14 }}>
          Attach a structured form to any state. Required forms must be completed before an
          instance can transition out of that state, and submitted values feed directly into
          rule evaluation.
        </p>

        <table className="table">
          <thead>
            <tr><th>State</th><th>Form</th><th>Fields</th><th>Gate</th><th style={{ width: 130 }}></th></tr>
          </thead>
          <tbody>
            {(wf.states ?? []).filter(s => !s.is_terminal).map(s => {
              const f = stateForms.find(x => x.state === s.id);
              return (
                <tr key={s.id}>
                  <td style={{ fontWeight: 500 }}>{s.display_name || s.name}</td>
                  <td>
                    {f
                      ? <span style={{ color: "var(--accent-light)" }}>{f.name}</span>
                      : <span className="text-muted text-sm">—</span>}
                  </td>
                  <td className="text-sm text-muted">
                    {f ? `${(f.schema.fields ?? []).length} field${(f.schema.fields ?? []).length === 1 ? "" : "s"}` : "—"}
                  </td>
                  <td>
                    {f && (
                      <span className={`badge ${f.schema.required_to_transition !== false ? "badge-warning" : "badge-inactive"}`} style={{ fontSize: "0.68rem" }}>
                        {f.schema.required_to_transition !== false ? "Blocks transition" : "Optional"}
                      </span>
                    )}
                  </td>
                  <td>
                    <div className="flex gap-2">
                      <button className="btn-secondary btn-sm" onClick={() => openFormEditor(s.id)}>
                        {f ? "Edit" : "+ Add form"}
                      </button>
                      {f && (
                        <button
                          className="btn-ghost btn-sm"
                          style={{ color: "var(--danger)" }}
                          onClick={() => deleteForm.mutate(f.id)}
                        >✕</button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* Form editor */}
        {formEditorState && (
          <div style={{
            marginTop: 16, padding: 16, background: "var(--bg-elevated)",
            border: "1px solid var(--border)", borderRadius: 10,
          }}>
            <div className="flex items-center gap-3 mb-3" style={{ justifyContent: "space-between" }}>
              <strong className="text-sm">
                Form for state:{" "}
                <span style={{ color: "var(--accent-light)" }}>
                  {(wf.states ?? []).find(s => s.id === formEditorState)?.name}
                </span>
              </strong>
              <label className="flex items-center gap-2 text-sm" style={{ cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={formRequired}
                  onChange={e => setFormRequired(e.target.checked)}
                  style={{ accentColor: "#6366f1" }}
                />
                Must be completed before transition
              </label>
            </div>

            <div className="form-group" style={{ marginBottom: 12 }}>
              <label>Form name</label>
              <input
                placeholder="e.g. Claim Assessment"
                value={formName}
                onChange={e => setFormName(e.target.value)}
              />
            </div>

            <div className="text-xs text-muted mb-2" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Fields
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 10 }}>
              {formFields.map((fld, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr 130px auto auto", gap: 6, alignItems: "center" }}>
                  <input
                    placeholder="field_name"
                    value={fld.name}
                    onChange={e => setFormFields(rows => rows.map((r, j) => j === i ? { ...r, name: e.target.value.replace(/\s+/g, "_").toLowerCase() } : r))}
                    style={{ fontFamily: "monospace", fontSize: "0.8rem", padding: "5px 8px" }}
                  />
                  <input
                    placeholder="Label shown to user"
                    value={fld.label ?? ""}
                    onChange={e => setFormFields(rows => rows.map((r, j) => j === i ? { ...r, label: e.target.value } : r))}
                    style={{ fontSize: "0.82rem", padding: "5px 8px" }}
                  />
                  <select
                    value={fld.type}
                    onChange={e => setFormFields(rows => rows.map((r, j) => j === i ? { ...r, type: e.target.value as FormField["type"] } : r))}
                    style={{ fontSize: "0.8rem", padding: "5px 8px" }}
                  >
                    {FIELD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <label className="flex items-center gap-1 text-xs" style={{ cursor: "pointer", whiteSpace: "nowrap" }}>
                    <input
                      type="checkbox"
                      checked={Boolean(fld.required)}
                      onChange={e => setFormFields(rows => rows.map((r, j) => j === i ? { ...r, required: e.target.checked } : r))}
                      style={{ accentColor: "#6366f1" }}
                    />
                    required
                  </label>
                  <button
                    className="btn-ghost btn-sm"
                    style={{ color: "var(--danger)", padding: "4px 8px" }}
                    onClick={() => setFormFields(rows => rows.filter((_, j) => j !== i))}
                  >✕</button>
                </div>
              ))}
            </div>

            <button
              className="btn-ghost btn-sm"
              style={{ marginBottom: 12, width: "100%", borderStyle: "dashed" }}
              onClick={() => setFormFields(rows => [...rows, { name: "", type: "text", required: false, label: "" }])}
            >
              + Add field
            </button>

            {formSaveErr && <div className="alert alert-error mb-2">{formSaveErr}</div>}

            <div className="flex gap-2">
              <button
                className="btn-primary btn-sm"
                onClick={() => saveForm.mutate()}
                disabled={saveForm.isPending || !formName.trim() || formFields.filter(f => f.name.trim()).length === 0}
              >
                {saveForm.isPending ? "Saving…" : "Save form"}
              </button>
              <button className="btn-secondary btn-sm" onClick={() => setFormEditorState(null)}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Webhooks ── */}
      <PresentationPanel workflow={wf} />

      {id && <WebhooksPanel workflowId={id} canEdit={true} />}

      {/* ── Version history ── */}
      {versionHistory.length > 1 && (
        <div className="card mt-4">
          <div className="card-header">
            <h3>Version history <Hint tip="Publishing creates a new editable version while items already in progress carry on under the version they started with." /></h3>
            <span className="badge badge-inactive">{versionHistory.length} versions</span>
          </div>
          {versionMsg && <div className="alert alert-success mb-3">{versionMsg}</div>}
          <table className="table">
            <thead>
              <tr>
                <th>Version</th>
                <th>Name</th>
                <th>Status</th>
                <th>Published</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {[...versionHistory].reverse().map((v) => (
                <tr key={v.id} style={v.id === id ? { background: "rgba(99,102,241,0.06)" } : undefined}>
                  <td>
                    <span className="badge badge-inactive" style={{ fontFamily: "monospace" }}>v{v.version}</span>
                  </td>
                  <td style={{ fontWeight: v.id === id ? 600 : 400 }}>
                    {v.name}
                    {v.id === id && <span className="text-muted text-xs" style={{ marginLeft: 6 }}>← current</span>}
                  </td>
                  <td>
                    <span className={`badge ${v.is_active ? "badge-active" : "badge-inactive"}`}>
                      {v.is_active ? "Active" : v.published_at ? "Archived" : "Draft"}
                    </span>
                  </td>
                  <td className="text-muted text-sm">
                    {v.published_at
                      ? formatDate(v.published_at)
                      : "—"}
                  </td>
                  <td>
                    {v.id !== id && (
                      <Link
                        to={`/workflows/${v.id}`}
                        style={{ fontSize: "0.78rem", color: "var(--accent-light)" }}
                      >
                        View →
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {versionMsg && versionHistory.length <= 1 && (
        <div className="alert alert-success mt-3">{versionMsg}</div>
      )}
    </div>
  );
}
