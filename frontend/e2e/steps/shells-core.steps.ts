import { expect } from "@playwright/test";
import { Given, When, Then, apiFetch } from "./fixtures";

/**
 * @core shell steps. Each scenario reconfigures a DIFFERENT seeded workflow's
 * ui_schema (table → Employee Leave Request, matrix → Test Run, list → Test)
 * so parallel workers never mutate the same row.
 */

async function configureShell(page: any, workflowName: string, uiSchemaPatch: Record<string, unknown>) {
  const wfs = await apiFetch(page, "GET", "/workflows/");
  const list = (wfs.json as any).results ?? wfs.json;
  const wf = list.find((w: any) => w.name === workflowName);
  expect(wf, `workflow not found: ${workflowName}`).toBeTruthy();
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
  await configureShell(page, "Test", { shell });
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
  const headers = page.locator("table thead th");
  // suite label column + one per workflow state (Test Run has 5 states)
  expect(await headers.count()).toBeGreaterThanOrEqual(5);
});

Then("cells show state-coloured instance chips", async ({ page }) => {
  await expect(page.locator("table tbody button").first()).toBeVisible();
});

When("I filter the list by a reference substring", async ({ page }) => {
  // The seeded "Test" workflow's instances carry the default WFF prefix.
  await page.getByPlaceholder(/filter by reference/i).fill("WFF");
});

Then("only matching instances remain", async ({ page }) => {
  const rows = page.locator(".card > div[style*='cursor']");
  await expect(rows.first()).toBeVisible();
  for (const text of await rows.allTextContents()) {
    expect(text).toMatch(/WFF/);
  }
  // And a non-matching filter empties the list with the no-match message.
  await page.getByPlaceholder(/filter by reference/i).fill("zzz-no-match");
  await expect(page.getByText(/no instances match/i)).toBeVisible();
});
