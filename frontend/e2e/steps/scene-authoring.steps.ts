import { expect } from "@playwright/test";
import { Given, When, Then, apiFetch } from "./fixtures";

const E2E_PREFIX = "E2E Scene Flow";

async function sweepStale(page: any) {
  const wfs = await apiFetch(page, "GET", "/workflows/");
  const list = (wfs.json as any).results ?? wfs.json;
  for (const wf of list) {
    if (typeof wf.name === "string" && wf.name.startsWith(E2E_PREFIX)) {
      await apiFetch(page, "DELETE", `/workflows/${wf.id}/`);
    }
  }
}

Given("I am viewing a throwaway scene workflow", async ({ page }) => {
  await sweepStale(page);
  const name = `${E2E_PREFIX} ${Date.now()}`;
  const created = await apiFetch(page, "POST", "/workflows/", {
    name,
    reference_prefix: "SCN",
    version: 1,
    is_active: true,
    states: [
      { name: "Awakening", is_initial: true, is_terminal: false, position_order: 1, sla_config: {}, task_config: {} },
      { name: "The Hallway", is_initial: false, is_terminal: false, position_order: 2, sla_config: {}, task_config: {} },
      { name: "Freedom", is_initial: false, is_terminal: true, position_order: 3, sla_config: {}, task_config: {} },
    ],
    transitions: [
      { name: "Open your eyes", from_state: "Awakening", to_state: "The Hallway", requires_approval: false },
      { name: "Step outside", from_state: "The Hallway", to_state: "Freedom", requires_approval: false },
    ],
  });
  expect(created.status, `workflow create failed: ${JSON.stringify(created.json)}`).toBe(201);

  const workflowId = (created.json as any).id;
  const patched = await apiFetch(page, "PATCH", `/workflows/${workflowId}/ui-schema/`, {
    ui_schema: {
      shell: "scene",
      scene_config: {
        Awakening: {
          speaker: "Narrator",
          dialogue: "You wake on a cold floor.",
        },
        "The Hallway": {
          speaker: "Narrator",
          dialogue: "The hallway is silent.",
        },
      },
    },
  });
  expect(patched.status, `ui-schema patch failed: ${JSON.stringify(patched.json)}`).toBe(200);

  await page.goto(`/workflows/${workflowId}`);
  await expect(page.getByRole("button", { name: "Save scenes" })).toBeVisible();
});

Then("I see the scene editor populated from its existing config", async ({ page }) => {
  const awakening = page.locator("[data-scene-state='Awakening']");
  await expect(awakening).toBeVisible();
  await expect(awakening.getByText("Configured")).toBeVisible();
  await expect(awakening.locator("[data-scene-field='speaker']")).toHaveValue("Narrator");
  await expect(awakening.locator("[data-scene-field='dialogue']")).toHaveValue("You wake on a cold floor.");
});

When("I save the scene editor without changes", async ({ page }) => {
  const responsePromise = page.waitForResponse((resp) =>
    resp.request().method() === "PATCH" && resp.url().includes("/ui-schema/"),
  );
  await page.getByRole("button", { name: "Save scenes" }).click();
  const response = await responsePromise;
  const text = await response.text();
  let json: unknown = null;
  try { json = text ? JSON.parse(text) : null; } catch { json = text; }
  (page as any)._lastSceneSave = { status: response.status(), json };
});

Then("I see the scene editor save successfully", async ({ page }) => {
  expect((page as any)._lastSceneSave?.status).toBe(200);
  await expect(page.getByText("Scenes saved.")).toBeVisible();
});

When("I close the YAML modal", async ({ page }) => {
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.locator("textarea[readonly]")).toHaveCount(0);
});

When("I add a sprite row to the {string} scene", async ({ page }, stateName: string) => {
  const card = page.locator(`[data-scene-state='${stateName}']`);
  await card.getByRole("button", { name: "+ Add sprite" }).click();
});

Then("I see a validation error on the {string} scene sprite asset field", async ({ page }, stateName: string) => {
  const card = page.locator(`[data-scene-state='${stateName}']`);
  expect((page as any)._lastSceneSave?.status).toBe(400);
  await expect(card.getByText(`ui_schema.scene_config['${stateName}'].sprites[0] requires an 'asset'.`)).toBeVisible();
});

When("I remove the incomplete sprite from the {string} scene", async ({ page }, stateName: string) => {
  const card = page.locator(`[data-scene-state='${stateName}']`);
  await card.locator("[data-scene-sprite='0']").getByRole("button", { name: "Remove" }).click();
});

When("I set the {string} scene speaker to {string}", async ({ page }, stateName: string, speaker: string) => {
  const card = page.locator(`[data-scene-state='${stateName}']`);
  await card.locator("[data-scene-field='speaker']").fill(speaker);
});

When("I set the {string} scene dialogue to {string}", async ({ page }, stateName: string, dialogue: string) => {
  const card = page.locator(`[data-scene-state='${stateName}']`);
  await card.locator("[data-scene-field='dialogue']").fill(dialogue);
});

Then("the YAML contains the scene speaker {string}", async ({ page }, speaker: string) => {
  await expect(page.locator("textarea[readonly]")).toHaveValue(new RegExp(`speaker:\\s+${speaker}`));
});

Then("the YAML contains the scene dialogue {string}", async ({ page }, dialogue: string) => {
  await expect(page.locator("textarea[readonly]")).toHaveValue(new RegExp(dialogue.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});
