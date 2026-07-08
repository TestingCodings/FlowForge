import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import {
  applyTheme,
  DATE_FORMAT_OPTIONS,
  FONT_OPTIONS,
  useWorkspace,
} from "../hooks/useWorkspace";

const THEME_FIELDS: { key: string; label: string; hint: string }[] = [
  { key: "accent",         label: "Accent",           hint: "Buttons, links, highlights" },
  { key: "accent_light",   label: "Accent (light)",   hint: "Hover states, secondary accents" },
  { key: "bg_base",        label: "Background",       hint: "Page background" },
  { key: "bg_surface",     label: "Surface",          hint: "Cards and panels" },
  { key: "bg_elevated",    label: "Elevated",         hint: "Inputs, dropdowns, nested panels" },
  { key: "bg_hover",       label: "Hover",            hint: "Row and button hover" },
  { key: "text_primary",   label: "Text",             hint: "Primary text colour" },
  { key: "text_secondary", label: "Text (secondary)", hint: "Labels, captions, muted copy" },
  { key: "border",         label: "Border",           hint: "Card and input borders" },
  { key: "success",        label: "Success",          hint: "Positive states" },
  { key: "warning",        label: "Warning",          hint: "SLA warnings, approvals" },
  { key: "danger",         label: "Danger",           hint: "Errors, breaches, deletes" },
];

/** Built-in theme presets. "Midnight" is the shipped default (empty = stylesheet values). */
const PRESETS: { name: string; theme: Record<string, string> }[] = [
  { name: "Midnight", theme: {} },
  {
    name: "Daylight",
    theme: {
      accent: "#4f46e5", accent_light: "#6366f1",
      bg_base: "#f6f8fa", bg_surface: "#ffffff", bg_elevated: "#eef1f4", bg_hover: "#e4e8ec",
      text_primary: "#1f2328", text_secondary: "#59636e", text_disabled: "#a1a9b1",
      border: "#d1d9e0", border_light: "#e8ecef",
      success: "#1a7f37", warning: "#9a6700", danger: "#d1242f", info: "#0969da",
    },
  },
  {
    name: "Ocean",
    theme: {
      accent: "#0ea5e9", accent_light: "#38bdf8",
      bg_base: "#0c1220", bg_surface: "#111a2e", bg_elevated: "#1a2742", bg_hover: "#223252",
      text_primary: "#e2ecf7", text_secondary: "#8ba3bf",
      border: "#243552",
      success: "#34d399", warning: "#fbbf24", danger: "#fb7185", info: "#7dd3fc",
    },
  },
  {
    name: "Forest",
    theme: {
      accent: "#22c55e", accent_light: "#4ade80",
      bg_base: "#0c1410", bg_surface: "#121c16", bg_elevated: "#1a2820", bg_hover: "#22342a",
      text_primary: "#e4f0e8", text_secondary: "#8fa898",
      border: "#25382d",
      success: "#4ade80", warning: "#facc15", danger: "#f87171", info: "#5eead4",
    },
  },
];

export default function WorkspacePage() {
  const qc = useQueryClient();
  const { data: workspace } = useWorkspace();

  const [name, setName] = useState("");
  const [tagline, setTagline] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [font, setFont] = useState("inter");
  const [dateFormat, setDateFormat] = useState("locale");
  const [theme, setTheme] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!workspace) return;
    setName(workspace.name);
    setTagline(workspace.tagline);
    setLogoUrl(workspace.logo_url);
    setFont(workspace.ui_config?.font ?? "inter");
    setDateFormat(workspace.ui_config?.date_format ?? "locale");
    setTheme(workspace.ui_config?.theme ?? {});
  }, [workspace]);

  // Live preview while editing
  useEffect(() => {
    applyTheme(theme, font);
  }, [theme, font]);

  const save = useMutation({
    mutationFn: async () =>
      (await apiClient.put("/workspace/", {
        name, tagline, logo_url: logoUrl,
        ui_config: { theme, font, date_format: dateFormat },
      })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workspace"] });
      setSaved(true);
      setErr(null);
      setTimeout(() => setSaved(false), 3000);
    },
    onError: (e: any) => setErr(e?.response?.data?.detail ?? "Failed to save workspace"),
  });

  const activePreset = PRESETS.find(
    p => JSON.stringify(p.theme) === JSON.stringify(theme)
  )?.name;

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>Workspace</h2>
          <p>Branding, theme, and formatting — applies for every user</p>
        </div>
        <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save workspace"}
        </button>
      </div>

      {saved && <div className="alert alert-success mb-4">Workspace saved — settings are live for all users.</div>}
      {err && <div className="alert alert-error mb-4">{err}</div>}

      <div className="grid grid-2">
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <div className="card-header"><h3>Identity</h3></div>
            <div className="form-group">
              <label>Workspace name</label>
              <input value={name} onChange={e => setName(e.target.value)} placeholder="Acme Corp" />
            </div>
            <div className="form-group">
              <label>Tagline</label>
              <input value={tagline} onChange={e => setTagline(e.target.value)} placeholder="Claims Processing" />
            </div>
            <div className="form-group">
              <label>Logo URL <span className="text-muted">(optional)</span></label>
              <input value={logoUrl} onChange={e => setLogoUrl(e.target.value)} placeholder="https://…/logo.png" style={{ fontFamily: "monospace", fontSize: "0.82rem" }} />
            </div>
          </div>

          <div className="card">
            <div className="card-header"><h3>Formatting</h3></div>
            <div className="form-group">
              <label>Font</label>
              <select value={font} onChange={e => setFont(e.target.value)}>
                {FONT_OPTIONS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>Date format</label>
              <select value={dateFormat} onChange={e => setDateFormat(e.target.value)}>
                {DATE_FORMAT_OPTIONS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
              </select>
            </div>
            <p className="text-xs text-muted" style={{ lineHeight: 1.6 }}>
              Dates across the platform (instance tables, timelines, boards) follow this format.
            </p>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3>Theme</h3>
            <div className="flex gap-1">
              {PRESETS.map(p => (
                <button
                  key={p.name}
                  className={activePreset === p.name ? "btn-primary btn-sm" : "btn-secondary btn-sm"}
                  onClick={() => setTheme({ ...p.theme })}
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {THEME_FIELDS.map(f => (
              <div key={f.key} style={{ display: "grid", gridTemplateColumns: "44px 1fr 110px", gap: 10, alignItems: "center" }}>
                <input
                  type="color"
                  value={theme[f.key] ?? "#000000"}
                  onChange={e => setTheme(t => ({ ...t, [f.key]: e.target.value }))}
                  style={{ width: 40, height: 30, padding: 2, border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-elevated)", cursor: "pointer" }}
                />
                <div>
                  <div className="text-sm" style={{ fontWeight: 600 }}>{f.label}</div>
                  <div className="text-xs text-muted">{f.hint}</div>
                </div>
                <input
                  value={theme[f.key] ?? ""}
                  placeholder="default"
                  onChange={e => {
                    const v = e.target.value;
                    setTheme(t => {
                      const next = { ...t };
                      if (v) next[f.key] = v; else delete next[f.key];
                      return next;
                    });
                  }}
                  style={{ fontFamily: "monospace", fontSize: "0.8rem", padding: "5px 8px" }}
                />
              </div>
            ))}
          </div>
          <div className="divider" />
          <p className="text-xs text-muted">
            Changes preview live. Empty fields fall back to the Midnight defaults. Presets are
            starting points — adjust any token after applying one.
          </p>
        </div>
      </div>
    </div>
  );
}
