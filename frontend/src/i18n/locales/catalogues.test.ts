import { describe, expect, it } from "vitest";

import { deDE } from "./de-DE";
import { enGB } from "./en-GB";
import { esES } from "./es-ES";
import { frFR } from "./fr-FR";

/**
 * Translation catalogue integrity.
 *
 * en-GB is the source of truth; the others are partials that fall back to it
 * at lookup time. That fallback is what makes a half-translated locale safe,
 * but it also hides mistakes: a key misspelled in es-ES silently serves
 * English forever, and nobody notices because the page still reads fine.
 *
 * These assertions catch the two failures the fallback would otherwise
 * conceal: keys that exist nowhere in the base, and placeholders that were
 * dropped or renamed in translation.
 */

const TRANSLATIONS = { "es-ES": esES, "fr-FR": frFR, "de-DE": deDE } as const;

const baseKeys = Object.keys(enGB);

function placeholders(text: string): string[] {
  return (text.match(/\{(\w+)\}/g) ?? []).sort();
}

describe("en-GB base catalogue", () => {
  it("has no empty messages", () => {
    for (const [key, value] of Object.entries(enGB)) {
      expect(value, `en-GB.${key} is empty`).toBeTruthy();
    }
  });

  it("namespaces every key with a dot", () => {
    // "nav.dashboard", not "dashboard" — the convention keeps the catalogue
    // navigable as it grows.
    for (const key of baseKeys) {
      expect(key, `${key} is not namespaced`).toContain(".");
    }
  });
});

describe.each(Object.entries(TRANSLATIONS))("%s catalogue", (name, catalogue) => {
  it("introduces no key that does not exist in en-GB", () => {
    // An orphan key is dead weight: nothing looks it up, and whatever it was
    // meant to translate is still showing English.
    const orphans = Object.keys(catalogue).filter((k) => !baseKeys.includes(k));
    expect(orphans, `${name} has keys absent from en-GB`).toEqual([]);
  });

  it("has no empty translations", () => {
    for (const [key, value] of Object.entries(catalogue)) {
      expect(value, `${name}.${key} is empty`).toBeTruthy();
    }
  });

  it("preserves every placeholder from the base message", () => {
    // "{count} instances" translated without {count} renders a sentence with
    // the number missing, which reads as a bug to the user.
    for (const [key, value] of Object.entries(catalogue)) {
      const expected = placeholders(enGB[key as keyof typeof enGB] as string);
      expect(placeholders(value as string), `${name}.${key} placeholder mismatch`)
        .toEqual(expected);
    }
  });
});

describe("coverage across locales", () => {
  it("reports how complete each locale is", () => {
    // Not an assertion so much as a guard against silent regression: if a
    // locale loses keys, the count moves and this test says so.
    const counts = Object.fromEntries(
      Object.entries(TRANSLATIONS).map(([name, c]) => [name, Object.keys(c).length]),
    );
    expect(counts).toEqual({ "es-ES": 27, "fr-FR": 42, "de-DE": 42 });
    expect(baseKeys.length).toBe(42);
  });

  it("keeps fully-translated locales complete", () => {
    for (const name of ["fr-FR", "de-DE"] as const) {
      const missing = baseKeys.filter((k) => !(k in TRANSLATIONS[name]));
      expect(missing, `${name} lost keys`).toEqual([]);
    }
  });
});
