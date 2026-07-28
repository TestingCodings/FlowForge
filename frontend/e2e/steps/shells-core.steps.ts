import { expect } from "@playwright/test";
import { Given, When, Then, apiFetch, findWorkflowByName } from "./fixtures";

/**
 * @core shell steps. These reconfigure a workflow's ui_schema, which is
 * shared mutable state, so each scenario must own a workflow no other spec
 * reads:
 *
 *   table  → Employee Leave Request
 *   matrix → Test Run
 *   list   → Release
 *
 * Two rules, both learned the hard way:
 *
 * 1. Every workflow named here must exist in `manage.py seed --testrail`,
 *    which is what CI runs. This once pointed at a workflow called "Test"
 *    that the seed has never created — it passed only on a developer machine
 *    that happened to have one by hand, so the suite could never go green on
 *    a clean database.
 * 2. Don't pick a workflow another feature asserts against. "Bug Report"
 *    looks free but workflows.feature opens it and expects an "Open kanban
 *    view" action, which changing the shell here would break.
 */

async function configureShell(page: any, workflowName: string, uiSchemaPatch: Record<string, unknown>) {
  // Paginated lookup: a page-1-only search silently misses seeded workflows
  // once the database holds more than 25.
  const wf = await findWorkflowByName(page, workflowName);
  const full = await apiFetch(page, "GET", `/workflows/${wf.id}/`);
  const resp = await apiFetch(page, "PATCH", `/workflows/${wf.id}/ui-schema/`, {
    ui_schema: { ...((full.json as any).ui_schema ?? {}), ...uiSchemaPatch },
  });
  expect(resp.status, `ui-schema patch failed: ${JSON.stringify(resp.json)}`).toBe(200);
  (page as any)._shellWorkflowId = wf.id; // consumed by the shared "I open its view"
  return wf.id;
}

Given(
  "a workflow configured with the {string} shell and columns {string}",
  async ({ page }, shell: string, columns: string) => {
    await configureShell(page, "Employee Leave Request", {
      shell, list_columns: columns.split(",").map((c) => c.trim()),
    });
  },
);

Given("a workflow configured with the {string} shell", async ({ page }, shell: string) => {
  await configureShell(page, "Release", { shell });
});

Given(
  "the {string} workflow uses the {string} shell grouped by suite and state",
  async ({ page }, name: string, shell: string) => {
    await configureShell(page, name, {
      shell, matrix: { rows: "metadata.suite", columns: "current_state" },
    });
  },
);

Then("the table header shows {string}, {string} and {string}", async ({ page }, a: string, b: string, c: string) => {
  for (const label of [a, b, c]) {
    await expect(page.getByRole("columnheader", { name: new RegExp(label, "i") })).toBeVisible();
  }
});

Then("I see a row per suite", async ({ page }) => {
  // Matrix rows are keyed by the suite metadata; the seeded Test Runs have
  // several distinct suites.
  const rows = page.locator("table tbody tr");
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThan(1);
});

Then("I see a column per state", async ({ page }) => {
  // The matrix only renders columns for states that instances actually
  // occupy, not every state the workflow defines — so a fixed number was
  // never satisfiable (Test Run defines 5 states but its seeded instances
  // sit in 3). Derive the expectation from the data instead.
  // Filter by the id the Given step stashed — the API filters on
  // workflow_definition by id only, so a name filter would be ignored and
  // silently return every instance in the system.
  const wfId = (page as any)._shellWorkflowId;
  const insts = await apiFetch(page, "GET", `/instances/?workflow_definition=${wfId}`);
  const rows = ((insts.json as any).results ?? insts.json) as any[];
  const occupied = new Set(rows.map((i) => i.current_state_name)).size;
  const headers = page.locator("table thead th");
  await expect(headers.first()).toBeVisible();
  // One label column for the row axis, plus one per occupied state.
  expect(await headers.count()).toBe(occupied + 1);
});

Then("cells show state-coloured instance chips", async ({ page }) => {
  await expect(page.locator("table tbody button").first()).toBeVisible();
});

When("I filter the list by a reference substring", async ({ page }) => {
  // Must match the workflow the list-shell scenario configures above.
  await page.getByPlaceholder(/filter by reference/i).fill("REL");
});

Then("only matching instances remain", async ({ page }) => {
  const rows = page.locator(".card > div[style*='cursor']");
  await expect(rows.first()).toBeVisible();
  for (const text of await rows.allTextContents()) {
    expect(text).toMatch(/REL/);
  }
  // And a non-matching filter empties the list with the no-match message.
  await page.getByPlaceholder(/filter by reference/i).fill("zzz-no-match");
  await expect(page.getByText(/no instances match/i)).toBeVisible();
});
