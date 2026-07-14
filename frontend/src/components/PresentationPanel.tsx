import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { ShellName, Workflow, WorkflowUiSchema } from "../types/api";
import Hint from "./Hint";
import { SHELL_OPTIONS } from "./shells";

interface Props {
  workflow: Workflow;
}

/** Visual configurator for ui_schema — no JSON editing (VISION "UI Schema Builder"). */
export default function PresentationPanel({ workflow }: Props) {
  const qc = useQueryClient();
  const [shell, setShell] = useState<ShellName>("list");
  const [titleField, setTitleField] = useState("");
  const [cardFields, setCardFields] = useState("");
  const [listColumns, setListColumns] = useState("");
  const [dateField, setDateField] = useState("");
  const [stateColours, setStateColours] = useState<Record<string, string>>({});
  const [childWorkflows, setChildWorkflows] = useState<string[]>([]);
  const [childColumns, setChildColumns] = useState("");
  const [rollUp, setRollUp] = useState(true);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const { data: allWorkflows = [] } = useQuery<Workflow[]>({
    queryKey: ["workflows"],
    queryFn: async () => (await apiClient.get("/workflows/")).data.results ?? [],
  });

  useEffect(() => {
    const ui = workflow.ui_schema ?? {};
    setShell(ui.shell ?? "list");
    setTitleField(ui.title_field ?? "");
    setCardFields((ui.card_fields ?? []).join(", "));
    setListColumns((ui.list_columns ?? []).join(", "));
    setDateField(ui.date_field ?? "");
    setChildWorkflows(ui.children?.workflows ?? []);
    setChildColumns((ui.children?.columns ?? []).join(", "));
    setRollUp(ui.children?.roll_up ?? true);
    const colours: Record<string, string> = {};
    for (const [name, cfg] of Object.entries(ui.state_display ?? {})) {
      if (cfg?.colour) colours[name] = cfg.colour;
    }
    setStateColours(colours);
  }, [workflow]);

  const save = useMutation({
    mutationFn: async () => {
      const parseList = (s: string) => s.split(",").map(x => x.trim()).filter(Boolean);
      const ui: WorkflowUiSchema = { shell };
      if (titleField.trim()) ui.title_field = titleField.trim();
      if (shell === "kanban" && cardFields.trim()) ui.card_fields = parseList(cardFields);
      if (shell === "table" && listColumns.trim()) ui.list_columns = parseList(listColumns);
      if (shell === "calendar" && dateField.trim()) ui.date_field = dateField.trim();
      const display: Record<string, { colour: string }> = {};
      for (const [name, colour] of Object.entries(stateColours)) {
        if (colour) display[name] = { colour };
      }
      if (Object.keys(display).length) ui.state_display = display;
      if (childWorkflows.length) {
        ui.children = { workflows: childWorkflows, shell: "table", roll_up: rollUp };
        if (childColumns.trim()) ui.children.columns = parseList(childColumns);
      }
      return (await apiClient.patch(`/workflows/${workflow.id}/ui-schema/`, { ui_schema: ui })).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow", workflow.id] });
      setErr(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
    onError: (e: any) => setErr(e?.response?.data?.detail ?? "Failed to save presentation"),
  });

  const states = [...(workflow.states ?? [])].sort((a, b) => a.position_order - b.position_order);

  return (
    <div className="card mt-4">
      <div className="card-header">
        <h3>Presentation <Hint tip="Controls how this workflow looks for everyone: a simple list, a drag-and-drop board, a table, or a calendar — plus colours and which details appear on cards." /></h3>
        <div className="flex gap-2 items-center">
          {shell !== "list" && (
            <Link to={`/workflows/${workflow.id}/view`} className="btn-secondary btn-sm" style={{ textDecoration: "none" }}>
              Open {shell} view
            </Link>
          )}
          <button className="btn-primary btn-sm" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save presentation"}
          </button>
        </div>
      </div>

      {saved && <div className="alert alert-success mb-2">Presentation saved.</div>}
      {err && <div className="alert alert-error mb-2">{err}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div>
          <div className="form-group">
            <label>Shell</label>
            <select value={shell} onChange={e => setShell(e.target.value as ShellName)}>
              {SHELL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          <div className="form-group">
            <label>Title field <span className="text-muted">(metadata key, optional)</span></label>
            <input
              value={titleField}
              onChange={e => setTitleField(e.target.value)}
              placeholder="e.g. title, suite, claimant_name"
              style={{ fontFamily: "monospace", fontSize: "0.82rem" }}
            />
          </div>

          {shell === "kanban" && (
            <div className="form-group">
              <label>Card fields <span className="text-muted">(metadata keys, comma-separated)</span></label>
              <input
                value={cardFields}
                onChange={e => setCardFields(e.target.value)}
                placeholder="e.g. suite, build, priority"
                style={{ fontFamily: "monospace", fontSize: "0.82rem" }}
              />
            </div>
          )}

          {shell === "table" && (
            <div className="form-group">
              <label>Columns <span className="text-muted">(comma-separated)</span></label>
              <input
                value={listColumns}
                onChange={e => setListColumns(e.target.value)}
                placeholder="reference, state, sla, created, metadata.priority"
                style={{ fontFamily: "monospace", fontSize: "0.82rem" }}
              />
              <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                Built-ins: <code>reference</code>, <code>state</code>, <code>sla</code>, <code>status</code>, <code>created</code> — plus any <code>metadata.&lt;key&gt;</code>
              </div>
            </div>
          )}

          {shell === "calendar" && (
            <div className="form-group">
              <label>Date field</label>
              <input
                value={dateField}
                onChange={e => setDateField(e.target.value)}
                placeholder="created_at (default) or a metadata key, e.g. due_date"
                style={{ fontFamily: "monospace", fontSize: "0.82rem" }}
              />
            </div>
          )}
        </div>

        <div>
          <div className="text-xs text-muted mb-2" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            State colours
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {states.map(s => (
              <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <input
                  type="color"
                  value={stateColours[s.name] ?? "#6b7280"}
                  onChange={e => setStateColours(c => ({ ...c, [s.name]: e.target.value }))}
                  style={{ width: 34, height: 26, padding: 1, border: "1px solid var(--border)", borderRadius: 5, background: "var(--bg-elevated)", cursor: "pointer" }}
                />
                <span className="text-sm" style={{ flex: 1 }}>{s.display_name || s.name}</span>
                {stateColours[s.name] && (
                  <button
                    className="btn-ghost btn-sm"
                    style={{ padding: "2px 6px" }}
                    title="Clear colour"
                    onClick={() => setStateColours(c => { const n = { ...c }; delete n[s.name]; return n; })}
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
          <p className="text-xs text-muted" style={{ marginTop: 10, lineHeight: 1.5 }}>
            Colours apply to kanban column headers, table state badges, and calendar chips.
          </p>
        </div>
      </div>

      <div className="divider" />

      {/* ── Sub-instances (containers) ── */}
      <div className="text-xs text-muted mb-2" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
        Sub-instances
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div>
          <div className="text-sm mb-2">Which workflows can nest inside a {workflow.name}?</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {allWorkflows.filter(w => w.id !== workflow.id).map(w => (
              <label key={w.id} className="text-sm" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={childWorkflows.includes(w.name)}
                  onChange={() =>
                    setChildWorkflows(cur =>
                      cur.includes(w.name) ? cur.filter(n => n !== w.name) : [...cur, w.name],
                    )
                  }
                />
                {w.name}
                <span className="text-xs text-muted" style={{ fontFamily: "monospace" }}>{w.reference_prefix}</span>
              </label>
            ))}
          </div>
        </div>
        <div>
          <div className="form-group">
            <label>Child table columns <span className="text-muted">(optional)</span></label>
            <input
              value={childColumns}
              onChange={e => setChildColumns(e.target.value)}
              placeholder="reference, state, metadata.priority"
              style={{ fontFamily: "monospace", fontSize: "0.82rem" }}
              disabled={childWorkflows.length === 0}
            />
          </div>
          <label className="text-sm" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
            <input type="checkbox" checked={rollUp} onChange={() => setRollUp(!rollUp)} disabled={childWorkflows.length === 0} />
            Show completion roll-up on the parent
          </label>
          <p className="text-xs text-muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
            Rules can gate parent transitions on children: use the injected fields{" "}
            <code>children_complete</code>, <code>children_open</code>, <code>children_total</code>.
          </p>
        </div>
      </div>
    </div>
  );
}
