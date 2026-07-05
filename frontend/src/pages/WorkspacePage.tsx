import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { applyTheme, useWorkspace } from "../hooks/useWorkspace";

const THEME_FIELDS: { key: string; label: string; hint: string }[] = [
  { key: "accent",       label: "Accent",          hint: "Buttons, links, highlights" },
  { key: "accent_light", label: "Accent (light)",  hint: "Hover states, secondary accents" },
  { key: "bg_base",      label: "Background",      hint: "Page background" },
  { key: "bg_surface",   label: "Surface",         hint: "Cards and panels" },
  { key: "bg_elevated",  label: "Elevated",        hint: "Inputs, dropdowns, nested panels" },
  { key: "text_primary", label: "Text",            hint: "Primary text colour" },
  { key: "success",      label: "Success",         hint: "Positive states" },
  { key: "warning",      label: "Warning",         hint: "SLA warnings, approvals" },
  { key: "danger",       label: "Danger",          hint: "Errors, breaches, deletes" },
];

const DEFAULTS: Record<string, string> = {
  accent: "#6366f1", accent_light: "#818cf8",
  bg_base: "#0d1117", bg_surface: "#161b22", bg_elevated: "#21262d",
  text_primary: "#e6edf3",
  success: "#3fb950", warning: "#d29922", danger: "#f85149",
};

export default function WorkspacePage() {
  const qc = useQueryClient();
  const { data: workspace } = useWorkspace();

  const [name, setName] = useState("");
  const [tagline, setTagline] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [theme, setTheme] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!workspace) return;
    setName(workspace.name);
    setTagline(workspace.tagline);
    setLogoUrl(workspace.logo_url);
    setTheme({ ...DEFAULTS, ...(workspace.ui_config?.theme ?? {}) });
  }, [workspace]);

  // Live preview while editing
  useEffect(() => {
    if (Object.keys(theme).length) applyTheme(theme);
  }, [theme]);

  const save = useMutation({
    mutationFn: async () =>
      (await apiClient.put("/workspace/", {
        name, tagline, logo_url: logoUrl,
        ui_config: { ...(workspace?.ui_config ?? {}), theme },
      })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workspace"] });
      setSaved(true);
      setErr(null);
      setTimeout(() => setSaved(false), 3000);
    },
    onError: (e: any) => setErr(e?.response?.data?.detail ?? "Failed to save workspace"),
  });

  const reset = () => setTheme({ ...DEFAULTS });

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <h2>Workspace</h2>
          <p>Branding and theme — changes apply for every user (Layer 1 white-labelling)</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary btn-sm" onClick={reset}>Reset theme</button>
          <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save workspace"}
          </button>
        </div>
      </div>

      {saved && <div className="alert alert-success mb-4">Workspace saved — theme is live for all users.</div>}
      {err && <div className="alert alert-error mb-4">{err}</div>}

      <div className="grid grid-2">
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
          <p className="text-xs text-muted" style={{ lineHeight: 1.6 }}>
            The name and tagline replace the FlowForge branding in the sidebar. Together with the
            theme, a workspace can look like the client's own tool rather than a generic platform.
          </p>
        </div>

        <div className="card">
          <div className="card-header"><h3>Theme</h3></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {THEME_FIELDS.map(f => (
              <div key={f.key} style={{ display: "grid", gridTemplateColumns: "44px 1fr 110px", gap: 10, alignItems: "center" }}>
                <input
                  type="color"
                  value={theme[f.key] ?? DEFAULTS[f.key]}
                  onChange={e => setTheme(t => ({ ...t, [f.key]: e.target.value }))}
                  style={{ width: 40, height: 32, padding: 2, border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-elevated)", cursor: "pointer" }}
                />
                <div>
                  <div className="text-sm" style={{ fontWeight: 600 }}>{f.label}</div>
                  <div className="text-xs text-muted">{f.hint}</div>
                </div>
                <input
                  value={theme[f.key] ?? ""}
                  onChange={e => setTheme(t => ({ ...t, [f.key]: e.target.value }))}
                  style={{ fontFamily: "monospace", fontSize: "0.8rem", padding: "5px 8px" }}
                />
              </div>
            ))}
          </div>
          <div className="divider" />
          <p className="text-xs text-muted">
            Changes preview live as you pick colours. Save to persist for everyone; Reset restores
            the FlowForge defaults.
          </p>
        </div>
      </div>
    </div>
  );
}
