import { expect } from "@playwright/test";
import { When, Then } from "./fixtures";

When("I open the workflow builder", async ({ page }) => {
  await page.goto("/workflows/new");
  // Dismiss any resumable draft banner so the canvas is deterministic.
  const discard = page.getByRole("button", { name: "Discard" });
  if (await discard.isVisible().catch(() => false)) await discard.click();
});

Then('the canvas shows one state node marked {string}', async ({ page }, badge: string) => {
  await expect(page.locator(".react-flow__node")).toHaveCount(1);
  await expect(page.locator(".react-flow__node").getByText(badge, { exact: false })).toBeVisible();
});

Then("the toolbar shows the Save, Add State, and Auto-layout controls", async ({ page }) => {
  await expect(page.getByRole("button", { name: /save workflow/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /add state/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /auto-layout/i })).toBeVisible();
});
