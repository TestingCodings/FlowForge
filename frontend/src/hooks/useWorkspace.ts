import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { Workspace } from "../types/api";

/** Maps ui_config.theme keys to the CSS custom properties in styles.css.
 *  Full coverage of the colour tokens so light themes render correctly. */
const THEME_VAR_MAP: Record<string, string> = {
  accent: "--accent",
  accent_light: "--accent-light",
  bg_base: "--bg-base",
  bg_surface: "--bg-surface",
  bg_elevated: "--bg-elevated",
  bg_hover: "--bg-hover",
  text_primary: "--text-primary",
  text_secondary: "--text-secondary",
  text_disabled: "--text-disabled",
  border: "--border",
  border_light: "--border-light",
  success: "--success",
  warning: "--warning",
  danger: "--danger",
  info: "--info",
};

export const FONT_OPTIONS: { value: string; label: string; stack: string }[] = [
  { value: "inter",  label: "Inter (default)", stack: '"Inter", "Segoe UI", system-ui, sans-serif' },
  { value: "system", label: "System",          stack: 'system-ui, "Segoe UI", Roboto, sans-serif' },
  { value: "serif",  label: "Serif",           stack: 'Georgia, "Times New Roman", serif' },
  { value: "mono",   label: "Monospace",       stack: '"JetBrains Mono", "Cascadia Code", Consolas, monospace' },
];

export const DATE_FORMAT_OPTIONS: { value: string; label: string }[] = [
  { value: "locale",     label: "Browser locale (default)" },
  { value: "dd/mm/yyyy", label: "DD/MM/YYYY" },
  { value: "mm/dd/yyyy", label: "MM/DD/YYYY" },
  { value: "yyyy-mm-dd", label: "YYYY-MM-DD (ISO)" },
];

export function applyWorkspaceConfig(ui: Workspace["ui_config"] | undefined) {
  const root = document.documentElement;
  const theme = ui?.theme;
  for (const [key, cssVar] of Object.entries(THEME_VAR_MAP)) {
    const value = theme?.[key];
    if (value) root.style.setProperty(cssVar, value);
    else root.style.removeProperty(cssVar);
  }
  // Derived glow from accent for focus rings
  if (theme?.accent) root.style.setProperty("--accent-glow", `${theme.accent}59`);
  else root.style.removeProperty("--accent-glow");

  const font = FONT_OPTIONS.find(f => f.value === ui?.font);
  if (font && font.value !== "inter") root.style.setProperty("--font", font.stack);
  else root.style.removeProperty("--font");
}

/** Backwards-compatible alias used by the theme editor's live preview. */
export function applyTheme(theme: Record<string, string> | undefined, font?: string) {
  applyWorkspaceConfig({ theme, font });
}

/* ── Workspace-aware date formatting ── */

let activeDateFormat = "locale";

function pad(n: number) {
  return String(n).padStart(2, "0");
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "";
  const d = typeof value === "string" ? new Date(value) : value;
  if (isNaN(d.getTime())) return "";
  switch (activeDateFormat) {
    case "dd/mm/yyyy": return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
    case "mm/dd/yyyy": return `${pad(d.getMonth() + 1)}/${pad(d.getDate())}/${d.getFullYear()}`;
    case "yyyy-mm-dd": return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    default:           return d.toLocaleDateString();
  }
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "";
  const d = typeof value === "string" ? new Date(value) : value;
  if (isNaN(d.getTime())) return "";
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return activeDateFormat === "locale" ? d.toLocaleString() : `${formatDate(d)} ${time}`;
}

export function useWorkspace() {
  const query = useQuery<Workspace>({
    queryKey: ["workspace"],
    queryFn: async () => (await apiClient.get("/workspace/")).data,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    applyWorkspaceConfig(query.data?.ui_config);
    activeDateFormat = query.data?.ui_config?.date_format ?? "locale";
  }, [query.data]);

  return query;
}
