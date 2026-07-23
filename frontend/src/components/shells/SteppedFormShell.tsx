import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";
import { CurrentForm, FormField, State, Transition, WorkflowInstance } from "../../types/api";
import { instanceTitle, ShellProps, stateColour, stateIcon } from "./types";

/**
 * Stepped-form shell (VISION Layer 2) — the Typeform / multi-step-wizard view.
 *
 * The other shells lay many instances out at once; this one focuses on moving
 * a single instance forward. It renders the workflow's states as an ordered
 * progress stepper and presents the current state's form as one big centred
 * card. Submitting the form and picking a transition advances the instance —
 * both still go through the engine, so rules, approvals, and required-form
 * gating apply exactly as everywhere else.
 */
export default function SteppedFormShell({ workflow, instances, fireTransition, transitionPending }: ShellProps) {
  const qc = useQueryClient();

  const orderedStates: State[] = useMemo(
    () => [...(workflow.states ?? [])].sort((a, b) => a.position_order - b.position_order),
    [workflow],
  );

  // Default to the first open instance so the wizard opens on real work.
  const firstOpen = instances.find((i) => !i.completed_at) ?? instances[0];
  const [selectedId, setSelectedId] = useState<string | null>(firstOpen?.id ?? null);
  const listRow = instances.find((i) => i.id === selectedId) ?? firstOpen ?? null;

  // The list payload omits current_form (detail-only, to avoid N+1). The
  // wizard focuses on one instance, so fetching that instance's detail is
  // cheap and gives us the form + freshest state.
  const { data: detail } = useQuery<WorkflowInstance>({
    queryKey: ["instance", selectedId],
    queryFn: async () => (await apiClient.get(`/instances/${selectedId}/`)).data,
    enabled: Boolean(selectedId),
  });
  const selected = detail ?? listRow;

  const [formError, setFormError] = useState<string | null>(null);

  const submitForm = useMutation({
    mutationFn: async (payload: { form_definition: string; data: Record<string, unknown> }) =>
      (await apiClient.post("/submissions/", { workflow_instance: selected!.id, ...payload })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instances", "by-workflow", workflow.id] });
      qc.invalidateQueries({ queryKey: ["instance", selectedId] });
      setFormError(null);
    },
    onError: (e: any) => {
      const d = e?.response?.data;
      setFormError(typeof d === "string" ? d : d?.detail ?? JSON.stringify(d) ?? "Submission failed");
    },
  });

  if (!selected) {
    return (
      <div className="card" style={{ textAlign: "center", padding: 40, color: "var(--text-secondary)" }}>
        No instances yet — create one to start the guided flow.
      </div>
    );
  }

  const currentIdx = orderedStates.findIndex((s) => s.id === selected.current_state);
  const form = selected.current_form;
  const isCompleted = Boolean(selected.completed_at);

  const availableTransitions: Transition[] = (workflow.transitions ?? []).filter(
    (t) => t.from_state === selected.current_state,
  );
  // Required, unsubmitted form blocks advancing (mirrors the engine's gate).
  const formBlocks = Boolean(form && form.required_to_transition && !form.submitted);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Instance selector — the wizard works one instance at a time */}
      {instances.length > 1 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="text-xs text-muted">Working on:</span>
          <select
            value={selected.id}
            onChange={(e) => { setSelectedId(e.target.value); setFormError(null); }}
            style={{ maxWidth: 320, padding: "6px 10px", fontSize: "0.85rem" }}
          >
            {instances.map((i) => (
              <option key={i.id} value={i.id}>
                {i.reference_number}
                {instanceTitle(workflow, i) ? ` — ${instanceTitle(workflow, i)}` : ""}
                {i.completed_at ? " (completed)" : ""}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Progress stepper */}
      <div style={{ display: "flex", alignItems: "center", gap: 0, overflowX: "auto", paddingBottom: 4 }}>
        {orderedStates.map((s, i) => {
          const done = i < currentIdx || (isCompleted && i <= currentIdx);
          const active = i === currentIdx && !isCompleted;
          const colour = stateColour(workflow, s.name) ?? (active ? "var(--accent)" : done ? "var(--success)" : "var(--border)");
          const icon = stateIcon(workflow, s.name);
          return (
            <div key={s.id} style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, minWidth: 78 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: "50%",
                  border: `2px solid ${colour}`,
                  background: active ? colour : done ? `${colour}22` : "transparent",
                  color: active ? "#fff" : colour,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: "0.72rem", fontWeight: 700,
                }}>
                  {done ? "✓" : icon ?? i + 1}
                </div>
                <span className="text-xs" style={{
                  color: active ? "var(--text-primary)" : "var(--text-secondary)",
                  fontWeight: active ? 700 : 400, textAlign: "center", maxWidth: 78,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>
                  {s.display_name || s.name}
                </span>
              </div>
              {i < orderedStates.length - 1 && (
                <div style={{ width: 26, height: 2, background: i < currentIdx ? "var(--success)" : "var(--border)", flexShrink: 0 }} />
              )}
            </div>
          );
        })}
      </div>

      {/* Focused step card */}
      <div className="card" style={{ maxWidth: 640, margin: "0 auto", width: "100%", padding: "28px 32px" }}>
        <div className="text-xs text-muted" style={{ marginBottom: 4 }}>
          {selected.reference_number}
          {instanceTitle(workflow, selected) ? ` · ${instanceTitle(workflow, selected)}` : ""}
        </div>

        {isCompleted ? (
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <div style={{ fontSize: 40 }}>🎉</div>
            <h2 style={{ marginTop: 8 }}>Completed</h2>
            <p className="text-muted" style={{ marginTop: 4 }}>
              This instance reached <strong>{selected.current_state_name}</strong>.
            </p>
            <Link to={`/instances/${selected.id}`} className="btn-secondary btn-sm" style={{ marginTop: 14, textDecoration: "none" }}>
              View full record
            </Link>
          </div>
        ) : (
          <>
            <h2 style={{ fontSize: "1.3rem", marginBottom: 2 }}>{selected.current_state_name}</h2>

            {form ? (
              <StepForm
                key={`${selected.id}:${form.id}:${String(form.submitted)}`}
                form={form}
                isPending={submitForm.isPending}
                error={formError}
                onSubmit={(data) => submitForm.mutate({ form_definition: form.id, data })}
              />
            ) : (
              <p className="text-muted text-sm" style={{ margin: "12px 0 20px" }}>
                No form for this step — choose how to continue.
              </p>
            )}

            {/* Advance controls */}
            <div style={{ marginTop: 22, borderTop: "1px solid var(--border)", paddingTop: 18 }}>
              {formBlocks && (
                <p className="text-xs" style={{ color: "var(--warning)", marginBottom: 10 }}>
                  Submit the form above before continuing.
                </p>
              )}
              {availableTransitions.length === 0 ? (
                <p className="text-muted text-sm">No transitions available from this step.</p>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {availableTransitions.map((t) => (
                    <button
                      key={t.id}
                      className="btn-primary"
                      disabled={formBlocks || transitionPending}
                      onClick={() => fireTransition(selected, t)}
                    >
                      {t.name} →
                    </button>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ── Focused, Typeform-styled form for the current step ── */
function StepForm({
  form, isPending, error, onSubmit,
}: {
  form: CurrentForm;
  isPending: boolean;
  error: string | null;
  onSubmit: (data: Record<string, unknown>) => void;
}) {
  const fields = form.schema.fields ?? [];
  const [values, setValues] = useState<Record<string, unknown>>(form.submission_data ?? {});
  const [errs, setErrs] = useState<Record<string, string>>({});

  const setValue = (name: string, v: unknown) => setValues((p) => ({ ...p, [name]: v }));

  const submit = () => {
    const e: Record<string, string> = {};
    for (const f of fields) {
      const v = values[f.name];
      if (f.required && (v === undefined || v === null || v === "")) e[f.name] = "Required";
      if (v !== undefined && v !== "" && (f.type === "number" || f.type === "currency")) {
        const n = Number(v);
        if (Number.isNaN(n)) e[f.name] = "Must be a number";
        else if (f.min !== undefined && n < f.min) e[f.name] = `Must be ≥ ${f.min}`;
        else if (f.max !== undefined && n > f.max) e[f.name] = `Must be ≤ ${f.max}`;
      }
    }
    setErrs(e);
    if (Object.keys(e).length) return;

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
      <div style={{ margin: "14px 0 4px" }}>
        <span className="badge badge-active">✓ {form.name} submitted</span>
        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
          {Object.entries(form.submission_data ?? {}).map(([k, v]) => {
            const field = fields.find((f) => f.name === k);
            return (
              <div key={k} style={{ display: "flex", gap: 10, fontSize: "0.85rem" }}>
                <span className="text-muted" style={{ minWidth: 140 }}>{field?.label || k}</span>
                <span style={{ fontWeight: 500 }}>{String(v)}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 18 }}>
      {fields.map((f) => (
        <StepField key={f.name} field={f} value={values[f.name]} error={errs[f.name]} onChange={(v) => setValue(f.name, v)} />
      ))}
      {error && <div className="alert alert-error">{error}</div>}
      <button className="btn-primary" onClick={submit} disabled={isPending} style={{ alignSelf: "flex-start" }}>
        {isPending ? "Submitting…" : "Submit"}
      </button>
    </div>
  );
}

function StepField({
  field, value, error, onChange,
}: {
  field: FormField;
  value: unknown;
  error?: string;
  onChange: (v: unknown) => void;
}) {
  const label = (
    <label style={{ display: "block", fontSize: "0.95rem", fontWeight: 600, marginBottom: 6 }}>
      {field.label || field.name}
      {field.required && <span style={{ color: "var(--danger)", marginLeft: 4 }}>*</span>}
    </label>
  );
  const big = { padding: "10px 12px", fontSize: "1rem", width: "100%" } as const;

  let control: JSX.Element;
  switch (field.type) {
    case "textarea":
      control = <textarea value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} rows={4} style={big} />;
      break;
    case "checkbox":
    case "toggle":
      // Boolean fields carry their own inline label, so skip the block label.
      return (
        <div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.95rem", cursor: "pointer" }}>
            <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} style={{ width: "auto" }} />
            {field.label || field.name}
            {field.required && <span style={{ color: "var(--danger)", marginLeft: 4 }}>*</span>}
          </label>
          {error && <div className="text-xs" style={{ color: "var(--danger)", marginTop: 4 }}>{error}</div>}
        </div>
      );
    case "dropdown":
      control = (
        <select value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} style={big}>
          <option value="">Select…</option>
          {(field.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
      break;
    case "date":
      control = <input type="date" value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} style={big} />;
      break;
    case "datetime":
      control = <input type="datetime-local" value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} style={big} />;
      break;
    case "number":
    case "currency":
      control = <input type="number" value={String(value ?? "")} min={field.min} max={field.max} onChange={(e) => onChange(e.target.value)} style={big} />;
      break;
    default:
      control = <input type="text" value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} style={big} />;
  }

  return (
    <div>
      {label}
      {control}
      {error && <div className="text-xs" style={{ color: "var(--danger)", marginTop: 4 }}>{error}</div>}
    </div>
  );
}
