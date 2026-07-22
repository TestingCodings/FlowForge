/**
 * Lightweight i18n scaffolding (VISION Layer 1 `locale`).
 *
 * Deliberately dependency-free: a workspace picks a `locale` in ui_config, a
 * provider resolves the matching catalogue, and `useTranslation().t(key)`
 * looks a message up with en-GB fallback and `{placeholder}` interpolation.
 *
 * This is the foundation, not a full translation of the app — nav and common
 * actions are wired as the proof. Adding a language = one catalogue file in
 * ./locales plus a line in LOCALES; translating more = more keys in en-GB.ts.
 */
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { enGB, type Catalogue, type MessageKey } from "./locales/en-GB";
import { esES } from "./locales/es-ES";

export interface LocaleOption {
  value: string;      // BCP-47 tag, also used for Intl date/number formatting
  label: string;      // shown in the workspace settings picker
  catalogue: Catalogue;
}

/** Registered locales. en-GB is always first and is the fallback. */
export const LOCALES: LocaleOption[] = [
  { value: "en-GB", label: "English (UK)", catalogue: enGB },
  { value: "es-ES", label: "Español", catalogue: esES },
];

export const DEFAULT_LOCALE = "en-GB";

export type TranslateFn = (key: MessageKey, vars?: Record<string, string | number>) => string;

interface I18nContextValue {
  locale: string;
  t: TranslateFn;
}

const I18nContext = createContext<I18nContextValue>({
  locale: DEFAULT_LOCALE,
  t: (key) => enGB[key],
});

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (m, name) =>
    name in vars ? String(vars[name]) : m,
  );
}

export function I18nProvider({ locale, children }: { locale?: string; children: ReactNode }) {
  const active = LOCALES.find((l) => l.value === locale) ?? LOCALES[0];

  // Keep <html lang> in sync for accessibility and native formatting.
  if (typeof document !== "undefined") {
    document.documentElement.lang = active.value;
  }

  const t = useCallback<TranslateFn>(
    (key, vars) => {
      const msg = active.catalogue[key] ?? enGB[key] ?? key;
      return interpolate(msg, vars);
    },
    [active],
  );

  const value = useMemo(() => ({ locale: active.value, t }), [active.value, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useTranslation() {
  return useContext(I18nContext);
}

export type { MessageKey };
