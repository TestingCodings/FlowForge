import { test as base, createBdd } from "playwright-bdd";
import type { Page } from "@playwright/test";

/** The seeded demo accounts (see backend seed command). */
export const ACCOUNTS: Record<string, { email: string; password: string }> = {
  "admin@flowforge.dev": { email: "admin@flowforge.dev", password: "Admin1234!" },
  "alice@flowforge.dev": { email: "alice@flowforge.dev", password: "Alice1234!" },
  "bob@flowforge.dev": { email: "bob@flowforge.dev", password: "Bob12345!" },
  "carol@flowforge.dev": { email: "carol@flowforge.dev", password: "Carol123!" },
};

/** Programmatic login: fills the login form and waits for the app shell. */
export async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByPlaceholder("you@example.com").fill(email);
  await page.getByPlaceholder("••••••••").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  // The app shell renders the sidebar nav once authenticated.
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 10_000 });
}

/**
 * Shared BDD test with a `signedInAs` helper. Scenarios that begin
 * "signed in as X" reuse this so auth isn't re-hand-rolled per step file.
 */
export const test = base.extend<{ signedInAs: (email: string) => Promise<void> }>({
  signedInAs: async ({ page }, use) => {
    await use(async (email: string) => {
      const acct = ACCOUNTS[email];
      if (!acct) throw new Error(`Unknown seeded account: ${email}`);
      await login(page, acct.email, acct.password);
    });
  },
});

export const { Given, When, Then } = createBdd(test);

/** Call the FlowForge API from inside the page, reusing the UI session's JWT. */
export async function apiFetch(page: Page, method: string, path: string, body?: unknown) {
  return page.evaluate(
    async ({ method, path, body, apiBase }) => {
      const token = localStorage.getItem("ff_access_token");
      const resp = await fetch(`${apiBase}${path}`, {
        method,
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await resp.text();
      let json: unknown = null;
      try { json = text ? JSON.parse(text) : null; } catch { json = text; }
      return { status: resp.status, json };
    },
    { method, path, body, apiBase: process.env.E2E_API_BASE ?? "http://localhost:8000/api" },
  );
}
