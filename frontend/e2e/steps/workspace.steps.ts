import { expect } from "@playwright/test";
import { After, Given, When, Then, apiFetch } from "./fixtures";

/**
 * Workspace configuration.
 *
 * These settings are the one genuinely global thing in the product: theme,
 * language and density apply to every user on the install. That makes them
 * the opposite of the fixture pattern used everywhere else, because there is
 * only one workspace and a scenario cannot own its own copy.
 *
 * So each scenario snapshots the config on the way in and the After hook puts
 * it back, whether the scenario passed or failed. Without that, switching the
 * language to Spanish here would leave every later scenario running against a
 * Spanish interface, which is exactly the shared-state trap the shell
 * scenarios used to fall into.
 */

const SNAPSHOT = Symbol.for("ff.workspace.snapshot");

Given("I am on the workspace settings page", async ({ page }) => {
  const current = await apiFetch(page, "GET", "/workspace/");
  const body = current.json as any;
  (page as any)[SNAPSHOT] = {
    name: body.name,
    tagline: body.tagline,
    logo_url: body.logo_url,
    ui_config: body.ui_config ?? {},
  };

  await page.goto("/admin/workspace");
  await expect(page.getByRole("button", { name: /save workspace/i })).toBeVisible();
});

After(async ({ page }) => {
  const snapshot = (page as any)[SNAPSHOT];
  if (!snapshot) return;
  // Restore even on failure: a half-changed workspace poisons the rest of
  // the run, and a failing assertion is not a reason to leave it that way.
  await apiFetch(page, "PUT", "/workspace/", snapshot);
  (page as any)[SNAPSHOT] = undefined;
});

async function save(page: any) {
  await page.getByRole("button", { name: /save workspace/i }).click();
  await expect(page.getByText(/saved/i).first()).toBeVisible({ timeout: 10_000 });
}

When("I apply the {string} theme preset and save", async ({ page }, preset: string) => {
  await page.getByRole("button", { name: preset, exact: true }).click();
  await save(page);
});

Then("the platform adopts the new theme colours", async ({ page }) => {
  // The preset writes CSS custom properties onto the document root, so the
  // check is what the browser actually computed rather than what we sent.
  const accent = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--accent").trim(),
  );
  expect(accent, "no accent token applied").toBeTruthy();

  const stored = await apiFetch(page, "GET", "/workspace/");
  expect((stored.json as any).ui_config?.theme?.accent).toBeTruthy();
});

When("I set the language to {string} and save", async ({ page }, language: string) => {
  await page.getByLabel("Language").selectOption({ label: language });
  await save(page);
});

Then("the sidebar navigation appears in Spanish", async ({ page }) => {
  // "Panel" is the es-ES translation of the dashboard nav item; asserting on
  // rendered navigation proves the catalogue reached the UI, not just the API.
  await expect(page.getByRole("link", { name: /Panel|Instancias|Flujos/ }).first())
    .toBeVisible({ timeout: 10_000 });
});

Then("the document language is {string}", async ({ page }, lang: string) => {
  await expect.poll(
    async () => page.evaluate(() => document.documentElement.lang),
    { timeout: 10_000 },
  ).toBe(lang);
});

When("I set the density to {string} and save", async ({ page }, density: string) => {
  // selectOption matches an exact label, and the comfortable option reads
  // "Comfortable (default)". Select by value, which is the stable identifier.
  await page.getByLabel("Density").selectOption(density.toLowerCase());
  await save(page);
});

Then("the interface uses the compact spacing", async ({ page }) => {
  const stored = await apiFetch(page, "GET", "/workspace/");
  expect((stored.json as any).ui_config?.density).toBe("compact");

  // And it reached the document, rather than only the database.
  await expect.poll(
    async () => page.evaluate(() => document.documentElement.dataset.density ?? ""),
    { timeout: 10_000 },
  ).toBe("compact");
});
