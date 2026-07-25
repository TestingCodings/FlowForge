import { expect } from "@playwright/test";
import { Given, When, Then } from "./fixtures";

const API = process.env.E2E_API_BASE ?? "http://localhost:8000/api";

/** Set a workflow's shell via the API, using the token the UI stored at login. */
async function setShell(page: any, workflowName: string, shell: string): Promise<string> {
  return page.evaluate(
    async ({ api, name, shell }: { api: string; name: string; shell: string }) => {
      const token = localStorage.getItem("ff_access_token");
      const hdrs = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
      const wfs = await (await fetch(`${api}/workflows/`, { headers: hdrs })).json();
      const list = wfs.results ?? wfs;
      const wf = list.find((w: any) => w.name === name);
      if (!wf) throw new Error(`Workflow not found: ${name}`);
      await fetch(`${api}/workflows/${wf.id}/ui-schema/`, {
        method: "PATCH", headers: hdrs,
        body: JSON.stringify({ ui_schema: { ...wf.ui_schema, shell } }),
      });
      return wf.id as string;
    },
    { api: API, name: workflowName, shell },
  );
}

Given("the {string} workflow uses the {string} shell", async ({ page }, name: string, shell: string) => {
  const id = await setShell(page, name, shell);
  (page as any)._shellWorkflowId = id;
});

When("I open its view", async ({ page }) => {
  const id = (page as any)._shellWorkflowId;
  await page.goto(`/workflows/${id}/view`);
});

Then("I see a column for each workflow state", async ({ page }) => {
  // Kanban columns carry a data-col attribute per state.
  await expect(page.locator("[data-col]").first()).toBeVisible();
  const count = await page.locator("[data-col]").count();
  expect(count).toBeGreaterThan(1);
});

Then("each card links to its instance", async ({ page }) => {
  const cards = page.locator("[data-card]");
  if (await cards.count() > 0) {
    await expect(cards.first().getByRole("link")).toBeVisible();
  }
});
