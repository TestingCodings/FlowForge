import { expect } from "@playwright/test";
import { Given, When, Then, apiFetch, listAllWorkflows } from "./fixtures";

/**
 * @core instance lifecycle steps. Each scenario creates its own throwaway
 * workflow via the API (unique name; stale ones from crashed runs are swept
 * first), so nothing depends on — or mutates — the seeded demo data.
 */

const E2E_PREFIX = "E2E Core Flow";

async function sweepStale(page: any) {
  // All pages: a page-1-only sweep leaves leftovers permanently unsweepable.
  const list = await listAllWorkflows(page);
  for (const w of list) {
    if (typeof w.name === "string" && w.name.startsWith(E2E_PREFIX)) {
      await apiFetch(page, "DELETE", `/workflows/${w.id}/`); // may 400 if instances exist; best-effort
    }
  }
}

async function createFixture(page: any) {
  await sweepStale(page);
  const name = `${E2E_PREFIX} ${Date.now()}`;
  const wf = await apiFetch(page, "POST", "/workflows/", {
    name, reference_prefix: "E2E", version: 1, is_active: true,
    states: [
      { name: "Open", is_initial: true, is_terminal: false, position_order: 1, sla_config: {}, task_config: {} },
      { name: "Closed", is_initial: false, is_terminal: true, position_order: 2, sla_config: {}, task_config: {} },
    ],
    transitions: [{ name: "Complete", from_state: "Open", to_state: "Closed", requires_approval: false }],
  });
  expect(wf.status, `workflow create failed: ${JSON.stringify(wf.json)}`).toBe(201);
  const inst = await apiFetch(page, "POST", "/instances/", {
    workflow_definition: (wf.json as any).id, metadata_json: { note: "before" },
  });
  expect(inst.status, `instance create failed: ${JSON.stringify(inst.json)}`).toBe(201);
  return inst.json as any;
}

Given("I am viewing an open instance with an available transition", async ({ page }) => {
  const inst = await createFixture(page);
  await page.goto(`/instances/${inst.id}`);
  await expect(page.getByRole("heading", { name: /actions/i })).toBeVisible();
});

Given("I am viewing an open instance", async ({ page }) => {
  const inst = await createFixture(page);
  await page.goto(`/instances/${inst.id}`);
  await expect(page.getByRole("heading", { name: /metadata/i })).toBeVisible();
});

When("I fire the transition", async ({ page }) => {
  // The button's accessible name includes the state arrow ("Complete Open → Closed"),
  // so match on the transition name rather than exactly.
  await page.locator("button.transition-btn").filter({ hasText: "Complete" }).click();
});

Then("the instance's current state updates", async ({ page }) => {
  // The fixture's transition lands on a terminal state, so the header badge
  // flips to Completed — an unambiguous, user-visible state change.
  await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible();
});

Then("the timeline records the transition", async ({ page }) => {
  const timeline = page.locator(".card", { has: page.getByRole("heading", { name: /timeline/i }) });
  await expect(timeline.getByText(/transition/i).first()).toBeVisible();
});

When("I edit a metadata value and save", async ({ page }) => {
  const metaCard = page.locator(".card", { has: page.getByRole("heading", { name: /metadata/i }) });
  await metaCard.getByRole("button", { name: "Edit" }).click();
  // Fill BOTH key and value: when an instance has no metadata the editor seeds
  // a blank row, and saving with an empty key is rejected client-side.
  await metaCard.getByPlaceholder("field name").first().fill("note");
  await metaCard.getByPlaceholder("value").first().fill("after-edit");
  await metaCard.getByRole("button", { name: "Save", exact: true }).click();
  await expect(metaCard.getByRole("button", { name: "Edit" })).toBeVisible(); // editor closed = saved
});

Then("the metadata shows the new value", async ({ page }) => {
  const metaCard = page.locator(".card", { has: page.getByRole("heading", { name: /metadata/i }) });
  await expect(metaCard.getByText("after-edit")).toBeVisible();
});

Then("the timeline records a metadata update", async ({ page }) => {
  const timeline = page.locator(".card", { has: page.getByRole("heading", { name: /timeline/i }) });
  await expect(timeline.getByText(/metadata/i).first()).toBeVisible();
});
