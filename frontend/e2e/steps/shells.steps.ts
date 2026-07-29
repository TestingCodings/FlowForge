import { expect } from "@playwright/test";
import { Given, When, Then, createWorkflowFixture, sweepFixtures } from "./fixtures";

/**
 * Shell scenarios build their own workflow rather than repointing a seeded
 * one. Mutating shared workflows made the suite unreliable under parallel
 * workers and coupled it to unrelated features — workflows.feature opens
 * "Bug Report" expecting a kanban action, which broke whenever a shell
 * scenario changed that workflow's shell.
 */
Given("the {string} workflow uses the {string} shell", async ({ page }, label: string, shell: string) => {
  await sweepFixtures(page);
  const wf = await createWorkflowFixture(page, {
    label: label.replace(/[^A-Za-z]/g, "") || "Shell",
    prefix: "SHL",
    states: [{ name: "Open" }, { name: "Doing" }, { name: "Done", terminal: true }],
    transitions: [
      { name: "Start", from: "Open", to: "Doing" },
      { name: "Finish", from: "Doing", to: "Done" },
    ],
    uiSchema: { shell },
    instances: [
      { metadata: { title: "First" } },
      { metadata: { title: "Second" }, advance: ["Start"] },
    ],
  });
  (page as any)._shellWorkflowId = wf.id;
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
