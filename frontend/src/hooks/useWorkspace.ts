import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { Workspace } from "../types/api";

/** Maps ui_config.theme keys to the CSS custom properties in styles.css */
const THEME_VAR_MAP: Record<string, string> = {
  accent: "--accent",
  accent_light: "--accent-light",
  bg_base: "--bg-base",
  bg_surface: "--bg-surface",
  bg_elevated: "--bg-elevated",
  text_primary: "--text-primary",
  success: "--success",
  warning: "--warning",
  danger: "--danger",
};

export function applyTheme(theme: Record<string, string> | undefined) {
  const root = document.documentElement;
  for (const [key, cssVar] of Object.entries(THEME_VAR_MAP)) {
    const value = theme?.[key];
    if (value) root.style.setProperty(cssVar, value);
    else root.style.removeProperty(cssVar);
  }
  // Derived glow from accent for focus rings
  if (theme?.accent) {
    root.style.setProperty("--accent-glow", `${theme.accent}59`); // ~35% alpha
  } else {
    root.style.removeProperty("--accent-glow");
  }
}

export function useWorkspace() {
  const query = useQuery<Workspace>({
    queryKey: ["workspace"],
    queryFn: async () => (await apiClient.get("/workspace/")).data,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    applyTheme(query.data?.ui_config?.theme);
  }, [query.data]);

  return query;
}
